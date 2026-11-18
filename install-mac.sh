#!/bin/bash
# Pokémon restock monitor – one-step Mac installer.
# Run in Terminal:
#   curl -fsSL https://raw.githubusercontent.com/MauroHdd/Pokemon-Restock/main/install-mac.sh | bash
set -e

APP="$HOME/pokemon-restock"
PLIST="$HOME/Library/LaunchAgents/com.pokemon.restock.plist"
ZIP_URL="https://github.com/MauroHdd/Pokemon-Restock/archive/refs/heads/main.zip"

echo "🔎 Checking Python..."
if ! /usr/bin/python3 -c "import sys" >/dev/null 2>&1; then
  echo ""
  echo "👉 Your Mac needs Apple's free developer tools first."
  echo "   A window will pop up: click INSTALL, wait for it to finish,"
  echo "   then paste the same command into Terminal again."
  xcode-select --install || true
  exit 1
fi

echo "⬇️  Downloading the monitor..."
TMP="$(mktemp -d)"
curl -fsSL "$ZIP_URL" -o "$TMP/app.zip"
unzip -q "$TMP/app.zip" -d "$TMP"
SRC="$(find "$TMP" -maxdepth 1 -type d -name 'Pokemon-Restock-*' | head -1)"
mkdir -p "$APP"
[ -f "$APP/state.json" ] && cp "$APP/state.json" "$TMP/state.json"   # keep memory of past alerts
cp -R "$SRC/." "$APP/"
[ -f "$TMP/state.json" ] && cp "$TMP/state.json" "$APP/state.json"
rm -rf "$TMP"

echo "📦 Installing (about 1 minute)..."
cd "$APP"
/usr/bin/python3 -m venv venv
./venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 || true
./venv/bin/pip install -q -r requirements.txt

echo "⚙️  Setting it to run automatically..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.pokemon.restock</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$APP/venv/bin/python</string><string>monitor.py</string><string>--loop</string>
  </array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP/monitor.log</string>
  <key>StandardErrorPath</key><string>$APP/monitor.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/com.pokemon.restock" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "📲 Sending a test alert to your phone..."
./venv/bin/python monitor.py --test-sms || true

echo ""
echo "✅ DONE! The monitor is running and checks stores every 5–8 minutes."
echo "   It starts by itself whenever this Mac turns on."
echo "   See what it's doing:  tail -f ~/pokemon-restock/monitor.log"
