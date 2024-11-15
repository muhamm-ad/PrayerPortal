# PrayerPortal

**PrayerPortal** uses the Adafruit PyPortal Titano to automatically fetch Muslim prayer times via Wi-Fi, display them on
the device's screen, and play the Adhan (Islamic call to prayer) at the appropriate times.

<p align="center">
  <img src="PrayerPortal.png" title="" alt="exemple" width="65%">
</p>

## Features

- **Automatic Prayer Times Fetching**: Connects to the internet to retrieve accurate prayer times for your location.
- **Prayer Times Display**: Shows the current time and all daily prayer times on the screen.
- **Adhan Alert**: Plays the Adhan at each prayer time.

## Hardware Required

- [Adafruit PyPortal Titano](https://learn.adafruit.com/adafruit-pyportal-titano)
- Micro USB cable
- Wi-Fi connection
- SD card ( < 32GB & > 1GB )

## Software Required

- [Circup](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup/overview)

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
   circup --path ./CIRCUITPY/ install adafruit-circuitpython-sd
   circup --path ./sd/ install -r requirements.txt
   ```

4. **Upload Code**:
    - Copy the content of the sd directory into your SD card.
    - Upload the `content` of the [CIRCUITPY](CIRCUITPY) directory to the PyPortal Titano.
5. **Run the Program**: Power on the PyPortal Titano, and it will automatically connect to Wi-Fi, fetch the prayer
   times, and display them on the screen.

## How It Works

1. **Wi-Fi Connection**: The PyPortal Titano connects to the internet using your Wi-Fi credentials.
2. **Fetching Prayer Times**: The device requests prayer times from the [Aladhan API](https://api.aladhan.com/) based on
   your location.
3. **Displaying Times**: The screen displays the prayer times for the day, updated regularly.
4. **Playing Adhan**: The Adhan is played `5 min` before each prayer time through the built-in speaker or a connected
   speaker.

## License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
