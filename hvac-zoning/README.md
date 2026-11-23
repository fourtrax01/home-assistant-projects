# DIY HVAC zoning

Room-by-room zoning on a single-zone system, controlled from Home Assistant.

Two pieces of hardware are involved:
- **Register vents** (`cover.kids_bath_vent`, `cover.kid1_vent`, `cover.kid2_vent`): motorized ESPHome vents in
  each room. **These are what the included automations control today.** Their firmware isn't in this repo.
- **Duct-damper controller** (`hvac-zone-controller.yaml`): an ESP32 with two GP8403 DACs that drives up to four
  0-10 V spring-return dampers. It exposes `number.damper_1..4`; **none of the included automations use it yet.**

⚠️ **Closing too many dampers can overheat or freeze your equipment's coil.** Keep minimum-open limits and the
watchdog. This shows how I did it; it isn't installation advice. Check your equipment's static-pressure limits.

## Files
- `hvac-zone-controller.yaml`: ESPHome firmware for the duct-damper controller (secrets via `!secret`).
- `custom_templates/hvac_zoning.jinja`: **the decision logic** (macro `hvac_plan`). Copy it to `/config/custom_templates/`;
  the controller automation can't run without it.
- `automations.yaml`:
  - **HVAC Zoning Controller**: runs every minute; applies `hvac_plan` to the three vent covers
  - **HVAC Vent Safety Watchdog**: the backstop (see below)
  - **HVAC Zoning Disabled - Open Vents**, evening handoff, kids' bath cap, fan circulation balance, filter alert, cooling-rate logger
  - two commissioning auto-runs (for the one-time airflow tests)
- `scripts.yaml`: commissioning/airflow tests and **HVAC - Open All Vents (Safety)**

## How it fails safe
In Home Assistant (applies to the register vents):

| Situation | What happens |
|---|---|
| A room/duct sensor is unavailable or implausible, duct pressure over the hard limit, supply air too cold, delta-T too high | `hvac_plan` returns a safety state (`SENSOR_FAILURE`, `PRESSURE_OVERRIDE`, `TEMPERATURE_OVERRIDE`) and the controller opens **all** vents to 100%, then holds for a recovery period |
| Heating | all vents open |
| Controller automation stops running (heartbeat older than 5 min) | watchdog turns zoning off and runs Open All Vents |
| HA restarts with zoning off, or during commissioning | watchdog opens all vents 30 s after start |
| Commissioning script ends abnormally or runs over 75 min | watchdog stops it and opens all vents |
| Zoning switched off | all vents open (the interim Kids Bath Cap re-applies the bath vent cap 30 min later) |

**Known gap: if Home Assistant itself is down, none of the above runs.** The register vents stay where they were
last commanded; what they do on their own depends on their firmware (not included here). The minimum-open limits
are what keep that safe, so check your vents' own fail-safe behavior.

In the duct-damper controller firmware:

| Situation | What happens |
|---|---|
| ESP boots or reboots | `on_boot` drives all four DAC outputs to 0 V (= fully open) before anything else, and sets the HA sliders to 100 |
| Clean ESP reboot / OTA | `on_shutdown` drives all outputs to 0 V first (the GP8403 otherwise holds its last voltage) |
| Damper power lost | spring-return actuators open mechanically |
| HA or Wi-Fi lost | dampers hold their last position until ESPHome's API `reboot_timeout` (default 15 min, not changed here) reboots the ESP, and `on_boot` then opens them |

If you want the dampers to open immediately when HA disconnects, you could add an `api: on_client_disconnected:`
action that opens all four. Test that brief HA restarts don't cause unwanted cycling. I haven't made that change here.

## Setup notes
- Entity IDs: vents are `cover.kids_bath_vent`, `cover.kid1_vent`, `cover.kid2_vent`; room temps are `sensor.master_temp_hk`, `sensor.kid1_temp_hk`,
  `sensor.kid2_temp_hk`; the thermostat is `climate.upstairs_hk`.
- Helpers: every `input_number.hvac_*` limit, `input_boolean.hvac_zoning_active`, `hvac_commissioning_running`,
  `hvac_vents_physically_installed`, `hvac_day_sleep`, `hvac_evening_mode`, `hvac_fan_balance_running`,
  `hvac_safety_override`, `input_datetime.hvac_controller_heartbeat`, and `input_select.hvac_zoning_state` /
  `hvac_requested_zone`. The selects need the state/zone values that `hvac_zoning.jinja` returns
  (e.g. `HEATING`, `HVAC_OFF`, `MASTER_PRIORITY`, `SENSOR_FAILURE`, `PRESSURE_OVERRIDE`, `TEMPERATURE_OVERRIDE`,
  zones `NONE`, `MASTER`, `KID1`, `KID2`) plus `DISABLED`.
- Sensors: duct static pressure (raw and 30 s / 2 min / 5 min statistics sensors), supply/return air temps and a
  2-minute delta-T average, plus the Uptime integration (`sensor.uptime`) used by the watchdog.
- Leave `input_boolean.hvac_vents_physically_installed` **off** until the vents are actually installed; the
  zoning controller and commissioning won't move anything while it's off. (The interim "Kids Bath Cap" automation
  isn't gated by it and caps the bath vent whenever zoning is off.)
