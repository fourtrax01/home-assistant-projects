# Home Assistant Projects

A few of the more interesting pieces of my Home Assistant setup, shared because people asked how I did them.
Everything here is pulled from a live install (HA 2026.11) with personal details replaced:
people are `Parent 1/2` and `Kid 1/2`, LAN IPs are `192.168.1.x`, and MAC-based entity IDs are `aa_bb_cc_dd_ee_NN`.
**Change the IPs and entity IDs to match your own setup before using anything.**

| Project | What it does |
|---|---|
| [govee-porch-lights](govee-porch-lights/) | Per-bead **local LAN control** of Govee H7076 wall lights and H6069 mini panels (no cloud), with holiday looks, animations and calendar-driven themes |
| [wled-eaves](wled-eaves/) | A small bridge that streams WLED effects onto the Govee porch lights so the permanent eave lights and porch lights animate as one strip |
| [hvac-zoning](hvac-zoning/) | DIY HVAC zoning: ESPHome damper controller (GP8403 DACs, fail-open) plus the HA controller automations and safety watchdogs |
| [doorbell-ai-captions](doorbell-ai-captions/) | Frigate doorbell events → AI caption (local Ollama vision model first, Gemini fallback) → phone and TV popup notifications with a clip |
| [school-wake-alarm](school-wake-alarm/) | School-day wake-up alarm with a sick-day "skip next alarm" button that re-arms itself |
| [big-alarm-keypad](big-alarm-keypad/) | A custom Lovelace card: a big square keypad for wall tablets |

## Hardware / integrations used
Home Assistant OS · Frigate (Coral) · ESPHome · WLED · Govee H7076 / H6069 · Z-Wave + Zigbee (ZHA) · UniFi · Ollama on a Synology/PC · Google Gemini (fallback)

## Security notes
- No secrets are stored in this repo. ESPHome uses `!secret`, the Gemini key is read from a file at runtime, and
  `.gitignore` excludes `secrets.yaml`, key/token files, `.env` files and HA's `.storage`/database files.
- Files in `/config/www` are public to anyone with the URL (`/local/...` needs no login). The doorbell project
  uses unguessable names and short retention; see its README.
- Govee's LAN API, Frigate's API, RTSP restreams and the WLED bridge have no or minimal authentication. Keep
  these devices on a trusted LAN/VLAN and never port-forward them.

## Notes
- These are shared as examples, not drop-in packages. Expect to adapt entity IDs.
- Built with a lot of help from Claude Code.
- No warranty: HVAC changes in particular can damage equipment. Read the safety notes first.
