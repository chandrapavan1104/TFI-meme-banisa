#!/bin/bash
# Install TFI-meme-banisa as a launchd user service (starts on login, restarts on crash).
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_DST="$HOME/Library/LaunchAgents/com.tfibanisa.server.plist"

mkdir -p "$HOME/.tfibanisa/logs" "$HOME/Library/LaunchAgents"
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__HOME__|$HOME|g" \
  "$PROJECT_DIR/scripts/tfibanisa.plist" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "Service installed and started. Check: curl http://localhost:8000/health"
echo "Uninstall with: launchctl unload $PLIST_DST && rm $PLIST_DST"
