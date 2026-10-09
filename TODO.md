# Future Enhancements

Listed by order of importance.

- [X] **Auto adjust time and location**: Add support for automatic adjustments based on location.

- [X] **Error Handling**: Implement robust error handling for connectivity issues, API failures, and other potential errors.
  - Failed requests are retried; a failed refresh keeps the previous data and is retried every 5 minutes.
  - Fatal errors are shown in the terminal on the screen and logged, then the device reboots after 30 seconds.

- [X] **Mount Log Files to SD Card**: Mount log files to an SD card and configure a cleaning cycle for the log files to optimize memory usage.
  - Logs go to [`/sd/PrayerPortal.log`](sd/PrayerPortal.log), rotated at 64 KB with one backup ([`PrayerPortal.log.1`](sd/PrayerPortal.log.1)).

- [X] **Custom Adhan Audio**: Allow users to choose different Adhan recordings directly from the device interface.
  - Tap a prayer on the screen to select it, then tap the footer to cycle through the files in [`/sd/adhans`](sd/adhans). The choice is saved in [`/sd/adhans.json`](sd/adhans.json).

- [ ] **Audio Settings**: Add a volume section opened by tapping the speaker icon (bottom right of the screen).
  - Buttons: volume **−**, volume **+** and **mute**, with the current level shown and the icon changed when muted.
  - Save the level in `/sd/audio.json` and play a short beep when it changes.
  - `audioio.AudioOut` has no volume control: play the WAV through `audiomixer.Mixer` (voice `level` from 0.0 to 1.0, mute = 0). It needs a small audio buffer in RAM.

- [ ] **Offline Prayer Times**: Keep working when the Aladhan API cannot be reached at boot.
  - Save the fetched days in `/sd/times.json` and reuse the last known times (they move by only a minute or two per day) until the API answers again.
  - The clock still needs Wi-Fi at boot: the PyPortal has no battery for its RTC.

- [ ] **Faster Screen Drawing**: Convert `bg*.bmp` and `template.bmp` to 8-bit indexed BMP files.
  - The backgrounds are read from the SD card each time a screen area is redrawn. At 614 KB each (32-bit) they are slow; 8-bit files are about 4 times smaller, so redraws and the boot are faster and there are fewer SD/SPI clashes.
  - Check the transparent colour of `template.bmp` after the conversion.

- [ ] **UI Improvements**:
  - Enhance the overall aesthetics and user experience on the screen.
  - Done: "Fajr" spelling, error/status messages in the footer, optional night dimming, touch highlight (selected prayer outlined, footer flash), unused settings icon removed.
  - Outline the tile of the next prayer.
  - Make the Wi-Fi icon show the connection state (hidden or dimmed when offline).
  - Switch the Hijri date at Maghrib (the Hijri day starts at sunset).
  - Show the sunrise time (end of Fajr).

- [ ] **Per-Prayer Adhan Options**: Silence the Adhan for chosen prayers (for example Fajr at night) and preview an Adhan with a long press on the footer.

- [ ] **On-Device Wi-Fi Configuration**: Enable users to configure Wi-Fi settings directly from the device interface without needing to edit configuration files manually.
  - Not started: it needs an on-screen keyboard and a writable `settings.toml`, which is too heavy for the PyPortal's RAM for now.

- [ ] **Tests in CI**: Run `python3 -I -m unittest discover -s tests` on every pull request with GitHub Actions.
