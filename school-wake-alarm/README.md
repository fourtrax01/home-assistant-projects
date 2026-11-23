# School-day wake-up alarm

On school days, at a time set by an `input_datetime`, it plays calm tracks from the Music Assistant library on the
kid's speaker (in a new random order every morning), raises the volume slowly and fades the bedroom lights up.
If the library playback doesn't start within 20 s, it falls back to a Pandora station through the Google Assistant SDK.

The useful part is the **sick-day skip**: a "Skip next alarm" toggle skips one alarm and then re-arms itself.
A skip that's more than 24 h old (or set before the weekend, for Monday) is treated as stale and cleared,
so a forgotten toggle never silently kills the alarm. Parents get a notification saying which alarm will be skipped and who pressed it.

## Files
- `automations.yaml`: the alarm (with the skip rules) and the parent notification
- `scripts.yaml`: `kid1_wake_up` (music, volume ramp, light fade) and `kid1_wake_up_shuffle` (picks the next morning's order)
- `custom_templates/district.jinja`: the school calendar (first/last day and no-school dates) plus two macros.
  **The dates are examples.** Replace them with your district's calendar each summer, then run `homeassistant.reload_custom_templates`.

## Setup
1. Copy `district.jinja` to `/config/custom_templates/`.
2. Create the helpers:
   - `input_datetime.kid1_wakeup_time` (time only), `input_boolean.kid1_skip_next_alarm`, `input_text.kid1_wake_up_song_order`
   - Template binary sensor `binary_sensor.district_school_day`:
     `{% from 'district.jinja' import district_is_school_day %}{{ district_is_school_day(now().date()) }}`
   - Optional template sensor `sensor.kid1_next_alarm` (device class timestamp):
     `{% from 'district.jinja' import district_next_alarm %}{{ district_next_alarm(states('input_datetime.kid1_wakeup_time'), 1 if is_state('input_boolean.kid1_skip_next_alarm', 'on') else 0) }}`
3. Edit `scripts.yaml`: the speaker entities (`media_player.kid1_bedroom_speaker` is the Cast entity used for
   volume, `media_player.kid1_speaker` the Music Assistant player), the light, and the `library://track/N` IDs
   (find them in Music Assistant). The Pandora fallback needs the Google Assistant SDK integration.
4. In `automations.yaml`, replace the `person_user_id_N` keys with your HA user IDs and the notify services with yours.

Note: the start check waits until the speaker *is* playing, not for it to *start* playing. Music Assistant's
`play_media` call can return after the speaker is already playing, and an earlier "wait for it to start" version
missed that and fell back to Pandora every morning.
