#!/usr/bin/env bash
set -euo pipefail
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
pkill -f 'python3 -m kurz' 2>/dev/null || true
rm -rf "$DATA/kurz" \
       "$DATA/krunner/dbusplugins/kurz.desktop" \
       "$DATA/dbus-1/services/dev.indiwine.Kurz.service" \
       "${XDG_CACHE_HOME:-$HOME/.cache}/kurz"
kquitapp6 krunner 2>/dev/null || true
echo "Uninstalled."
