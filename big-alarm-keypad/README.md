# big-alarm-keypad

A Lovelace card with big square buttons for `alarm_control_panel` entities, made for wall tablets.

```yaml
type: custom:big-alarm-keypad
entity: alarm_control_panel.alarm
states: [arm_home, arm_away]
code_length: 4   # optional
```
Install: copy `big-alarm-keypad.js` to `/config/www/`, then add `/local/big-alarm-keypad.js` as a dashboard resource (JavaScript module).
The code you type lives only in the browser tab and is sent once with the service call.
