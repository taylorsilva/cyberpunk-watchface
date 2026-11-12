# Cyberpunk Watchface

A Pebble Time 2 watchface inspired by the Cyberpunk 2077 video game.

![Render of the watchface](./screenshot_default.png)
![Render of the watchface with the charging and disconnected icons](./screenshot_charging_disconnected.png)

There are three cards that can be displayed. Current display options are:

- Steps
- Heart rate
- Current temperature and dominant weather condition of the day
- UV index

Other features:
- 12h or 24h Time format selection
- Celsius or Fahrenheit temperature selection
- Watch or phone battery selection for the progress bar
- Battery percentage is displayed in the bottom right and a progress bar is visible along the bottom
- Vibrate and display an icon to the right of the date if the watch is disconnected from the phone
- Display an icon to the left of the date when the watch is charging

The percentage always shows the watch battery. The progress bar shows the watch
battery by default, or the phone battery when selected. When the phone battery is
above 40% the bar is cyan to match the other accents; at 40% and below it turns
red. Phone battery readings use `navigator.getBattery()`, which the Android Pebble
app exposes but the iOS Pebble app does not. Until the first phone reading arrives,
and whenever the watch is disconnected, the bar falls back to the watch battery and
stays red.

![Render of the watchface showing the phone battery bar](./screenshot_phone_battery.png)

## Build and run

```sh
pebble build
pebble install --emulator emery --vnc
pebble screenshot --emulator emery --vnc --no-open screenshot_emery.png
```

`--vnc` is required in headless environments. The bundled output is
`build/pebble-cyberpunk-watchface.pbw`.

---

All icons are from: https://github.com/pebble-dev/iconography
