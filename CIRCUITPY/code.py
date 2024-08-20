import time
from os import getenv
import gc

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
    logger.info("Root filesystem mounted ")
else:
    logger.warning("Failed to mount the root filesystem ")

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

esp : adafruit_esp32spi.ESP_SPIcontrol
requests : adafruit_requests.Session

def connect_to_wifi():
    global esp, requests

    esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
    pool = adafruit_connection_manager.get_radio_socketpool(esp)
    ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)

    requests = adafruit_requests.Session(pool, ssl_context)
    if not esp.connected:
        logger.info(f"Connecting to Wi-Fi {SECRETS['ssid']} ... ")
        try:
            esp.connect_AP(SECRETS["ssid"], SECRETS["password"])
        except OSError:
            logger.warning(f"Retrying connection to {SECRETS['ssid']} ... ")
            try:
                esp.connect_AP(SECRETS["ssid"], SECRETS["password"])
            except OSError as e2:
                logger.error(f"Failed to connect to {SECRETS['ssid']}: {e2} ")
                raise
        logger.info(f"Connected to {esp.ap_info.ssid} with RSSI: {esp.ap_info.rssi} ")
        # logger.info(f"My IP address is {esp.ipv4_address} ")


def disconnect_from_wifi():
    global esp, requests
    if esp.connected:
        logger.info(f"Disconnecting from Wi-Fi {SECRETS['ssid']} ... ")
        try:
            esp.disconnect()
            logger.info("Disconnected from Wi-Fi successfully ")
        except Exception as e:
            logger.error(f"Failed to disconnect from Wi-Fi: {e} ")
            raise


def fetch_and_set_rtc() -> adafruit_datetime.datetime:
    word_time_api_link = "http://worldtimeapi.org/api/ip"
    logger.info(f"Fetching time from {word_time_api_link} ")

    try:
        response = requests.get(word_time_api_link)
        word_time_dict = response.json()
        response.close()

        # Parse the ISO time string
        iso_time_str = word_time_dict["datetime"][:-6]  # Remove timezone part
        parsed_time = adafruit_datetime.datetime.fromisoformat(iso_time_str)

        # Set the RTC
        rtc.RTC().datetime = parsed_time.timetuple()
        logger.info(f"RTC has been set to {parsed_time} ")
        return parsed_time

    except Exception as e:
        logger.error(f"Error fetching or setting time: {e} ")
        raise


def fetch_prayer_times(date: adafruit_datetime.date = None):
    if date is None:
        date = adafruit_datetime.datetime.now().date()

    base_url = getenv("API_BASE_URL", "https://api.aladhan.com/v1/")
    country = getenv("COUNTRY", "Canada")
    state = getenv("STATE", "")
    city = getenv("CITY", "Montreal")
    method = getenv("CALCULATION_METHOD", 2)
    month = date.month
    year = date.year
    calendar_type = getenv("API_CALENDAR_TYPE", "calendarByCity")

    try:
        logger.info(
            f"Fetching prayer times for {city},{(' ' + state + ',') if state else ''} {country} for {month}/{year} using method {method} ")
        url = f"{base_url}{calendar_type}/{year}/{month}?country={country}&city={city}&method={method}"

        if state:
            url += f"&state={state}"

        logger.info(f"URL: {url} ")

        response = requests.get(url=url)
        data = response.json()
        response.close()
        logger.info("Prayer times fetched successfully! ")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch prayer times: {e} ")
        raise


def get_day_timings(data, date):
    if data is not None:
        for day_data in data['data']:
            day_date = day_data['date']['gregorian']
            api_date = adafruit_datetime.date(
                year=int(day_date['year']),
                month=int(day_date['month']['number']),
                day=int(day_date['day'])
            )
            if api_date == date:
                return day_data['timings']

    logger.warning("No timings found for the current day ")
    return None


def get_next_prayer(timings, time : adafruit_datetime.time = None):
    if timings is not None:
        if time is None:
            time = adafruit_datetime.datetime.now().time()

        for next_p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            t = timings[next_p].split(' ')[0].split(':')
            next_p_time = adafruit_datetime.time(hour=int(t[0]), minute=int(t[1]))

            if next_p_time > time:
                return next_p, next_p_time

    return None, None


def get_next_day(date_obj: adafruit_datetime.date):
    """
    Returns the next day, taking into account month and year changes.
    """
    if date_obj.month == 2:  # Handle February and leap years
        if (date_obj.year % 4 == 0 and date_obj.year % 100 != 0) or (date_obj.year % 400 == 0):
            days_in_month = 29
        else:
            days_in_month = 28
    elif date_obj.month in [4, 6, 9, 11]:  # Handle months with 30 days
        days_in_month = 30
    else:  # Handle months with 31 days
        days_in_month = 31

    # Check if it's the last day of the month
    if date_obj.day < days_in_month:
        return adafruit_datetime.date(year=date_obj.year, month=date_obj.month, day=date_obj.day + 1)
    else:
        if date_obj.month == 12:  # December, transition to next year
            return adafruit_datetime.date(year=date_obj.year + 1, month=1, day=1)
        else:
            return adafruit_datetime.date(year=date_obj.year, month=date_obj.month + 1, day=1)


#######################################################################################################################

connect_to_wifi()
fetch_and_set_rtc()
today_date = adafruit_datetime.datetime.now().date()
prayer_dict = fetch_prayer_times(today_date)
disconnect_from_wifi()

today_timings = None
next_prayer = None
next_prayer_time = None
start = True
all_prayers_passed = False

while True:
    if today_timings is None:
        today_timings = get_day_timings(prayer_dict, today_date)
        if today_timings is not None :
            if start:
                start = False
                logger.info("Today's Prayer Times: ")
            else:
                logger.info("Tomorrow's Prayer Times: ")

            for p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
                logger.info(f"{p}: {today_timings[p]}{', ' if p != 'Isha' else ''} ")

    if all_prayers_passed:
        all_prayers_passed = False
        ct = adafruit_datetime.time(hour=00, minute=00, second=00)
    else:
        ct = adafruit_datetime.datetime.now().time()

    new_next_prayer, new_next_prayer_time = get_next_prayer(timings=today_timings, time=ct)
    if (next_prayer_time is None) or (new_next_prayer_time != next_prayer_time):
        if next_prayer_time is not None:
            logger.info(f"{next_prayer} ({next_prayer_time}) has passed. Updating the next prayer time ... ")

        next_prayer = new_next_prayer
        next_prayer_time = new_next_prayer_time

        if next_prayer_time is not None:
            logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
            logger.info(f"Next prayer is {next_prayer} at {next_prayer_time} ")
        else:
            logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
            logger.info(f"All prayers for today {adafruit_datetime.datetime.now().date()} have passed. ")
            all_prayers_passed = True

            today_date = get_next_day(today_date)
            logger.info(f"Tomorrow is {today_date}. ")

            if today_date.day == 1:
                logger.warning("End of the month detected. ")
                connect_to_wifi()
                logger.info(f"Free memory: {gc.mem_free()} bytes ")
                logger.info("Deleting prayer_dict ...")
                del prayer_dict
                gc.collect()
                logger.info(f"Free memory: {gc.mem_free()} bytes ")
                prayer_dict = fetch_prayer_times(today_date)
                logger.info(f"Free memory: {gc.mem_free()} bytes ")
                disconnect_from_wifi()

            today_timings = None

    if next_prayer_time is not None:
        current_time = adafruit_datetime.datetime.now().time()
        one_day_in_seconds = 60 * 60 * 24

        if (next_prayer == 'Fajr') and (current_time > next_prayer_time):
            # Calculate the time until Fajr, considering it's the next day
            section1 = one_day_in_seconds - (current_time.hour * 60 + current_time.minute) * 60 - current_time.second
            section2 = (next_prayer_time.hour * 60 + next_prayer_time.minute) * 60
            time_until_next_prayer = section1 + section2
        else:
            # Calculate time until the next prayer within the same day
            time_until_next_prayer = (next_prayer_time.hour * 60 + next_prayer_time.minute) * 60 - \
                                     (current_time.hour * 60 + current_time.minute) * 60 - current_time.second

        logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
        logger.info(f"Time until next prayer: {time_until_next_prayer} seconds ")
        time.sleep(time_until_next_prayer)
