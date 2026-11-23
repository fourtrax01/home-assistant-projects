# WLED → Govee bridge

My permanent eave lights run WLED. This bridge lets WLED treat the six Govee porch lights as extra pixels.
WLED sends them as a virtual **DDP** output, and `bridge.py` forwards each light's pixels using Govee's LAN
"razer"/DreamView streaming command. A chase effect then runs along the eaves *and* down through the porch lights.

- `bridge.py`: Python standard library only, configured with environment variables (documented in its header)
- `docker-compose.yml`: runs it with host networking, read-only, as an unprivileged user
- The HA automations that turn it on and off live in [`../govee-porch-lights/automations.yaml`](../govee-porch-lights/automations.yaml)
  (`Porch Follows Eaves - Apply` / `- Safety Off`).

## Install
1. In the Govee app, enable **LAN Control** on each light and give each light a DHCP reservation.
2. Edit `docker-compose.yml`: `GOVEE_IPS` (in strip order), `ALLOW_FROM` (your HA and WLED IPs) and optionally `BRIDGE_TOKEN`.
3. `docker compose up -d`, then check `docker logs wled-govee-bridge`.
4. In WLED: *Settings → LED Preferences → add a* **Virtual / DDP RGB** output pointing at the bridge host, port 4048,
   with `6 × PIXELS` LEDs (60 with the default `PIXELS=10`).
5. In Home Assistant (`configuration.yaml`):

```yaml
rest_command:
  porch_eaves_bridge:
    url: "http://192.168.1.20:8790/{{ action }}"   # bridge host; action = on | off | status
    method: GET
    timeout: 5
    # headers:                                    # only if you set BRIDGE_TOKEN
    #   X-Bridge-Token: !secret porch_bridge_token
```

## HTTP control
`GET /on`, `/off`, `/status`, and `/floor?pct=0-100&rgb=RRGGBB` (minimum porch glow between effects).
The bridge starts **disabled**, and HA re-sends `on` every 5 minutes while the feature is active.

## Security
The control endpoints can only switch the porch lights between "follow WLED" and normal, so the worst case on
an exposed bridge is someone changing your porch lights. Still:

- **Keep it on your LAN.** Don't publish or port-forward 8790/4048. Host networking publishes nothing by itself.
- **`ALLOW_FROM`** limits both the HTTP control and incoming DDP to the listed IPs/CIDRs. It defaults to private
  LAN ranges, so internet addresses are always refused; narrow it to your HA and WLED IPs.
- **`BRIDGE_TOKEN`** (optional) requires a shared secret on every HTTP request. This also stops a web page open on
  a LAN device from toggling the lights with a hidden link. Put the token in `secrets.yaml`, not in the repo.
- **`BIND_HOST`** can pin it to one interface if the host has several networks.
- No TLS: the token is sent in clear text on your LAN, so treat it as a nuisance barrier, not strong authentication.
- Govee's LAN protocol itself has no authentication: anything on the same network can control the lights directly
  over UDP 4003, with or without this bridge. Isolating IoT devices on their own VLAN is the real protection.
