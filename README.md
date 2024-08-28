# PrayerPortal

**PrayerPortal** uses the Adafruit PyPortal Titano to automatically fetch Muslim prayer times via Wi-Fi, display them on
the device's screen, and play the Adhan (Islamic call to prayer) at the appropriate times.

## Features

- **Automatic Prayer Times Fetching**: Connects to the internet to retrieve accurate prayer times for your location.
- **Adhan Alert**: Plays the Adhan at each prayer time.
- **Prayer Times Display**: Shows the current time and all daily prayer times on the screen.
- **Customizable Location**: Easily set your location for precise prayer times.

## Hardware Required

- [Adafruit PyPortal Titano](https://learn.adafruit.com/adafruit-pyportal-titano)
- Micro USB cable
- Wi-Fi connection
- SD card (less than 32 GB)

## Software Required

- Python 3.x
- [Circup](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup/overview)

[//]: # (## Required Libraries)

[//]: # ()
[//]: # (- [Adafruit CircuitPython PyPortal]&#40;https://github.com/adafruit/Adafruit_CircuitPython_PyPortal&#41;)

## Setup Instructions

1. **Install CircuitPython**:
   Follow [Adafruit's guide](https://learn.adafruit.com/adafruit-pyportal-titano/circuitpython) to install CircuitPython
   on the PyPortal Titano.

2. **Configure Settings**:
   In the [settings.toml](CIRCUITPY/settings.toml) file, update:
   
    - **Wi-Fi**: Your Wi-Fi credentials.
    - **Location**: Set your geographic location.

3. **Install Required Libraries**:
   
   Install the necessary CircuitPython libraries by running the following command in the [root of this project](./):
   
   ```cli
   circup --path ./CIRCUITPY/ install --auto
   ```

4. **Upload Code**: 
- Copy the content of the sd directory into your SD card.
- Upload the `content` of the [CIRCUITPY](CIRCUITPY) directory to the PyPortal Titano: 
    - By drag and drop.
    - Or using the sync scripts :
       - Run the script from your terminal on Linux/macOS with `./sync.sh push` to upload all the `content` of the [CIRCUITPY](CIRCUITPY) directory.
       - Run the script from the Windows Command Prompt with `sync.bat push` to upload all the `content` of the [CIRCUITPY](CIRCUITPY) directory.

5. **Run the Program**: Power on the PyPortal Titano, and it will automatically connect to Wi-Fi, fetch the prayer
   times, and display them on the screen.

## How It Works

1. **Wi-Fi Connection**: The PyPortal Titano connects to the internet using your Wi-Fi credentials.
2. **Fetching Prayer Times**: The device requests prayer times from the [Aladhan API](https://api.aladhan.com/) based on
   your location.
3. **Displaying Times**: The screen displays the prayer times for the day, updated regularly.
4. **Playing Adhan**: The Adhan is played at each prayer time through the built-in speaker or a connected speaker.

## Future Enhancements

- **Custom Adhan Audio**: Allow users to choose different Adhan recordings from the SD card.
- **Multiple Locations**: Add support for selecting different locations directly on the device.
- **UI Improvements**: Enhance the graphical display with additional features like a countdown to the next prayer.
- **On-Device Wi-Fi Configuration**: Enable users to set up Wi-Fi credentials directly on the device without needing to
  modify the `settings.toml` file.

## Contribution

Contributions are welcome! Fork the repository and submit a pull request with your changes.

## License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
