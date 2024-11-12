import time
from gc import collect as clean_memory, mem_free
from os import getenv

import displayio
import rtc
import board
from storage import remount
from digitalio import DigitalInOut
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label
from micropython import const
from adafruit_pyportal.graphics import Graphics
from adafruit_pyportal import Peripherals
from adafruit_esp32spi.adafruit_esp32spi import ESP_SPIcontrol
from adafruit_connection_manager import get_radio_socketpool, get_radio_ssl_context
from adafruit_datetime import date as adafruit_date, datetime as adafruit_datetime, time as adafruit_time
from adafruit_logging import FileHandler, INFO, StreamHandler, getLogger
from adafruit_requests import Session
# import adafruit_touchscreen

clean_memory()
print("\n*******************************")
print(f"** Free memory: {mem_free()} **")
print("*******************************\n")

esp: ESP_SPIcontrol = ESP_SPIcontrol(
        board.SPI(),
        DigitalInOut(board.ESP_CS),
        DigitalInOut(board.ESP_BUSY),
        DigitalInOut(board.ESP_RESET)
)

graphics = Graphics(
        # default_bg="/sd/images/loading.bmp",
        debug=True,
)

try:
    remount(mount_path="/", readonly=False)
    mounted = True
except RuntimeError:
    mounted = False

# Set up logging
logger = getLogger("PrayerPortal")
try:
    log_file = "/PrayerPortal.log"  # Log file path
    handler = FileHandler(log_file)
except OSError:
    handler = StreamHandler()
logger.setLevel(INFO)
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
    # TODO Show error on screen
    raise ValueError("Wi-Fi secrets are missing. Please add them in settings.py!")

RETRIES_DELAY = const(10)
MAX_RETRIES = const(3)

def connect_to_wifi():
    global esp
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
        clean_memory()
        # logger.info(f"My IP address is {esp.ipv4_address} ")

def disconnect_from_wifi():
    global esp
    if esp.connected:
        logger.info(f"Disconnecting from Wi-Fi {SECRETS['ssid']} ... ")
        try:
            esp.disconnect()
            clean_memory()
            logger.info("Disconnected from Wi-Fi successfully ")
        except Exception as e:
            logger.error(f"Failed to disconnect from Wi-Fi: {e} ")
            raise

def fetch_and_set_rtc():
    requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
    api_url = "https://api.coindesk.com/v1/bpi/currentprice/USD.json"
    logger.info(f"Fetching time from {api_url} ...")
    response = None
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            response = requests.get(url=api_url, stream=True)
            respond_json = response.json()
            response.close()
            del response
            del requests
            # Parse the ISO time string from the CoinDesk API
            iso_time_str = respond_json["time"]["updatedISO"]
            # Parse the datetime
            parsed_time = adafruit_datetime.fromisoformat(iso_time_str)
            # Set the RTC
            rtc.RTC().datetime = parsed_time.timetuple()
            logger.info(f"RTC has been set to {parsed_time} ")

            clean_memory()
            return parsed_time
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to fetch and set RTC: {e} ")
                raise
            else:
                logger.warning("Failed to fetch and set RTC, retrying ... ")
                if response:
                    response.close()
                    del response
                del requests
                time.sleep(RETRIES_DELAY * retry_count)
                requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
                clean_memory()

def fetch_location():
    requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
    api_url = "http://ip-api.com/json/"
    logger.info(f"Fetching location from {api_url} ...")
    response = None
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            response = requests.get(url=api_url, stream=True)
            respond_json = response.json()
            response.close()
            del response
            del requests
            logger.info(f"Location is fetched successfully")

            clean_memory()
            return respond_json["country"], respond_json["city"]
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to fetch location: {e} ")
                raise
            else:
                logger.warning("Failed to fetch location, retrying ... ")
                if response:
                    response.close()
                    del response
                del requests
                time.sleep(RETRIES_DELAY * retry_count)
                requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
                clean_memory()


def construct_prayer_times_url(date, city, country, state):
    adhans_api_base_url = "https://api.aladhan.com/v1/"
    methode = getenv("CALCULATION_METHOD", 2)

    url = f"{adhans_api_base_url}timingsByCity?date={date.day}-{date.month}-{date.year}&country={country}&city={city}&method={methode}"
    if state:
        url += f"&state={state}"

    logger.info(
            f"Fetching prayer times for {city},{(' ' + state + ',') if state else ''} {country} for {date} using method {methode} "
    )
    logger.info(f"URL: {url}")
    clean_memory()
    return url

def try_fetch_prayer_times(url):
    requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
    retry_count = 0
    response = None
    while retry_count < MAX_RETRIES:
        try:
            logger.info(f"Attempting to fetch prayer times ...")
            clean_memory()
            response = requests.get(url=url, stream=True)
            response_json = response.json()
            response.close()
            del response
            del requests

            logger.info("Prayer times fetched successfully!")
            clean_memory()
            return response_json
        except Exception as e:
            retry_count += 1

            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to fetch prayer times: {e}")
                raise
            else:
                logger.warning("Failed to fetch prayer times, retrying...")
                if response:
                    response.close()
                    del response
                del requests
                time.sleep(RETRIES_DELAY*retry_count)
                requests = Session(socket_pool=get_radio_socketpool(esp), ssl_context=get_radio_ssl_context(esp))
                clean_memory()

def fetch_prayer_times(date: adafruit_date = None,
                       city: str = getenv("CITY", "Montreal"),
                       country: str = getenv("COUNTRY", "Canada"),
                       state: str = getenv("STATE", ""),
                       ):
    if date is None:
        date = adafruit_datetime.now().date()
    url = construct_prayer_times_url(date=date, city=city, country=country, state=state)
    return try_fetch_prayer_times(url)

clean_memory()

connect_to_wifi()
fetch_and_set_rtc()
current_ip_country, current_ip_city = fetch_location()
prayers_date = today_date = adafruit_datetime.now().date()
today_data = fetch_prayer_times(date=prayers_date, country=current_ip_country, city=current_ip_city)

clean_memory()
print("\n************************")
print(f"** Free memory: {mem_free()} **")
print("************************\n")

# ------------- Constantes ------------- #
SCREEN_WIDTH = const(480)
SCREEN_HEIGHT = const(320)
WHITE = const(0xFFFFFF)
BLACK = const(0x000000)

# Fonts
FONT_16 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-16.bdf")
FONT_16.load_glyphs(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :")

FONT_24 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-24-AlphaNum.bdf")
FONT_24.load_glyphs(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :")

FONT_48 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-48-CurrentTime.bdf")
FONT_48.load_glyphs(b"0123456789:")

# Adhans
ADHAN_MINUTES_BEFORE_PRAYER = const(5)
ADHANS = {
    "Fajr": {
        "file": "/sd/adhans/AhmadAlNafees.wav",
        "name": "Ahmad Al Nafees"
    },
    "Dhuhr": {
        "file": "/sd/adhans/HafizMustafaOzcan.wav",
        "name": "Hafiz Mustafa Ozcan"
    },
    "Asr": {
        "file": "/sd/adhans/MasjidAlHaramMecca.wav",
        "name": "Masjid Al Haram Mecca"
    },
    "Maghrib": {
        "file": "/sd/adhans/MisharyRashidAlafasy.wav",
        "name": "Mishary Rashid Alafasy"
    },
    "Isha": {
        "file": "/sd/adhans/QariAbdulKareem.wav",
        "name": "Qari Abdul Kareem"
    }
}

# ------------- Functions ------------- #

def set_image(group, filename):
    """Set the image file for a given goup for display.
    This is most useful for Icons or image slideshows.
        :param group: The chosen group
        :param filename: The filename of the chosen image
    """
    print("Set image ", filename)
    if group:
        group.pop()

    if not filename:
        return  # we're done, no icon desired

    image_file = open(filename, "rb")
    image = displayio.OnDiskBitmap(image_file)
    image.pixel_shader.make_transparent(0)
    image_sprite = displayio.TileGrid(image, pixel_shader=image.pixel_shader)

    group.append(image_sprite)

def get_str_time(the_time):
    return f"{the_time.hour:02}:{the_time.minute:02}"


def get_hijri_str_month(month_number):
    months = {
        1: "Muharram",
        2: "Safar",
        3: "Rabi' al-awwal",
        4: "Rabi' al-thani",
        5: "Jumada al-awwal",
        6: "Jumada al-thani",
        7: "Rajab",
        8: "Sha'ban",
        9: "Ramadan",
        10: "Shawwal",
        11: "Dhu al-Qi'dah",
        12: "Dhu al-Hijjah"
    }
    return months[month_number]

def get_str_date(data):
    today_gregorian_dict = data['data']['date']['gregorian']
    today_gregorian = today_gregorian_dict['day'] + ' ' + today_gregorian_dict['month']['en'] + ' ' + \
                      today_gregorian_dict['year']
    today_hijiri_dict = data['data']['date']['hijri']
    today_hijiri = today_hijiri_dict['day'] + ' ' + get_hijri_str_month(today_hijiri_dict['month']['number']) + ' ' + \
                   today_hijiri_dict['year']
    return today_gregorian, today_hijiri

def get_day_timings(data, date):
    if data is not None:
        day_date = data['date']['gregorian']
        api_date = adafruit_date(
                year=int(day_date['year']),
                month=int(day_date['month']['number']),
                day=int(day_date['day'])
        )
        if api_date == date:
            return data['timings']
    return None

def get_next_prayer(timings, current_t: adafruit_time = None):
    if timings is not None:
        if current_t is None:
            current_t = adafruit_datetime.now().time()

        for next_p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            t = timings[next_p].split(' ')[0].split(':')
            next_p_time = adafruit_time(hour=int(t[0]), minute=int(t[1]))

            if next_p_time > current_t:
                return next_p, next_p_time

    return None, None

def get_next_day(date_obj: adafruit_date):
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
        return adafruit_date(year=date_obj.year, month=date_obj.month, day=date_obj.day + 1)
    else:
        if date_obj.month == 12:  # December, transition to next year
            return adafruit_date(year=date_obj.year + 1, month=1, day=1)
        else:
            return adafruit_date(year=date_obj.year, month=date_obj.month + 1, day=1)

# ------------- Inits ------------- #

clean_memory()
print("\n************************")
print(f"** Free memory: {mem_free()} **")
print("************************\n")

display = board.DISPLAY
display.rotation = 0

# Initializes the display touch screen area
# ts = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
#                                       board.TOUCH_YD, board.TOUCH_YU,
#                                       calibration=((5200, 59000), (5800, 57000)),
#                                       size=(SCREEN_WIDTH, SCREEN_HEIGHT))

splash = displayio.Group(scale=1, x=0, y=0)

clean_memory()

# Set general back ground
bg_group = displayio.Group(scale=1, x=0, y=0)
set_image(bg_group, "/sd/images/bg1.bmp")
splash.append(bg_group)

# Set template
template_group = displayio.Group(scale=1, x=0, y=0)
set_image(template_group, "/sd/images/template.bmp")
splash.append(template_group)

clean_memory()

# Initialize the prayer time labels
prayer_time_labels = {}
for i, prayer in enumerate(["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]):
    # Create the time label
    pt_label = Label(y=71, font=FONT_16, color=WHITE)
    splash.append(pt_label)
    prayer_time_labels[prayer] = pt_label  # Store the time label for later updates

clean_memory()

# Initialize current time label
ct_label = Label(y=151, font=FONT_48, text=get_str_time(adafruit_datetime.now().time()), color=WHITE)
ct_label.x = (240 - ct_label.bounding_box[2]) // 2
splash.append(ct_label)

clean_memory()

# Initialize current date labels
today_str_gregorian, today_str_hijiri = get_str_date(today_data)
cd_gregorian_label = Label(y=242, font=FONT_16, text=today_str_gregorian, color=WHITE)
cd_hijri_label = Label(y=274, font=FONT_16, text=today_str_hijiri, color=WHITE)
cd_gregorian_label.x = (240 - cd_gregorian_label.bounding_box[2]) // 2
cd_hijri_label.x = (240 - cd_hijri_label.bounding_box[2]) // 2
splash.append(cd_gregorian_label)
splash.append(cd_hijri_label)

clean_memory()

# Initialize next prayer labels
np_name_label = Label(y=127, font=FONT_24, color=WHITE)
np_adhan_label = Label(y=198, font=FONT_24, color=WHITE)
np_countdown_label = Label(y=269, font=FONT_24, color=WHITE)
splash.append(np_name_label)
splash.append(np_adhan_label)
splash.append(np_countdown_label)

clean_memory()

# Initialize footer adhan label
footer_adhan_label = Label(y=307, font=FONT_16, color=WHITE)
splash.append(footer_adhan_label)

clean_memory()

print("\n************************")
print(f"** Free memory: {mem_free()} **")
print("************************\n")

# ------------- Run ------------- #

today_timings = None
next_prayer = None
next_prayer_time = None
next_adhan_time = None
start = True
all_prayers_passed = False
localtile_refresh = time.monotonic()

# Set the splash screen as the root group for display
board.DISPLAY.root_group = splash

clean_memory()
while True:
    # only query the online time once per hour (and on first run)
    if (time.monotonic() - localtile_refresh) > 3600:
        fetch_and_set_rtc()
        localtile_refresh = time.monotonic()

    # update time label
    ct_label.text = get_str_time(adafruit_datetime.now().time())
    ct_label.x = (240 - ct_label.bounding_box[2]) // 2

    # update date label
    if today_date != adafruit_datetime.now().date():
        today_date = adafruit_datetime.now().date()
        today_gregorian, today_hijiri = get_str_date(today_data)
        cd_gregorian_label.text = today_gregorian
        cd_gregorian_label.x = (240 - cd_gregorian_label.bounding_box[2]) // 2
        cd_hijri_label.text = today_hijiri
        cd_hijri_label.x = (240 - cd_hijri_label.bounding_box[2]) // 2

    clean_memory()
    if today_timings is None:
        today_timings = get_day_timings(today_data['data'], prayers_date)
        if today_timings is not None:
            if start:
                start = False
                logger.info("Today's Prayer Times: ")
            else:
                logger.info("Tomorrow's Prayer Times: ")

            for i, prayer in enumerate(["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]):
                logger.info(f"{prayer}: {today_timings[prayer]}{', ' if prayer != 'Isha' else ''} ")
                prayer_time_labels[prayer].text = today_timings[prayer]  # Update the time label text
                prayer_time_labels[prayer].x = (i * 96) + (
                        96 - prayer_time_labels[prayer].bounding_box[2]) // 2  # Recenter the text

    if all_prayers_passed:
        all_prayers_passed = False
        ct = adafruit_time(hour=00, minute=00, second=00)
    else:
        ct = adafruit_datetime.now().time()

    new_next_prayer, new_next_prayer_time = get_next_prayer(timings=today_timings, current_t=ct)

    if (next_adhan_time is not None) and (ct >= next_adhan_time):
        logger.info(f"Playing adhan {ADHANS[next_prayer]['name']} for {next_prayer} ... ")
        Peripherals.play_file(file_name=ADHANS[next_prayer]['file'], wait_to_finish=True)
        logger.info(f"Adhan for {next_prayer} has finished. ")
        next_adhan_time = None

    if (next_prayer_time is None) or (new_next_prayer_time != next_prayer_time):
        if next_prayer_time is not None:
            logger.info(f"{next_prayer} ({next_prayer_time}) has passed. Updating the next prayer time ... ")

        next_prayer = new_next_prayer
        next_prayer_time = new_next_prayer_time

        if next_prayer_time is not None:
            next_adhan_time = adafruit_time(
                    hour=(next_prayer_time.hour if next_prayer_time.minute >= ADHAN_MINUTES_BEFORE_PRAYER
                          else (next_prayer_time.hour - 1) % 24),
                    minute=(next_prayer_time.minute - ADHAN_MINUTES_BEFORE_PRAYER) % 60
            )
            logger.info(f"RTC: {adafruit_datetime.now()} ")
            logger.info(f"Next prayer is {next_prayer} at time {next_prayer_time} and adhan {next_adhan_time} ")

            # update next prayer label
            np_name_label.text = next_prayer
            np_name_label.x = 240 + (240 - np_name_label.bounding_box[2]) // 2

            # update next adhan label
            np_adhan_label.text = get_str_time(next_adhan_time)
            np_adhan_label.x = 240 + (240 - np_adhan_label.bounding_box[2]) // 2

            footer_adhan_label.text = f"{ADHANS[next_prayer]['name']}"
            footer_adhan_label.x = 28

        else:
            if not all_prayers_passed:
                logger.info(f"RTC: {adafruit_datetime.now()} ")
                logger.info(f"All prayers for today {adafruit_datetime.now().date()} have passed. ")
                all_prayers_passed = True

                prayers_date = get_next_day(prayers_date)
                logger.info(f"Tomorrow is {prayers_date}. ")

                clean_memory()
                print("\n*******************************")
                print(f"** Free memory: {mem_free()} **")
                print("*******************************\n")
                del today_data
                today_data = fetch_prayer_times(date=prayers_date, country=current_ip_country, city=current_ip_city)
                clean_memory()
                print("\n*******************************")
                print(f"** Free memory: {mem_free()} **")
                print("*******************************\n")

                today_timings = None

    if next_prayer_time is not None:
        current_time = adafruit_datetime.now().time()
        one_day_in_seconds = 60 * 60 * 24

        if (next_prayer == 'Fajr') and (current_time > next_prayer_time):
            # Calculate the time until Fajr, considering it's the next day
            section1 = one_day_in_seconds - (
                    current_time.hour * 60 + current_time.minute) * 60 - current_time.second
            section2 = (next_prayer_time.hour * 60 + next_prayer_time.minute) * 60
            time_until_next_prayer = section1 + section2
        else:
            # Calculate time until the next prayer within the same day
            time_until_next_prayer = (next_prayer_time.hour * 60 + next_prayer_time.minute) * 60 - \
                                     (current_time.hour * 60 + current_time.minute) * 60 - current_time.second

        time_until_next_adhan = time_until_next_prayer - (
                ADHAN_MINUTES_BEFORE_PRAYER * 60)  # FIXME : can be negative
        logger.info(f"RTC: {adafruit_datetime.now()} ")
        logger.info(f"Time until next adhan: {time_until_next_adhan} seconds ")
        logger.info(f"Time until next prayer: {time_until_next_prayer} seconds ")
        # time.sleep(time_until_next_adhan if time_until_next_adhan > 0 else time_until_next_prayer)

        # update next prayer countdown label
        hours = time_until_next_prayer // 3600
        minutes = (time_until_next_prayer % 3600) // 60
        np_countdown_label.text = f"{hours:02d} h {minutes:02d} m"
        np_countdown_label.x = 240 + (240 - np_countdown_label.bounding_box[2]) // 2
