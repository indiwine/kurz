# Kurz

**Kurz** (Czech/German for "exchange rate") is a currency converter for KDE Plasma 6 KRunner. It covers ~300 currencies, including
UAH, which the built-in unit converter lacks because that one only has ECB reference rates.

Rates come from [fawazahmed0/exchange-api](https://github.com/fawazahmed0/exchange-api)
(free, no API key, updated daily). They're cached in `~/.cache/kurz/` for 6 h,
and the last cached rates are used when you're offline.

## Usage

`Alt+Space`, then:

| Query | Result |
|---|---|
| `500 EUR to UAH` | one result |
| `500 eur uah`, `500eur in uah`, `500 eur -> uah` | same |
| `€20 to ₴`, `$10 to gbp`, `100 Kč to eur` | symbols work |
| `2k usd to uah`, `1.5m czk eur` | k / m suffixes |
| `500 eur` | converts to your default targets |

Each result is just the converted amount, e.g. `25 644.63 UAH`. Enter copies the number to the clipboard.

## Install / uninstall

Needs `python-dbus` and `python-gobject` (system packages).

```bash
./install.sh     # per-user, no sudo; re-run after editing code
./uninstall.sh
```

The script installs:
- `~/.local/share/kurz/kurz/`: the code
- `~/.local/share/krunner/dbusplugins/kurz.desktop`: registers the runner
- `~/.local/share/dbus-1/services/dev.indiwine.Kurz.service`: D-Bus activation

## Config

`~/.config/kurz/config.json` (optional):

```json
{ "default_targets": ["usd", "eur", "czk", "uah"] }
```

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v   # 47 tests, no extra deps
# run in foreground with logging (stop the installed one first):
pkill -f 'python3 -m kurz'; KURZ_LOG=INFO PYTHONPATH=src python3 -m kurz
# query it directly:
qdbus6 dev.indiwine.Kurz /kurz org.kde.krunner1.Match "500 eur to uah"
```
