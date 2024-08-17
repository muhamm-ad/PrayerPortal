from os import getenv
import time

import adafruit_connection_manager
import adafruit_datetime
import adafruit_logging as logging
import adafruit_requests
import board
import busio
import rtc
import storage
from adafruit_esp32spi import adafruit_esp32spi
from digitalio import DigitalInOut

try:
    storage.remount(mount_path="/", readonly=False)
    mounted = True
except RuntimeError:
    mounted = False

# Set up logging
logger = logging.getLogger("PrayerPortal")
try:
    log_file = "/PrayerPortal.log"  # Log file path
    handler = logging.FileHandler(log_file)
except OSError:
    handler = logging.StreamHandler()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

if mounted:
    logger.info("Root filesystem mounted\n")
else:
    logger.warning("Failed to mount the root filesystem")

# Wi-Fi configuration
SECRETS = {
    "ssid": getenv("CIRCUITPY_WIFI_SSID"),
    "password": getenv("CIRCUITPY_WIFI_PASSWORD"),
}
if SECRETS["ssid"] is None or SECRETS["password"] is None:
    raise ValueError("Wi-Fi secrets are missing. Please add them in settings.py!")

# ESP32 SPI Configuration
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
pool = adafruit_connection_manager.get_radio_socketpool(esp)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
requests = adafruit_requests.Session(pool, ssl_context)


def connect_to_ap():
    logger.info(f"Connecting to Wi-Fi {SECRETS['ssid']} ...\n")
    try:
        esp.connect_AP(SECRETS["ssid"], SECRETS["password"])
    except OSError:
        logger.warning(f"Retrying connection to {SECRETS['ssid']}...\n")
        try:
            esp.connect_AP(SECRETS["ssid"], SECRETS["password"])
        except OSError as e2:
            logger.error(f"Failed to connect to {SECRETS['ssid']}: {e2}\n")
            raise
    logger.info(f"Connected to {esp.ap_info.ssid} with RSSI: {esp.ap_info.rssi}\n")
    # logger.info(f"My IP address is {esp.ipv4_address}\n")


def disconnect_from_ap():
    logger.info(f"Disconnecting from Wi-Fi {SECRETS['ssid']}...\n")
    try:
        esp.disconnect()
        logger.info("Disconnected from Wi-Fi successfully.\n")
    except Exception as e:
        logger.error(f"Failed to disconnect from Wi-Fi: {e}\n")
        raise

def fetch_and_set_rtc() -> adafruit_datetime.datetime:
    word_time_api_link = "http://worldtimeapi.org/api/ip"
    logger.info(f"Fetching time from {word_time_api_link}\n")

    try:
        response = requests.get(word_time_api_link)
        word_time_dict = response.json()
        response.close()

        # Parse the ISO time string
        iso_time_str = word_time_dict["datetime"][:-6]  # Remove timezone part
        parsed_time = adafruit_datetime.datetime.fromisoformat(iso_time_str)

        # Set the RTC
        rtc.RTC().datetime = parsed_time.timetuple()
        logger.info(f"RTC has been set to {parsed_time}\n")
        return parsed_time

    except Exception as e:
        logger.error(f"Error fetching or setting time: {e}\n")
        raise


def fetch_prayer_times():
    base_url = getenv("API_BASE_URL", "https://api.aladhan.com/v1/")
    country = getenv("COUNTRY", "Canada")
    state = getenv("STATE", "")
    city = getenv("CITY", "Montreal")
    method = getenv("CALCULATION_METHOD", 2)
    month = adafruit_datetime.datetime.now().month
    year = adafruit_datetime.datetime.now().year
    calendar_type = getenv("API_CALENDAR_TYPE", "calendarByCity")

    try:
        if state:
            logger.info(f"Fetching prayer times for {city}, {state}, {country} for {month}/{year} using method {method}\n")
            url = f"{base_url}{calendar_type}/{year}/{month}?country={country}&state={state}&city={city}&method={method}"
        else:
            logger.info(f"Fetching prayer times for {city}, {country} for {month}/{year} using method {method}\n")
            url = f"{base_url}{calendar_type}/{year}/{month}?country={country}&city={city}&method={method}"

        logger.info(f"URL: {url}\n")

        response = requests.get(url=url)
        data = response.json()
        response.close()
        logger.info("Prayer times fetched successfully!\n")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch prayer times: {e}\n")
        raise


connect_to_ap()
fetch_and_set_rtc()
prayer_time_dict = fetch_prayer_times()
disconnect_from_ap()

print("\n" * 5)
print("*" * 40)
while True:
    print(f"Current RTC time: {adafruit_datetime.datetime.now()}")
    time.sleep(1)
