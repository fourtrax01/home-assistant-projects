# Govee porch lights: per-bead local control

Govee's LAN API officially only supports on/off, brightness and a single color. By capturing the Govee app's
Bluetooth traffic, I found that the "DIY" packets can be sent over the LAN `ptReal` command
(UDP port 4003). That gives **per-bead color control** of H7076 wall lights and **per-panel control** of
H6069 mini panels, fully local, with no cloud.

## Files
| File | Purpose |
|---|---|
| `porch.py` | Core H7076 protocol: `porch.py IP top=RRGGBB left=RRGGBB right=RRGGBB 5=RRGGBB ... [bri=]`. Bead map: 0 top, 1 bottom, 2-18 left strip, 19-35 right strip |
| `porch_looks.py` | Named looks/animations across 6 lights (Christmas, Halloween, chases, twinkle…): `porch_looks.py list` |
| `govee_panels.py` | H6069 per-panel colors: `govee_panels.py IP "0:ff0000" "1:00ff00"` |
| `heart.py` | Scenes and animations for a 20-panel heart layout of H6069 panels |
| `govee_scene.py` | Trigger Govee's **built-in** scenes locally (`h6069_effects.json` / `h7076_effects.json` hold the decoded scene codes) |
| `automations.yaml` | HA automations: holiday calendar → porch look, arrival whites, offline auto power-cycle, eave lights following the porch |
| `scripts.yaml` | HA scripts for each holiday/animation look |

## Setup
1. Enable **LAN Control** for each light in the Govee app.
2. Give the lights DHCP reservations, then edit the IPs: `IPS` in `porch.py`, `IP` in `heart.py`, `WLED` in `porch_looks.py`.
3. Copy the Python files and the two JSON files to `/config/govee_tools/` (the scripts expect that path).
4. Add the shell commands HA calls (`configuration.yaml`), then restart HA:

```yaml
shell_command:
  porch_look: "python3 /config/govee_tools/porch_looks.py {{ look }} bri={{ bri | default(100) }}"
  heart_scene: "python3 /config/govee_tools/heart.py {{ scene }}"
```

Only the Python standard library is needed. The automations also expect some things from my setup that you'll want
to swap for your own: the `input_select.porch_look` / `porch_govee_scene` pickers, the UniFi `device_tracker`
entities used to detect a light that dropped off Wi-Fi, the smart plugs used to power-cycle it, the govee2mqtt
add-on, and the `rest_command.porch_eaves_bridge` from [`../wled-eaves`](../wled-eaves/).

**Security:** Govee's LAN API has no authentication, so any device on the same network can control the lights
over UDP 4003. Put them on a trusted network or IoT VLAN.
