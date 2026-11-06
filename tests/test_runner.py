import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dbus

from kurz import runner
from kurz.runner import (
    DEFAULT_CONFIG,
    ICON,
    CurrencyRunner,
    clipboard_value,
    copy_to_clipboard,
    format_amount,
    load_config,
    make_match,
)

NNBSP = " "


class FakeRates:
    """Stand-in for RateSource: 1 EUR = 51.29 UAH = 24.29 CZK = 1.12 USD."""

    TABLE = {"eur": 1.0, "uah": 51.29, "czk": 24.29, "usd": 1.12}

    def __init__(self, offline=False):
        self.offline = offline
        self.currencies_calls = 0

    def currencies(self):
        self.currencies_calls += 1
        if self.offline:
            raise ConnectionError
        return {c: c.upper() for c in self.TABLE}

    def rates(self, base):
        return "2026-11-05", {}

    def convert(self, amount, source, target):
        if self.offline:
            raise ConnectionError
        if target not in self.TABLE:
            raise KeyError(target)
        return amount / self.TABLE[source] * self.TABLE[target], "2026-11-05"


def make_runner(rates=None, config=None):
    return CurrencyRunner(None, rates or FakeRates(), config or dict(DEFAULT_CONFIG), warm_up=False)


class FormatAmountTest(unittest.TestCase):
    def test_formats(self):
        cases = {
            0: "0",
            5: "5.00",
            1234.5: f"1{NNBSP}234.50",
            25644.6312: f"25{NNBSP}644.63",
            1_000_000: f"1{NNBSP}000{NNBSP}000.00",
            0.0195: "0.0195",
            0.123456: "0.1235",
            0.00001234: "1.2340e-05",
            -42.5: "-42.50",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_amount(value), expected)


class ClipboardValueTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(clipboard_value(25644.6312), "25644.63")
        self.assertEqual(clipboard_value(1_000_000), "1000000.00")
        self.assertEqual(clipboard_value(0.0195123), "0.0195123")


class MakeMatchTest(unittest.TestCase):
    def test_shape(self):
        match_id, text, icon, kind, relevance, props = make_match("uah", 25644.6312, 0.9)
        self.assertEqual(match_id, "25644.63")
        self.assertEqual(text, f"25{NNBSP}644.63 UAH")
        self.assertEqual(icon, ICON)
        self.assertEqual(kind, 100)
        self.assertEqual(relevance, 0.9)
        self.assertEqual(props, {"category": "Currency"})

    def test_no_subtext(self):
        self.assertNotIn("subtext", make_match("eur", 1.0, 1.0)[5])


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()
        self.file = Path(self.tmp.name) / "kurz" / "config.json"

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_defaults_without_file(self):
        self.assertEqual(load_config(), DEFAULT_CONFIG)

    def test_user_targets_lowercased(self):
        self.file.parent.mkdir()
        self.file.write_text(json.dumps({"default_targets": ["PLN", "Uah"]}))
        self.assertEqual(load_config()["default_targets"], ["pln", "uah"])

    def test_broken_file_falls_back(self):
        self.file.parent.mkdir()
        self.file.write_text("{not json")
        with self.assertLogs("kurz", "WARNING"):
            self.assertEqual(load_config(), DEFAULT_CONFIG)

    def test_does_not_mutate_defaults(self):
        self.file.parent.mkdir()
        self.file.write_text(json.dumps({"default_targets": ["PLN"]}))
        load_config()
        self.assertEqual(DEFAULT_CONFIG["default_targets"], ["usd", "eur", "czk", "uah"])


class MatchesTest(unittest.TestCase):
    def test_explicit_target(self):
        [match] = make_runner().matches("500 EUR to UAH")
        self.assertEqual(match[0], "25645.00")
        self.assertEqual(match[1], f"25{NNBSP}645.00 UAH")
        self.assertEqual(match[4], 1.0)

    def test_default_targets_skip_source(self):
        results = make_runner().matches("500 eur")
        self.assertEqual([m[1].split()[-1] for m in results], ["USD", "CZK", "UAH"])
        relevances = [m[4] for m in results]
        self.assertEqual(relevances, sorted(relevances, reverse=True))

    def test_default_targets_skip_unknown(self):
        r = make_runner(config={"default_targets": ["xyz", "uah"]})
        self.assertEqual([m[1].split()[-1] for m in r.matches("1 eur")], ["UAH"])

    def test_non_currency_query(self):
        r = make_runner()
        self.assertEqual(r.matches("500 km to mi"), [])
        self.assertEqual(r.matches("firefox"), [])

    def test_offline_returns_nothing(self):
        self.assertEqual(make_runner(FakeRates(offline=True)).matches("500 eur to uah"), [])

    def test_missing_rate_is_skipped(self):
        rates = FakeRates()
        with mock.patch.object(rates, "convert", side_effect=KeyError("uah")):
            with self.assertLogs("kurz", "WARNING"):
                self.assertEqual(make_runner(rates).matches("500 eur to uah"), [])

    def test_currency_list_loaded_once(self):
        rates = FakeRates()
        r = make_runner(rates)
        r.matches("1 eur to uah")
        r.matches("2 eur to uah")
        self.assertEqual(rates.currencies_calls, 1)

    def test_warm_up_swallows_errors(self):
        r = make_runner(FakeRates(offline=True))
        with self.assertLogs("kurz", "WARNING"):
            r._warm_up()


class DBusMethodsTest(unittest.TestCase):
    def test_match_delegates(self):
        r = make_runner()
        self.assertEqual(r.Match("500 eur to uah"), r.matches("500 eur to uah"))

    def test_actions_empty(self):
        self.assertEqual(make_runner().Actions(), [])

    def test_run_copies_match_id(self):
        with mock.patch.object(runner, "copy_to_clipboard") as copy:
            make_runner().Run("25645.00", "")
        copy.assert_called_once_with("25645.00")


class CopyToClipboardTest(unittest.TestCase):
    def test_calls_klipper(self):
        with mock.patch.object(runner.dbus, "SessionBus") as bus:
            copy_to_clipboard("42.00")
        bus.return_value.get_object.assert_called_once_with("org.kde.klipper", "/klipper")
        bus.return_value.get_object.return_value.setClipboardContents.assert_called_once_with(
            "42.00", dbus_interface="org.kde.klipper.klipper"
        )

    def test_dbus_error_is_logged(self):
        with mock.patch.object(runner.dbus, "SessionBus", side_effect=dbus.DBusException("no bus")):
            with self.assertLogs("kurz", "WARNING"):
                copy_to_clipboard("1")


if __name__ == "__main__":
    unittest.main()
