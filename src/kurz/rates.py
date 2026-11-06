"""Exchange rates from fawazahmed0/exchange-api, with an on-disk cache.

https://github.com/fawazahmed0/exchange-api — free, no key, daily updates,
~300 currencies including UAH.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

# Primary CDN + the project's documented fallback.
URLS = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/{path}",
    "https://latest.currency-api.pages.dev/v1/{path}",
)
TTL_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 4
USER_AGENT = "kurz/0.1"


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = Path(base) / "kurz"
    path.mkdir(parents=True, exist_ok=True)
    return path


class RateSource:
    def __init__(self, cache_dir: Path | None = None, ttl: float = TTL_SECONDS):
        self.cache_dir = cache_dir or _cache_dir()
        self.ttl = ttl
        self._mem: dict[str, tuple[float, dict]] = {}

    # -- low level -----------------------------------------------------------

    def _fetch(self, path: str) -> dict:
        last_err: Exception | None = None
        for template in URLS:
            url = template.format(path=path)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                    return json.load(resp)
            except (urllib.error.URLError, TimeoutError, ValueError) as err:
                log.warning("fetch %s failed: %s", url, err)
                last_err = err
        raise ConnectionError(f"all sources failed for {path}") from last_err

    def _get(self, name: str, path: str) -> dict:
        """Memory cache -> fresh disk cache -> network -> stale disk cache."""
        now = time.time()
        hit = self._mem.get(name)
        if hit and now - hit[0] < self.ttl:
            return hit[1]

        file = self.cache_dir / f"{name}.json"
        stale: dict | None = None
        if file.exists():
            try:
                data = json.loads(file.read_text())
                mtime = file.stat().st_mtime
                if now - mtime < self.ttl:
                    self._mem[name] = (mtime, data)
                    return data
                stale = data
            except (OSError, ValueError):
                pass

        try:
            data = self._fetch(path)
        except ConnectionError:
            if stale is None:
                raise
            log.warning("using stale cache for %s", name)
            # Don't hammer the network on every keystroke while offline.
            self._mem[name] = (now - self.ttl + 300, stale)
            return stale

        tmp = file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(file)
        self._mem[name] = (now, data)
        return data

    # -- public API ----------------------------------------------------------

    def currencies(self) -> dict[str, str]:
        """Lower-case code -> human name."""
        return self._get("currencies", "currencies.min.json")

    def rates(self, base: str) -> tuple[str, dict[str, float]]:
        """Return (date, {code: rate}) for 1 unit of *base*."""
        base = base.lower()
        data = self._get(f"rates-{base}", f"currencies/{base}.min.json")
        return data.get("date", "?"), data[base]

    def convert(self, amount: float, source: str, target: str) -> tuple[float, str]:
        date, table = self.rates(source)
        return amount * table[target.lower()], date
