import gc
import sys
import time
from os import getenv

import board
import busio
import displayio
import rtc
import storage
from digitalio import DigitalInOut
import adafruit_sdcard


print(f"Free memory: {gc.mem_free()} ")
# print()
# supervisor.runtime.autoreload = False
# print("supervisor.runtime.autoreload = False")

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)  # board.SPI()
vfs = storage.VfsFat(adafruit_sdcard.SDCard(spi, DigitalInOut(board.SD_CS)))
storage.mount(vfs, "/sd")

sys.path.append("/sd")
sys.path.append("/sd/lib")

from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_text.label import Label
from micropython import const
from adafruit_pyportal.graphics import Graphics
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_connection_manager
import adafruit_datetime
import adafruit_logging as Logging
import adafruit_requests
# import adafruit_touchscreen

esp: adafruit_esp32spi.ESP_SPIcontrol = adafruit_esp32spi.ESP_SPIcontrol(
        spi,
        DigitalInOut(board.ESP_CS),
        DigitalInOut(board.ESP_BUSY),
        DigitalInOut(board.ESP_RESET)
)
# Create a shared requests session
requests = adafruit_requests.Session(
        adafruit_connection_manager.get_radio_socketpool(esp),
        adafruit_connection_manager.get_radio_ssl_context(esp)
)

graphics = Graphics(
        # default_bg="/sd/images/bgs/loading.bmp",
        debug=True,
)

try:
    storage.remount(mount_path="/", readonly=False)
    mounted = True
except RuntimeError:
    mounted = False

# Set up Logging
logger = Logging.getLogger("PrayerPortal")
try:
    log_file = "/PrayerPortal.log"  # Log file path
    handler = Logging.FileHandler(log_file)
except OSError:
    handler = Logging.StreamHandler()
logger.setLevel(Logging.INFO)
logger.addHandler(handler)

if mounted:
    logger.info("Root filesystem mounted ")
else:
    logger.warning("Failed to mount the root filesystem ")

# ------------- Constantes ------------- #
RETRIES_DELAY = const(10)
MAX_RETRIES = const(2)
SCREEN_WIDTH = const(480)
SCREEN_HEIGHT = const(320)
WHITE = const(0xFFFFFF)
BLACK = const(0x000000)

# prayer group
PRAYER_GROUP_X = const(0)
PRAYER_GROUP_Y = const(0)
PRAYER_ICON_SIZE = const(32)
# prayer
PRAYER_WIDTH = const(SCREEN_WIDTH // 5)
PRAYER_HEIGHT = const(80)

FOOTER_HEIGHT = const(32)
CENTER_HEIGHT = const(SCREEN_HEIGHT - PRAYER_HEIGHT - FOOTER_HEIGHT)

# current time group
CT_WIDTH = const(SCREEN_WIDTH // 2)
CT_HEIGHT = const((CENTER_HEIGHT // 3) * 2)
CT_X = const(0)
CT_Y = const(PRAYER_HEIGHT)


# date group
CD_WIDTH = const(SCREEN_WIDTH // 2)
CD_HEIGHT = const(CENTER_HEIGHT // 3)
CD_X = const(0)
CD_Y = const(CT_Y + CT_HEIGHT)

# footer group
FOOTER_WIDTH = const(SCREEN_WIDTH)
FOOTER_X = const(0)
FOOTER_Y = const(CD_Y + CD_HEIGHT)
FOOTER_ICON_SIZE = const(24)

# next prayer group
NP_WIDTH = const(SCREEN_WIDTH // 2)
NP_HEIGHT = const(SCREEN_HEIGHT - PRAYER_HEIGHT - FOOTER_HEIGHT)
NP_X = const(SCREEN_WIDTH // 2)
NP_Y = const(PRAYER_HEIGHT)

# adhans
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

# ---------- Set Fonts ------------- #
DEFAULT_FONT_INTERLINE = const(4)
DEFAULT_FONT_SIZE = const(16)
DEFAULT_FONT = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-16.bdf")
DEFAULT_FONT.load_glyphs(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :")

FONT_BOLD_24_ALPHA_NUM_INTERLINE = const(6)
FONT_BOLD_24_ALPHA_NUM_SIZE = const(24)
FONT_BOLD_24_ALPHA_NUM = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-24-AlphaNum.bdf")
FONT_BOLD_24_ALPHA_NUM.load_glyphs(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :")

CT_FONT_SIZE = const(48)
CT_FONT = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-48-CurrentTime.bdf")
CT_FONT.load_glyphs(b"0123456789:")

# Touchscreen setup [ Rotate 0 ]
display = board.DISPLAY
display.rotation = 0
# Initializes the display touch screen area
# ts = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
#                                       board.TOUCH_YD, board.TOUCH_YU,
#                                       calibration=((5200, 59000), (5800, 57000)),
#                                       size=(SCREEN_WIDTH, SCREEN_HEIGHT))

# Wi-Fi configuration
SECRETS = {
    "ssid": getenv("CIRCUITPY_WIFI_SSID"),
    "password": getenv("CIRCUITPY_WIFI_PASSWORD"),
}
if SECRETS["ssid"] is None or SECRETS["password"] is None:
    # TODO Show error on screen
    raise ValueError("Wi-Fi secrets are missing. Please add them in settings.py!")


# ------------- Functions ------------- #
def set_image(group, filename):
    """Set the image file for a given goup for display.
    This is most useful for Icons or image slideshows.
        :param group: The chosen group
        :param filename: The filename of the chosen image
    """
    print("Set image to ", filename)
    if group:
        group.pop()

    if not filename:
        return  # we're done, no icon desired

    image_file = open(filename, "rb")
    image = displayio.OnDiskBitmap(image_file)
    image.pixel_shader.make_transparent(0)
    image_sprite = displayio.TileGrid(image, pixel_shader=image.pixel_shader)

    group.append(image_sprite)


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
        # logger.info(f"My IP address is {esp.ipv4_address} ")


def disconnect_from_wifi():
    global esp

    if esp.connected:
        logger.info(f"Disconnecting from Wi-Fi {SECRETS['ssid']} ... ")
        try:
            esp.disconnect()
            logger.info("Disconnected from Wi-Fi successfully ")
        except Exception as e:
            logger.error(f"Failed to disconnect from Wi-Fi: {e} ")
            raise


def fetch_and_set_rtc() -> adafruit_datetime.datetime:
    global requests
    word_time_api_url = "http://worldtimeapi.org/api/ip"
    logger.info(f"Fetching time from {word_time_api_url} ")

    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            response = requests.get(word_time_api_url)
            respond_json = response.json()
            response.close()

            # Parse the ISO time string
            iso_time_str = respond_json["datetime"][:-6]  # Remove timezone part

            # iso_time_str = "2024-08-31T01:13:25.837247"
            parsed_time = adafruit_datetime.datetime.fromisoformat(iso_time_str)

            # Set the RTC
            rtc.RTC().datetime = parsed_time.timetuple()
            logger.info(f"RTC has been set to {parsed_time} ")
            return parsed_time
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to fetch and set RTC: {e} ")
                raise
            else:
                logger.warning("Failed to fetch and set RTC, retrying ... ")
                time.sleep(RETRIES_DELAY)


def fetch_prayer_times(date: adafruit_datetime.date = None):
    global requests
    if date is None:
        date = adafruit_datetime.datetime.now().date()

    adhans_api_base_url = "https://api.aladhan.com/v1/"
    country = getenv("COUNTRY", "Canada")
    state = getenv("STATE", "")
    city = getenv("CITY", "Montreal")
    methode = getenv("CALCULATION_METHOD", 2)

    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            url = f"{adhans_api_base_url}timingsByCity?date={date.day}-{date.month}-{date.year}&country={country}&city={city}&method={methode}"
            if state:
                url += f"&state={state}"
            logger.info(
                    f"Fetching prayer times for {city},{(' ' + state + ',') if state else ''} {country} for {date} using method {methode} "
            )
            logger.info(f"URL: {url} ")

            response = requests.get(url=url)
            response_json = response.json()
            response.close()
            logger.info("Prayer times fetched successfully! ")
            return response_json
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to fetch prayer times: {e} ")
                raise
            else:
                logger.warning("Failed to fetch prayer times, retrying ... ")
                time.sleep(RETRIES_DELAY)


def get_day_timings(data, date):
    if data is not None:
        day_date = data['date']['gregorian']
        api_date = adafruit_datetime.date(
                year=int(day_date['year']),
                month=int(day_date['month']['number']),
                day=int(day_date['day'])
        )
        if api_date == date:
            return data['timings']
    return None


def get_next_prayer(timings, current_t: adafruit_datetime.time = None):
    if timings is not None:
        if current_t is None:
            current_t = adafruit_datetime.datetime.now().time()

        for next_p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            t = timings[next_p].split(' ')[0].split(':')
            next_p_time = adafruit_datetime.time(hour=int(t[0]), minute=int(t[1]))

            if next_p_time > current_t:
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


def get_str_time(the_time):
    return f"{the_time.__str__()}"


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


def get_str_date(today_data):
    today_gregorian_dict = today_data['data']['date']['gregorian']
    today_gregorian = today_gregorian_dict['day'] + ' ' + today_gregorian_dict['month']['en'] + ' ' + \
                      today_gregorian_dict['year']
    today_hijiri_dict = today_data['data']['date']['hijri']
    today_hijiri = today_hijiri_dict['day'] + ' ' + get_hijri_str_month(today_hijiri_dict['month']['number']) + ' ' + \
                   today_hijiri_dict['year']
    return today_gregorian, today_hijiri


def create_prayer_group(x_position, y_position, prayer_name, width, height):
    prayer_group = displayio.Group(scale=1, x=x_position, y=y_position)

    # Calculate dimensions
    total_label_height = PRAYER_ICON_SIZE + DEFAULT_FONT_SIZE + DEFAULT_FONT_INTERLINE

    # Create the rectangle with a white stroke for the icon and label
    prayer_rect = Rect(
            x=0,
            y=0,
            width=width,
            height=total_label_height,
            outline=WHITE
    )
    prayer_group.append(prayer_rect)

    # Add the icon image group
    icon_group = displayio.Group(scale=1, x=(width - PRAYER_ICON_SIZE) // 2, y=0)
    set_image(icon_group, "/sd/images/icons/" + prayer_name + ".bmp")
    prayer_group.append(icon_group)

    # Create the prayer label
    prayer_label = Label(
            y=PRAYER_ICON_SIZE + (total_label_height - PRAYER_ICON_SIZE) // 2,
            font=DEFAULT_FONT,
            text=prayer_name,
            color=WHITE
    )
    prayer_label.x = (width - prayer_label.bounding_box[2]) // 2
    prayer_group.append(prayer_label)

    # Create the rectangle with a white stroke for the time label
    time_rect = Rect(
            x=0,
            y=total_label_height,
            width=width,
            height=height - total_label_height,
            outline=WHITE
    )
    prayer_group.append(time_rect)

    # Create the time label
    time_label = Label(
            y=total_label_height + (height - total_label_height) // 2,
            font=DEFAULT_FONT,
            color=WHITE
    )
    prayer_group.append(time_label)
    return prayer_group, time_label


def create_current_time_group(x_position, y_position, width, height, current_time):
    ct_group = displayio.Group(scale=1, x=x_position, y=y_position)

    # ct_rect = Rect(x=0, y=0, width=width, height=height, outline=WHITE)
    # ct_group.append(ct_rect)
    # gc.collect()

    time_label = Label(
        y=height // 2,
        font=CT_FONT,
        text=current_time,
        color=WHITE
    )
    time_label.x = (width - time_label.bounding_box[2]) // 2
    ct_group.append(time_label)
    return ct_group, time_label

def create_date_group(x_position, y_position, width, height, gregorian, hijri):
    cd_group = displayio.Group(scale=1, x=x_position, y=y_position)

    cd_rect = Rect(x=0, y=0, width=width, height=height, outline=WHITE)
    cd_group.append(cd_rect)
    gc.collect()

    gregorian_label = Label(
            y=height // 2 - DEFAULT_FONT_SIZE,
            font=FONT_BOLD_24_ALPHA_NUM,
            text=gregorian,
            color=WHITE
    )
    gregorian_label.x = (width - gregorian_label.bounding_box[2]) // 2
    cd_group.append(gregorian_label)

    hijri_label = Label(
            y=height // 2 + DEFAULT_FONT_SIZE,
            font=FONT_BOLD_24_ALPHA_NUM,
            text=hijri,
            color=WHITE
    )
    hijri_label.x = (width - hijri_label.bounding_box[2]) // 2
    cd_group.append(hijri_label)

    return cd_group, gregorian_label, hijri_label


def create_next_prayer_group(x_position, y_position, width, height, title):
    np_group = displayio.Group(scale=1, x=x_position, y=y_position)

    np_rect = Rect(x=0, y=0, width=width, height=height, outline=WHITE)
    np_group.append(np_rect)
    gc.collect()

    title_label = Label(
            y=height // 2 - DEFAULT_FONT_SIZE // 2,
            font=DEFAULT_FONT,
            text=title,
            color=WHITE
    )
    title_label.x = (width - title_label.bounding_box[2]) // 2
    np_group.append(title_label)

    text_label = Label(
            y=height // 2 + DEFAULT_FONT_SIZE,
            font=FONT_BOLD_24_ALPHA_NUM,
            color=WHITE
    )
    np_group.append(text_label)
    return np_group, text_label


def create_footer_group(x_position, y_position, width, height):
    footer_group = displayio.Group(scale=1, x=x_position, y=y_position)

    # footer_rect = Rect(x=0, y=0, width=width, height=height, outline=WHITE)
    # footer_group.append(footer_rect)
    # gc.collect()

    return footer_group


#######################################################################################################################
def main():
    gc.collect()
    connect_to_wifi()
    fetch_and_set_rtc()
    prayers_date = today_date = adafruit_datetime.datetime.now().date()
    # today_data = fetch_prayer_times(prayers_date) # FIXME
    today_data = {
        "code": 200,
        "status": "OK",
        "data": {
            "timings": {
                "Fajr": "04:48",
                "Sunrise": "06:15",
                "Dhuhr": "12:54",
                "Asr": "16:38",
                "Sunset": "19:33",
                "Maghrib": "19:33",
                "Isha": "21:00",
                "Imsak": "04:38",
                "Midnight": "00:54",
                "Firstthird": "23:07",
                "Lastthird": "02:41"
            },
            "date": {
                "readable": "31 Aug 2024",
                "timestamp": "1725102000",
                "hijri": {
                    "date": "25-02-1446",
                    "format": "DD-MM-YYYY",
                    "day": "25",
                    "weekday": {
                        "en": "Al Sabt",
                        "ar": "السبت"
                    },
                    "month": {
                        "number": 2,
                        "en": "Ṣafar",
                        "ar": "صَفَر"
                    },
                    "year": "1446",
                    "designation": {
                        "abbreviated": "AH",
                        "expanded": "Anno Hegirae"
                    },
                    "holidays": []
                },
                "gregorian": {
                    "date": "31-08-2024",
                    "format": "DD-MM-YYYY",
                    "day": "31",
                    "weekday": {
                        "en": "Saturday"
                    },
                    "month": {
                        "number": 8,
                        "en": "August"
                    },
                    "year": "2024",
                    "designation": {
                        "abbreviated": "AD",
                        "expanded": "Anno Domini"
                    }
                }
            },
            "meta": {
                "latitude": 0,
                "longitude": 0,
                "timezone": "America/Toronto",
                "method": {
                    "id": 2,
                    "name": "Islamic Society of North America (ISNA)",
                    "params": {
                        "Fajr": 15,
                        "Isha": 15
                    },
                    "location": {
                        "latitude": 39.7042123,
                        "longitude": -86.3994387
                    }
                },
                "latitudeAdjustmentMethod": "ANGLE_BASED",
                "midnightMode": "STANDARD",
                "school": "STANDARD",
                "offset": {
                    "Imsak": 0,
                    "Fajr": 0,
                    "Sunrise": 0,
                    "Dhuhr": 0,
                    "Asr": 0,
                    "Maghrib": 0,
                    "Sunset": 0,
                    "Isha": 0,
                    "Midnight": 0
                }
            }
        }
    }
    disconnect_from_wifi()

    splash = displayio.Group(scale=1, x=0, y=0)
    gc.collect()

    # Set general back ground
    bg_group = displayio.Group(scale=1, x=0, y=0)
    set_image(bg_group, "/sd/images/bgs/bg1.bmp")
    splash.append(bg_group)
    gc.collect()

    # Initialize the display with empty prayer groups
    time_labels = {}
    for i, prayer in enumerate(["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]):
        group, time_label = create_prayer_group(x_position=(i * PRAYER_WIDTH), y_position=PRAYER_GROUP_Y,
                                                width=PRAYER_WIDTH, height=PRAYER_HEIGHT,
                                                prayer_name=prayer)
        splash.append(group)
        time_labels[prayer] = time_label  # Store the time label for later updates
    gc.collect()

    # Add current time at the center
    ct_group, ct_label = create_current_time_group(x_position=CT_X, y_position=CT_Y,
                                                   width=CT_WIDTH, height=CT_HEIGHT,
                                                   current_time=get_str_time(adafruit_datetime.datetime.now().time()))
    splash.append(ct_group)
    gc.collect()

    # Add date at the bottom
    today_gregorian, today_hijiri = get_str_date(today_data)
    cd_group, gregorian_label, hijri_label = create_date_group(x_position=CD_X, y_position=CD_Y,
                                                               width=CD_WIDTH + 1, height=CD_HEIGHT,
                                                                gregorian=today_gregorian, hijri=today_hijiri)
    splash.append(cd_group)
    gc.collect()

    # Add next prayer at the top right
    SINGLE_NP_HEIGHT = NP_HEIGHT // 3
    np_name_group, np_name_label = create_next_prayer_group(x_position=NP_X, y_position=NP_Y-1,
                                                            width=NP_WIDTH, height=SINGLE_NP_HEIGHT+1,
                                                            title="Next Prayer"
                                                            )
    gc.collect()
    np_adhan_group, np_adhan_label = create_next_prayer_group(x_position=NP_X, y_position=NP_Y+SINGLE_NP_HEIGHT-1,
                                                              width=NP_WIDTH, height=SINGLE_NP_HEIGHT+2,
                                                              title="Next Adhan"
                                                              )
    gc.collect()
    np_countdown_group, np_countdown_label = create_next_prayer_group(x_position=NP_X,
                                                                      y_position=NP_Y + 2 * SINGLE_NP_HEIGHT,
                                                                      width=NP_WIDTH, height=SINGLE_NP_HEIGHT,
                                                                      title="Next Prayer countdown"
                                                                      )
    gc.collect()
    splash.append(np_name_group)
    splash.append(np_adhan_group)
    splash.append(np_countdown_group)

    # Add footer at the bottom
    footer_group = create_footer_group(x_position=FOOTER_X, y_position=FOOTER_Y,
                                       width=FOOTER_WIDTH, height=FOOTER_HEIGHT
                                       )
    splash.append(footer_group)

    today_timings = None
    next_prayer = None
    next_prayer_time = None
    next_adhan_time = None
    start = True
    all_prayers_passed = False
    localtile_refresh = time.monotonic()

    # Set the splash screen as the root group for display
    board.DISPLAY.root_group = splash

    while True:
        # only query the online time once per hour (and on first run)
        # if (time.monotonic() - localtile_refresh) > 3600:
        #     try:
        #         fetch_and_set_rtc()
        #         localtile_refresh = time.monotonic()
        #     except RuntimeError as e:
        #         logger.info("Some error occured, retrying! -", e)
        #         continue

        # update time label
        ct_label.text = get_str_time(adafruit_datetime.datetime.now().time())
        ct_label.x = (CT_WIDTH - ct_label.bounding_box[2]) // 2

        # update date label
        if today_date != adafruit_datetime.datetime.now().date():
            today_date = adafruit_datetime.datetime.now().date()
            today_gregorian, today_hijiri = get_str_date(today_data)
            gregorian_label.text = today_gregorian
            gregorian_label.x = (CD_WIDTH - gregorian_label.bounding_box[2]) // 2
            hijri_label.text = today_hijiri
            hijri_label.x = (CD_WIDTH - hijri_label.bounding_box[2]) // 2

        gc.collect()
        if today_timings is None:
            today_timings = get_day_timings(today_data['data'], prayers_date)
            if today_timings is not None:
                if start:
                    start = False
                    logger.info("Today's Prayer Times: ")
                else:
                    logger.info("Tomorrow's Prayer Times: ")

                for p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
                    logger.info(f"{p}: {today_timings[p]}{', ' if p != 'Isha' else ''} ")
                    time_labels[p].text = today_timings[p]  # Update the time label text
                    time_labels[p].x = (PRAYER_WIDTH - time_labels[p].bounding_box[2]) // 2  # Recenter the text

        if all_prayers_passed:
            all_prayers_passed = False
            ct = adafruit_datetime.time(hour=00, minute=00, second=00)
        else:
            ct = adafruit_datetime.datetime.now().time()

        new_next_prayer, new_next_prayer_time = get_next_prayer(timings=today_timings, current_t=ct)

        if (next_adhan_time is not None) and (ct >= next_adhan_time):
            logger.info(f"Playing adhan {ADHANS[next_prayer]['name']} for {next_prayer} ... ")
            # adafruit_pyportal.play_file(ADHANS[next_prayer]['file']) # FIXME
            logger.info(f"Adhan for {next_prayer} has finished. ")
            next_adhan_time = None

        if (next_prayer_time is None) or (new_next_prayer_time != next_prayer_time):
            if next_prayer_time is not None:
                logger.info(f"{next_prayer} ({next_prayer_time}) has passed. Updating the next prayer time ... ")

            next_prayer = new_next_prayer
            next_prayer_time = new_next_prayer_time

            if next_prayer_time is not None:
                next_adhan_time = adafruit_datetime.time(
                        hour=(next_prayer_time.hour if next_prayer_time.minute >= ADHAN_MINUTES_BEFORE_PRAYER
                              else (next_prayer_time.hour - 1) % 24),
                        minute=(next_prayer_time.minute - ADHAN_MINUTES_BEFORE_PRAYER) % 60
                )
                logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
                logger.info(f"Next prayer is {next_prayer} at time {next_prayer_time} and adhan {next_adhan_time} ")

                # update next prayer label
                np_name_label.text = next_prayer
                np_name_label.x = (NP_WIDTH - np_name_label.bounding_box[2]) // 2

                # update next adhan label
                np_adhan_label.text = get_str_time(next_adhan_time)
                np_adhan_label.x = (NP_WIDTH - np_adhan_label.bounding_box[2]) // 2

            else:
                if not all_prayers_passed:
                    logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
                    logger.info(f"All prayers for today {adafruit_datetime.datetime.now().date()} have passed. ")
                    all_prayers_passed = True

                    prayers_date = get_next_day(prayers_date)
                    logger.info(f"Tomorrow is {prayers_date}. ")
                    # connect_to_wifi()
                    today_data = fetch_prayer_times(prayers_date)
                    # disconnect_from_wifi()

                    today_timings = None

        if next_prayer_time is not None:
            current_time = adafruit_datetime.datetime.now().time()
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
            logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
            logger.info(f"Time until next adhan: {time_until_next_adhan} seconds ")
            logger.info(f"Time until next prayer: {time_until_next_prayer} seconds ")
            # time.sleep(time_until_next_adhan if time_until_next_adhan > 0 else time_until_next_prayer)

            # update next prayer countdown label
            np_countdown_label.text = str(time_until_next_prayer)
            np_countdown_label.x = (NP_WIDTH - np_countdown_label.bounding_box[2]) // 2


main()
# retry_count = 0
# while retry_count < MAX_RETRIES:
#     try:
#         main()
#         break
#     except Exception as e:
#         retry_count += 1
#         logger.error(f"Exception caught: {e}. Attempt {retry_count} of {MAX_RETRIES} ")
#         # time.sleep(RETRIES_DELAY)
#         if retry_count == MAX_RETRIES:
#             logger.error("Max retries reached. Raising exception. ")
#             raise e
#         else:
#             gc.collect()
#             logger.info("Reloading program... ")
#             supervisor.reload()  # Reload the entire program
