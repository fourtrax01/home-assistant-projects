# Doorbell AI captions

When Frigate sees a person at the door (or someone presses the doorbell), HA grabs a snapshot, gets a short AI
description and sends a phone notification. The notification is then replaced with a playable clip, and the
live doorbell video pops up on the TVs.

- `describe_image.py`: tries a **local Ollama vision model** first (private, free), then falls back to Gemini.
  The prompt is written to stop small models from making up details on dark or blurry frames,
  and it names delivery carriers (Amazon/UPS/FedEx/USPS/DHL) from uniform and truck colors.
  The Gemini key is read from a file (`/config/.gemini_key`) and sent in a request header, never in the URL or the script.
- `save_doorbell_clip.sh`: saves the Frigate clip into `/config/www/clips` so the companion app can play it.
  It rejects unexpected arguments (path traversal, non-numeric times).
- `automations.yaml`: the notification flow (one alert per visit), the "doorbell rang" dashboard helper and the nightly media cleanup
- `scripts.yaml`: the TV popups (TvOverlay app on Android/Google TV)
- `configuration.example.yaml`: the `shell_command` / `rest_command` entries and the helpers you need to create

## Setup
1. Copy `describe_image.py` and `save_doorbell_clip.sh` to `/config/scripts/` (`chmod +x` the shell script).
2. Add the entries from `configuration.example.yaml` and create the helpers listed at its top, then restart HA.
3. Edit the IPs: `OLLAMA_HOST` and `DRIVEWAY_URL` in `describe_image.py`, the TV and RTSP addresses in `scripts.yaml`.
   If Frigate isn't the HA add-on, set `FRIGATE_URL` for the clip script (or edit its default).
4. Optional Gemini fallback: put your API key alone in `/config/.gemini_key` (it's in `.gitignore`).
5. Set `clip_ext_url` in `automations.yaml` to your own external HA URL (Nabu Casa or reverse proxy), so tapping the
   notification opens the clip in the browser when you're away from home.
6. Replace `notify.mobile_app_parent1_phone`, `script.home_speaker_say` and the speakers with your own.

## Time limits
Home Assistant stops any `shell_command` after 60 seconds. The clip download gives up after 45 s, and
`describe_image.py` keeps all its AI calls (caption, carrier follow-ups, Gemini fallback) within a 50 s budget, so
neither is cut off mid-way. In normal use a clip downloads in a second or two.

## Privacy and security
Files in `/config/www` are served at `/local/...` **without login**, including through Nabu Casa or a reverse
proxy. That's what lets the phone notification and an external browser load the picture and clip, but it means
anyone who has the exact URL can open it. To keep that safe:

- **Unguessable names.** Each event's snapshot is `doorbell_<date>_<time>_<32 hex>.jpg`, and its clip is the same name
  with `.mp4`. The 32 hex characters (128 bits) come from Python's `secrets` module, the operating system's
  cryptographic random generator, through `shell_command.doorbell_token`, freshly for every event. A URL can't be
  guessed from the time of a visit. Nothing else is written to `/config/www` by this project.
- **Short retention.** The `Doorbell Media Cleanup` automation runs nightly at 03:00: snapshots are deleted once they're
  older than **30 days**, clips once they're older than **48 hours** (`find -mmin`, which is exact; `-mtime` rounds
  down to whole days). Because it runs once a day, a file can outlive its limit by up to 24 hours. The clip script
  also prunes old clips whenever it saves a new one.
- **No directory listing:** HA doesn't list `/local` folders, so files can only be found by exact name.

**Remaining limitations**
- Anyone who gets a specific URL (for example from a forwarded notification, a screenshot of the link or a shared
  device) can open that snapshot or clip until it's deleted. There is no per-user check.
- If `shell_command.doorbell_token` ever fails, the alert still goes out, but that one file name falls back to Jinja's
  non-cryptographic `random`, and a warning is written to the HA log (logger `doorbell`). Watch for it.
- On the LAN, the TV popups use the camera's RTSP restream and the carrier check uses Frigate's API (port 5000),
  and neither has a login. Keep cameras, Frigate and TVs on a trusted network or VLAN.
- Clips and snapshots are included in HA backups taken while they exist.

**Could it use authenticated URLs instead?** Partly. The companion app can show a notification picture from
`/api/camera_proxy/camera.doorbell` and adds your login automatically, but that shows the camera at the moment the
phone fetches it, not the moment of the visit. "Play Clip"/"View Photo" open in a normal browser, which has no
HA login, so authenticated URLs would break those buttons away from home. If you don't need the browser buttons,
keep only the in-app attachment and shorten retention further. Otherwise, random names plus short retention is
the trade-off used here.
