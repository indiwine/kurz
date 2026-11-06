"""KRunner D-Bus runner (org.kde.krunner1) for currency conversion.

Query examples:  ``500 EUR to UAH``, ``500 eur uah``, ``€20 in czk``, ``2k usd``
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from .parser import parse_query
from .rates import RateSource

log = logging.getLogger("kurz")

SERVICE = "dev.indiwine.Kurz"
OBJPATH = "/kurz"
IFACE = "org.kde.krunner1"
ICON = "accessories-calculator"

DEFAULT_CONFIG = {
    # Shown when the query has no target, e.g. "500 eur".
    "default_targets": ["usd", "eur", "czk", "uah"],
}


def load_config() -> dict:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = Path(base) / "kurz" / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(path.read_text()))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as err:
        log.warning("bad config %s: %s", path, err)
    cfg["default_targets"] = [c.lower() for c in cfg["default_targets"]]
    return cfg


def format_amount(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1:
        text = f"{value:,.2f}"
    else:
        # Small values (crypto, weak currencies): keep 4 significant digits.
        text = f"{value:.4g}" if abs(value) >= 1e-4 else f"{value:.4e}"
    return text.replace(",", " ")  # narrow no-break space as thousands sep


def clipboard_value(value: float) -> str:
    """Plain number (no thousands separators) that Run() copies to the clipboard."""
    return f"{value:.2f}" if abs(value) >= 1 else f"{value:.6g}"


def make_match(target: str, value: float, relevance: float) -> tuple:
    """Build one org.kde.krunner1 match: (id, text, icon, type, relevance, props).

    The match id carries the value Run() copies; type 100 is
    QueryMatch::CategoryRelevance::Highest.
    """
    text = f"{format_amount(value)} {target.upper()}"
    return (clipboard_value(value), text, ICON, 100, relevance, {"category": "Currency"})


class CurrencyRunner(dbus.service.Object):
    def __init__(
        self,
        bus: dbus.Bus | None,
        rates: RateSource | None = None,
        config: dict | None = None,
        warm_up: bool = True,
    ):
        # bus=None creates an unexported object (used by the tests).
        super().__init__(bus, OBJPATH if bus is not None else None)
        self.rates = rates or RateSource()
        self.config = config or load_config()
        self._known: frozenset[str] = frozenset()
        if warm_up:
            threading.Thread(target=self._warm_up, daemon=True).start()

    def _warm_up(self) -> None:
        try:
            self._load_currencies()
            for code in self.config["default_targets"][:2]:
                self.rates.rates(code)
        except Exception as err:  # noqa: BLE001 - best effort
            log.warning("warm-up failed: %s", err)

    def _load_currencies(self) -> None:
        if not self._known:
            self._known = frozenset(self.rates.currencies())

    # -- matching ------------------------------------------------------------

    def matches(self, text: str) -> list[tuple]:
        try:
            self._load_currencies()
        except ConnectionError:
            return []
        query = parse_query(text, self._known)
        if query is None:
            return []
        targets = [query.target] if query.target else [
            t for t in self.config["default_targets"] if t != query.source and t in self._known
        ]
        out = []
        for i, target in enumerate(targets):
            try:
                value, _date = self.rates.convert(query.amount, query.source, target)
            except (ConnectionError, KeyError) as err:
                log.warning("convert %s failed: %s", query, err)
                continue
            out.append(make_match(target, value, relevance=1.0 - i * 0.01))
        return out

    # -- D-Bus interface -----------------------------------------------------

    @dbus.service.method(IFACE, in_signature="s", out_signature="a(sssida{sv})")
    def Match(self, query: str):
        return self.matches(str(query))

    @dbus.service.method(IFACE, out_signature="a(sss)")
    def Actions(self):
        return []

    @dbus.service.method(IFACE, in_signature="ss")
    def Run(self, match_id: str, action_id: str):
        copy_to_clipboard(str(match_id))

    @dbus.service.method(IFACE)
    def Teardown(self):
        pass


def copy_to_clipboard(text: str) -> None:
    try:
        klipper = dbus.SessionBus().get_object("org.kde.klipper", "/klipper")
        klipper.setClipboardContents(text, dbus_interface="org.kde.klipper.klipper")
    except dbus.DBusException as err:
        log.warning("clipboard copy failed: %s", err)


def main() -> None:
    logging.basicConfig(level=os.environ.get("KURZ_LOG", "WARNING"))
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    name = dbus.service.BusName(SERVICE, bus, do_not_queue=True)  # noqa: F841 - keep ref
    CurrencyRunner(bus)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
