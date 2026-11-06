#!/usr/bin/env bash
# Per-user install: no sudo, no compilation. Re-run after editing the code.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
LIB="$DATA/kurz"

mkdir -p "$LIB" "$DATA/krunner/dbusplugins" "$DATA/dbus-1/services"

rm -rf "$LIB/kurz"
cp -r "$SRC/src/kurz" "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +

cp "$SRC/data/kurz.desktop" "$DATA/krunner/dbusplugins/"

# D-Bus activation: KRunner starts the service on first query.
cat > "$DATA/dbus-1/services/dev.indiwine.Kurz.service" <<EOF
[D-BUS Service]
Name=dev.indiwine.Kurz
Exec=/usr/bin/env PYTHONPATH=$LIB /usr/bin/python3 -m kurz
EOF

# Restart any running instance so new code is picked up, then KRunner.
pkill -f 'python3 -m kurz' 2>/dev/null || true
kquitapp6 krunner 2>/dev/null || true

echo "Installed. Try Alt+Space → 500 EUR to UAH"
