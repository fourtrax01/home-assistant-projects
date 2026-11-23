#!/bin/sh
# Pull a Frigate recording segment into /config/www/clips so the companion app
# can play it from /local (the /api/frigate proxy 404s in the app webview).
# Usage: save_doorbell_clip.sh <camera> <start_ts> <end_ts> <out_filename>
# FRIGATE_URL overrides the default (the Frigate add-on's internal hostname).
set -e

CAMERA="$1"
START="$2"
END="$3"
OUT="$4"
FRIGATE="${FRIGATE_URL:-http://ccab4aaf-frigate-fa:5000}"
DEST="/config/www/clips"

# Arguments come from an automation template; refuse anything unexpected
# (path traversal in the file name, odd camera names, non-numeric times).
case "$CAMERA" in ''|*[!A-Za-z0-9_-]*) echo "bad camera" >&2; exit 2 ;; esac
case "$START$END" in ''|*[!0-9]*) echo "bad time range" >&2; exit 2 ;; esac
case "$OUT" in doorbell_*.mp4) ;; *) echo "bad file name" >&2; exit 2 ;; esac
case "$OUT" in *[!A-Za-z0-9_.-]*|*..*) echo "bad file name" >&2; exit 2 ;; esac

mkdir -p "$DEST"
# Clips are only needed for the notification, so keep them 48 hours (-mmin is
# exact; -mtime rounds down to whole days). The daily cleanup automation also
# removes them, in case no new clip is saved for a while.
find "$DEST" -name 'doorbell_*.mp4' -mmin +2880 -delete 2>/dev/null || true

# Home Assistant kills a shell_command after 60 s, so finish well before that.
curl -sfS --connect-timeout 5 --max-time 45 -o "$DEST/$OUT" \
  "$FRIGATE/api/$CAMERA/start/$START/end/$END/clip.mp4" \
  || { rm -f "$DEST/$OUT"; echo "download failed" >&2; exit 1; }

# A zero-length file means Frigate had no footage for that window.
[ -s "$DEST/$OUT" ] || { rm -f "$DEST/$OUT"; echo "empty clip" >&2; exit 1; }
