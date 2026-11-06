import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from kurz import rates as rates_mod
from kurz.rates import URLS, RateSource

EUR = {"date": "2026-11-05", "eur": {"uah": 51.0, "czk": 24.3}}
CURRENCIES = {"eur": "Euro", "uah": "Ukrainian Hryvnia"}


def fake_response(payload):
    """Mimic the context manager returned by urlopen()."""
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
    return resp


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class CacheTest(TmpDirCase):
    def test_fetch_and_cache(self):
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value=EUR) as fetch:
            self.assertEqual(src.convert(10, "EUR", "UAH"), (510.0, "2026-11-05"))
            src.convert(1, "eur", "czk")
            fetch.assert_called_once_with("currencies/eur.min.json")
        self.assertEqual(json.loads((self.dir / "rates-eur.json").read_text()), EUR)
        self.assertFalse((self.dir / "rates-eur.tmp").exists())

    def test_fresh_disk_cache_skips_network(self):
        (self.dir / "rates-eur.json").write_text(json.dumps(EUR))
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", side_effect=AssertionError("network used")):
            self.assertAlmostEqual(src.convert(1, "eur", "czk")[0], 24.3)

    def test_expired_disk_cache_refetches(self):
        file = self.dir / "rates-eur.json"
        file.write_text(json.dumps({"date": "old", "eur": {"uah": 1.0}}))
        old = time.time() - 10 * 86400
        os.utime(file, (old, old))
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value=EUR):
            self.assertEqual(src.convert(1, "eur", "uah"), (51.0, "2026-11-05"))

    def test_expired_memory_cache_refetches(self):
        src = RateSource(self.dir, ttl=0)
        with mock.patch.object(src, "_fetch", return_value=EUR) as fetch:
            src.rates("eur")
            src.rates("eur")
        self.assertEqual(fetch.call_count, 2)

    def test_corrupt_disk_cache_refetches(self):
        (self.dir / "rates-eur.json").write_text("{garbage")
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value=EUR):
            self.assertEqual(src.rates("eur"), ("2026-11-05", EUR["eur"]))

    def test_stale_cache_used_when_offline(self):
        file = self.dir / "rates-eur.json"
        file.write_text(json.dumps(EUR))
        old = time.time() - 10 * 86400
        os.utime(file, (old, old))
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", side_effect=ConnectionError) as fetch:
            with self.assertLogs("kurz.rates", "WARNING"):
                self.assertEqual(src.convert(1, "eur", "uah")[0], 51.0)
            # Second lookup within the 5-minute backoff must not retry the network.
            src.convert(1, "eur", "uah")
        fetch.assert_called_once()

    def test_offline_without_cache_raises(self):
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", side_effect=ConnectionError):
            with self.assertRaises(ConnectionError):
                src.rates("eur")

    def test_unknown_target_raises_keyerror(self):
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value=EUR):
            with self.assertRaises(KeyError):
                src.convert(1, "eur", "xyz")

    def test_missing_date(self):
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value={"eur": {"uah": 2.0}}):
            self.assertEqual(src.rates("eur"), ("?", {"uah": 2.0}))

    def test_currencies(self):
        src = RateSource(self.dir)
        with mock.patch.object(src, "_fetch", return_value=CURRENCIES) as fetch:
            self.assertEqual(src.currencies(), CURRENCIES)
        fetch.assert_called_once_with("currencies.min.json")


class FetchTest(TmpDirCase):
    def test_primary_url(self):
        src = RateSource(self.dir)
        with mock.patch.object(rates_mod.urllib.request, "urlopen", return_value=fake_response(EUR)) as urlopen:
            self.assertEqual(src._fetch("currencies/eur.min.json"), EUR)
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, URLS[0].format(path="currencies/eur.min.json"))
        self.assertEqual(req.get_header("User-agent"), rates_mod.USER_AGENT)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], rates_mod.TIMEOUT_SECONDS)

    def test_falls_back_to_mirror(self):
        src = RateSource(self.dir)
        responses = [urllib.error.URLError("down"), fake_response(EUR)]
        with mock.patch.object(rates_mod.urllib.request, "urlopen", side_effect=responses) as urlopen:
            with self.assertLogs("kurz.rates", "WARNING"):
                self.assertEqual(src._fetch("x.json"), EUR)
        self.assertEqual(urlopen.call_args.args[0].full_url, URLS[1].format(path="x.json"))

    def test_all_sources_fail(self):
        src = RateSource(self.dir)
        errors = [TimeoutError(), urllib.error.URLError("down")]
        with mock.patch.object(rates_mod.urllib.request, "urlopen", side_effect=errors):
            with self.assertLogs("kurz.rates", "WARNING"), self.assertRaises(ConnectionError):
                src._fetch("x.json")

    def test_invalid_json_is_a_failure(self):
        src = RateSource(self.dir)
        bad = fake_response(None)
        bad.__enter__.return_value = io.BytesIO(b"<html>")
        with mock.patch.object(rates_mod.urllib.request, "urlopen", return_value=bad):
            with self.assertLogs("kurz.rates", "WARNING"), self.assertRaises(ConnectionError):
                src._fetch("x.json")


class CacheDirTest(unittest.TestCase):
    def test_respects_xdg_cache_home(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
            path = rates_mod._cache_dir()
            self.assertEqual(path, Path(tmp) / "kurz")
            self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()
