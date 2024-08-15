# PrayerPortal

**PrayerPortal** uses the Adafruit PyPortal Titano to automatically fetch Muslim prayer times via Wi-Fi, display them on the device's screen, and play the Adhan (Islamic call to prayer) at the appropriate times.

## Features
- **Automatic Prayer Times Fetching**: Connects to the internet to retrieve accurate prayer times for your location.
- **Adhan Alert**: Plays the Adhan at each prayer time.
- **Prayer Times Display**: Shows the current time and all daily prayer times on the screen.
- **Customizable Location**: Easily set your location for precise prayer times.

## Hardware Required
- [Adafruit PyPortal Titano](https://learn.adafruit.com/adafruit-pyportal-titano)
- Micro USB cable
- Wi-Fi connection

## Software Required
- Python 3.x
- CircuitPython Libraries for PyPortal Titano

## Required Libraries
- [Adafruit CircuitPython PyPortal](https://github.com/adafruit/Adafruit_CircuitPython_PyPortal)
- Python `json` library

## Setup Instructions
1. **Install CircuitPython**: Follow [Adafruit's guide](https://learn.adafruit.com/adafruit-pyportal-titano/circuitpython) to install CircuitPython on the PyPortal Titano.
2. **Install Required Libraries**: Download the necessary CircuitPython libraries and copy them to the `lib` folder on your PyPortal Titano.
3. **Configure Settings**:
   - **Wi-Fi**: Update your Wi-Fi credentials in the [settings.toml](settings.toml) file.
   - **Location**: Set your geographic location in the `settings.toml` file to fetch accurate prayer times.
4. **Upload Code**: Upload the `src` directory to the PyPortal Titano.
5. **Run the Program**: Power on the PyPortal Titano, and it will automatically connect to Wi-Fi, fetch the prayer times, and display them on the screen.

## How It Works
1. **Wi-Fi Connection**: The PyPortal Titano connects to the internet using your Wi-Fi credentials.
2. **Fetching Prayer Times**: The device requests prayer times from the [Aladhan API](https://api.aladhan.com/) based on your location.
3. **Displaying Times**: The screen displays the prayer times for the day, updated regularly.
4. **Playing Adhan**: The Adhan is played at each prayer time through the built-in speaker or a connected speaker.

## Future Enhancements
- **Custom Adhan Audio**: Allow users to choose different Adhan recordings from the SD card.
- **Multiple Locations**: Add support for selecting different locations directly on the device.
- **UI Improvements**: Enhance the graphical display with additional features like a countdown to the next prayer.
- **On-Device Wi-Fi Configuration**: Enable users to set up Wi-Fi credentials directly on the device without needing to modify the `settings.toml` file.

## Contribution
Contributions are welcome! Fork the repository and submit a pull request with your changes.

## License
This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
