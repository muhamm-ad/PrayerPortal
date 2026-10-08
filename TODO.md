## Future Enhancements

Listed by order of importance.

- [X] **Auto adjust time and location**: Add support for automatic adjustments based on location.

- [X] **Error Handling**: Implement robust error handling for connectivity issues, API failures, and other potential
  errors.
    - Failed requests are retried; a failed refresh keeps the previous data and is retried every 5 minutes.
    - Fatal errors are shown in the footer and logged, then the device reboots after 30 seconds.

- [X] **Mount Log Files to SD Card**: Mount log files to an SD card and configure a cleaning cycle for the log files to
  optimize memory usage.
    - Logs go to `/sd/PrayerPortal.log`, rotated at 64 KB with one backup (`.log.1`).

- [X] **Custom Adhan Audio**: Allow users to choose different Adhan recordings directly from the device interface.
    - Tap a prayer on the screen to select it, then tap the footer to cycle through the files in `/sd/adhans`.
      The choice is saved in `/sd/adhans.json`.

- [ ] **UI Improvements**:
    - Enhance the overall aesthetics and user experience on the screen.
    - Done: "Fajr" spelling, error/status messages in the footer, optional night dimming.

- [ ] **On-Device Wi-Fi Configuration**: Enable users to configure Wi-Fi settings directly from the device interface
  without needing to edit configuration files manually.
    - Not started: it needs an on-screen keyboard and a writable `settings.toml`, which is too heavy for the
      PyPortal's RAM for now.
