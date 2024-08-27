import gc
import time
from os import getenv

import adafruit_connection_manager
import adafruit_datetime
import adafruit_logging as logging
import adafruit_requests
import adafruit_touchscreen
import board
import displayio
import rtc
import storage
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_text.label import Label
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_pyportal import PyPortal
from digitalio import DigitalInOut

esp: adafruit_esp32spi.ESP_SPIcontrol = adafruit_esp32spi.ESP_SPIcontrol(
    board.SPI(),
    DigitalInOut(board.ESP_CS),
    DigitalInOut(board.ESP_BUSY),
    DigitalInOut(board.ESP_RESET)
)
# ESP32 SPI Configuration
requests: adafruit_requests.Session
# ------------- Screen Setup ------------- #
pyportal = PyPortal(
    default_bg="/images/bg.bmp",
    status_neopixel=board.NEOPIXEL,
    text_wrap=True,
    esp=esp
    # debug=True
)

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

# ------------- Constantes ------------- #
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
WHITE = 0xFFFFFF
RED = 0xFF0000
YELLOW = 0xFFFF00
GREEN = 0x00FF00
BLUE = 0x0000FF
PURPLE = 0xFF00FF
BLACK = 0x000000

PRAYER_ICON_SIZE = 32
PRAYER_WIDTH = SCREEN_WIDTH // 5
PRAYER_HEIGHT = 80
PRAYER_Y_POSITION = 0  # SCREEN_HEIGHT - PRAYER_HEIGHT
LABEL_SPACING = 8

ADHAN_MINUTES_BEFORE_PRAYER = 5
ADHANS = {
    "Fajr": "/sd/adhans/AhmadAlNafees.wav",
    "Dhuhr": "/sd/adhans/HafizMustafaOzcan.wav",
    "Asr": "/sd/adhans/MasjidAlHaramMecca.wav",
    "Maghrib": "/sd/adhans/MisharyRashidAlafasy.wav",
    "Isha": "/sd/adhans/QariAbdulKareem.wav"
}

# ---------- Set Font ------------- #
# Set the font and preload letters
font = bitmap_font.load_font("/fonts/Helvetica-Bold-16.bdf")
font.load_glyphs(b"abcdefghjiklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890- ()")

# Touchscreen setup [ Rotate 0 ]
display = board.DISPLAY
display.rotation = 0
# Initializes the display touch screen area
ts = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
                                      board.TOUCH_YD, board.TOUCH_YU,
                                      calibration=((5200, 59000), (5800, 57000)),
                                      size=(SCREEN_WIDTH, SCREEN_HEIGHT))

# Wi-Fi configuration
SECRETS = {
    "ssid": getenv("CIRCUITPY_WIFI_SSID"),
    "password": getenv("CIRCUITPY_WIFI_PASSWORD"),
}
if SECRETS["ssid"] is None or SECRETS["password"] is None:
    # TODO Show error on screen
    raise ValueError("Wi-Fi secrets are missing. Please add them in settings.py!")


# ------------- Functions ------------- #
# Backlight function
# Value between 0 and 1 where 0 is OFF, 0.5 is 50% and 1 is 100% brightness.
def set_backlight(val):
    val = max(0, min(1.0, val))
    try:
        board.DISPLAY.auto_brightness = False
    except AttributeError:
        pass
    board.DISPLAY.brightness = val


# This will handle switching Images and Icons
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


# return a reformatted string with word wrapping using PyPortal.wrap_nicely
def text_box(target, top, string, max_chars):
    text = pyportal.wrap_nicely(string, max_chars)
    new_text = ""
    test = ""

    for w in text:
        new_text += "\n" + w
        test += "M\n"

    text_height = Label(font, text="M", color=0x03AD31)
    text_height.text = test  # Odd things happen without this
    glyph_box = text_height.bounding_box
    target.text = ""  # Odd things happen without this
    target.y = int(glyph_box[3] / 2) + top
    target.text = new_text


def create_prayer_group(x_position, prayer_name, prayer_time="12:00"):
    group = displayio.Group(scale=1, x=x_position, y=PRAYER_Y_POSITION)

    # Calculate dimensions
    prayer_label_y = PRAYER_ICON_SIZE + LABEL_SPACING
    total_label_height = PRAYER_ICON_SIZE + (prayer_label_y // 2)

    # Create the rectangle with a white stroke for the icon and label
    prayer_rect = Rect(
        x=0,
        y=0,
        width=PRAYER_WIDTH,
        height=total_label_height,
        outline=WHITE
    )
    group.append(prayer_rect)

    # Add the icon image group
    icon_group = displayio.Group(scale=1, x=(PRAYER_WIDTH - PRAYER_ICON_SIZE) // 2, y=0)
    set_image(icon_group, "/images/" + prayer_name + ".bmp")
    group.append(icon_group)

    # Create the prayer label
    prayer_label = Label(
        y=prayer_label_y,
        font=font,
        text=prayer_name,
        color=WHITE
    )
    prayer_label.x = (PRAYER_WIDTH - prayer_label.bounding_box[2]) // 2
    group.append(prayer_label)

    # Create the rectangle with a white stroke for the time label
    time_rect = Rect(
        x=0,
        y=total_label_height,
        width=PRAYER_WIDTH,
        height=PRAYER_HEIGHT - total_label_height,
        outline=WHITE
    )
    group.append(time_rect)

    # Create the time label
    time_label_y = total_label_height + LABEL_SPACING * 2
    time_label = Label(
        y=time_label_y,
        font=font,
        # text=prayer_time,
        color=WHITE
    )
    # time_label.x = (PRAYER_WIDTH - time_label.bounding_box[2]) // 2
    group.append(time_label)

    return group, time_label


def connect_to_wifi():
    global esp, requests

    if not esp.connected:
        requests = adafruit_requests.Session(
            adafruit_connection_manager.get_radio_socketpool(esp),
            adafruit_connection_manager.get_radio_ssl_context(esp)
        )
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

    retry = 0
    while retry < 3:
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
            if retry == 2:
                logger.error(f"Failed to fetch and set RTC: {e} ")
                raise
            else:
                logger.warning("Failed to fetch and set RTC, retrying ... ")
                retry += 1
                time.sleep(5)


def fetch_prayer_times(date: adafruit_datetime.date = None):
    if date is None:
        date = adafruit_datetime.datetime.now().date()

    base_url = getenv("API_BASE_URL", "https://api.aladhan.com/v1/")
    country = getenv("COUNTRY", "Canada")
    state = getenv("STATE", "")
    city = getenv("CITY", "Montreal")
    method = getenv("CALCULATION_METHOD", 2)
    day = date.day
    month = date.month
    year = date.year

    retry = 0
    while retry < 3:
        try:
            url = f"{base_url}timingsByCity?date={day}-{month}-{year}&country={country}&city={city}&method={method}"

            if state:
                url += f"&state={state}"

            logger.info(
                f"Fetching prayer times for {city},{(' ' + state + ',') if state else ''} {country} for {date} using method {method} ")
            logger.info(f"URL: {url} ")

            response = requests.get(url=url)
            data = response.json()
            response.close()
            logger.info("Prayer times fetched successfully! ")
            return data
        except Exception as e:
            if retry == 2:
                logger.error(f"Failed to fetch prayer times: {e} ")
                raise
            else:
                logger.warning("Failed to fetch prayer times, retrying ... ")
                retry += 1
                time.sleep(5)


def get_day_timings(data, date) -> dict | None:
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


def get_next_prayer(timings, current_t: adafruit_datetime.time = None) -> (str, adafruit_datetime.time):
    if timings is not None:
        if current_t is None:
            current_t = adafruit_datetime.datetime.now().time()

        for next_p in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
            t = timings[next_p].split(' ')[0].split(':')
            next_p_time = adafruit_datetime.time(hour=int(t[0]), minute=int(t[1]))

            if next_p_time > current_t:
                return next_p, next_p_time

    return None, None


def get_next_day(date_obj: adafruit_datetime.date) -> adafruit_datetime.date:
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

gc.collect()
connect_to_wifi()
fetch_and_set_rtc()
today_date = adafruit_datetime.datetime.now().date()
today_data = fetch_prayer_times(today_date)
disconnect_from_wifi()

splash = displayio.Group(scale=1, x=0, y=0)

# Set general back ground
bg_group = displayio.Group(scale=1, x=0, y=0)
set_image(bg_group, "/images/bg.bmp")
splash.append(bg_group)

# Initialize the display with empty prayer groups
time_labels = {}
for i, prayer in enumerate(["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]):
    group, time_label = create_prayer_group(x_position=(i * PRAYER_WIDTH), prayer_name=prayer)
    splash.append(group)
    time_labels[prayer] = time_label  # Store the time label for later updates

today_timings = None
next_prayer = None
next_prayer_time = None
next_adhan_time = None
start = True
all_prayers_passed = False

# Set the splash screen as the root group for display
board.DISPLAY.root_group = splash

while True:
    gc.collect()
    if today_timings is None:
        today_timings = get_day_timings(today_data['data'], today_date)
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
        logger.info(f"Playing adhan for {next_prayer} ... ")
        pyportal.play_file(ADHANS[next_prayer])
        logger.info(f"Adhan for {next_prayer} has finished. ")

    if (next_prayer_time is None) or (new_next_prayer_time != next_prayer_time):
        if next_prayer_time is not None:
            logger.info(f"{next_prayer} ({next_prayer_time}) has passed. Updating the next prayer time ... ")

        next_prayer = new_next_prayer
        next_prayer_time = new_next_prayer_time
        next_adhan_time = adafruit_datetime.time(hour=next_prayer_time.hour,
                                                 minute=next_prayer_time.minute - ADHAN_MINUTES_BEFORE_PRAYER)

        if next_prayer_time is not None:
            logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
            logger.info(f"Next prayer is {next_prayer} at {next_prayer_time} ")
        else:
            logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
            logger.info(f"All prayers for today {adafruit_datetime.datetime.now().date()} have passed. ")
            all_prayers_passed = True

            today_date = get_next_day(today_date)
            logger.info(f"Tomorrow is {today_date}. ")
            connect_to_wifi()
            today_data = fetch_prayer_times(today_date)
            disconnect_from_wifi()

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

        time_until_next_adhan = time_until_next_prayer - (ADHAN_MINUTES_BEFORE_PRAYER * 60) # FIXME : can be negative
        logger.info(f"RTC: {adafruit_datetime.datetime.now()} ")
        logger.info(f"Time until next adhan: {time_until_next_adhan} seconds ")
        logger.info(f"Time until next prayer: {time_until_next_prayer} seconds ")
        time.sleep(time_until_next_adhan if time_until_next_adhan > 0 else 0)
