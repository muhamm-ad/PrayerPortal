"""PrayerPortal: prayer times, clock and adhan on the Adafruit PyPortal Titano."""
import time
from gc import collect as clean_memory, mem_free
from json import dump, load
from os import getenv, listdir

import adafruit_touchscreen
import audiocore
import audioio
import board
import displayio
import microcontroller
import rtc
from adafruit_bitmap_font import bitmap_font
from adafruit_connection_manager import get_radio_socketpool, get_radio_ssl_context
from adafruit_display_text.label import Label
from adafruit_esp32spi.adafruit_esp32spi import ESP_SPIcontrol
from adafruit_logging import INFO, RotatingFileHandler, StreamHandler, getLogger
from adafruit_requests import Session
from digitalio import DigitalInOut
from micropython import const

import prayer_logic as pl

clean_memory()

# ------------- Constants ------------- #
SCREEN_WIDTH = const(480)
SCREEN_HEIGHT = const(320)
WHITE = const(0xFFFFFF)

RETRIES_DELAY = const(10)  # seconds, multiplied by the attempt number
MAX_RETRIES = const(3)
RETRY_AFTER_S = const(300)  # wait before retrying a failed refresh
SYNC_EVERY_S = const(3600)  # NTP / UTC offset refresh period
RESET_AFTER_S = const(30)  # delay before rebooting after a fatal error
HOLD_S = const(10)  # how long a footer message / selected prayer stays shown
MIN_VALID_UNIX = 1700000000  # the ESP32 reports ~0 until its NTP sync completes

ADHAN_LEAD_S = const(300)  # the adhan plays 5 minutes before the prayer
ADHAN_DIR = "/sd/adhans"
ADHAN_CONFIG = "/sd/adhans.json"
DEFAULT_ADHANS = (
    "AhmadAlNafees.wav",  # Fajr
    "HafizMustafaOzcan.wav",  # Dhuhr
    "MasjidAlHaramMecca.wav",  # Asr
    "MisharyRashidAlafasy.wav",  # Maghrib
    "QariAbdulKareem.wav",  # Isha
)

LOG_FILE = "/sd/PrayerPortal.log"
LOG_MAX_BYTES = const(65536)  # one backup is kept, so at most ~128 KB on the SD card

LOCATION_URL = "http://ip-api.com/json/?fields=status,message,country,city,timezone,offset"
ALADHAN_URL = "https://api.aladhan.com/v1/timingsByCity/"

SECRETS = {
    "ssid": getenv("CIRCUITPY_WIFI_SSID"),
    "password": getenv("CIRCUITPY_WIFI_PASSWORD"),
}



def env_flag(name, default=True):
    """Read an on/off setting from settings.toml (0, false, off and no mean off)."""
    value = getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() not in ("0", "false", "off", "no")


# ------------- Logging ------------- #
# Every message goes to the SD card; TERMINAL_LOGS (on by default) also prints it to the serial console.
logger = getLogger("PrayerPortal")
console_logs = env_flag("TERMINAL_LOGS")
try:
    logger.addHandler(RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=1))
except OSError:
    console_logs = True  # no log file: keep the console so nothing is lost
if console_logs:
    logger.addHandler(StreamHandler())
logger.setLevel(INFO)

# ------------- State shared with the helpers ------------- #
esp = None
utc_offset = 0
offset_fixed = False  # True when UTC_OFFSET is set in settings.toml
status_label = None  # footer label: adhan name, or a status / error message
footer_hold_until = 0  # while time.time() is below this, keep the message shown


# ------------- Display helpers ------------- #

def set_image(group, filename):
    """Set the image file for a given group for display.
    This is most useful for Icons or image slideshows.
        :param group: The chosen group
        :param filename: The filename of the chosen image
        :return: the open image file (it must stay open while the image is shown)
    """
    if group:
        group.pop()

    if not filename:
        return None  # we're done, no icon desired

    logger.info(f"Set image {filename} ")
    image_file = open(filename, "rb")
    image = displayio.OnDiskBitmap(image_file)
    image.pixel_shader.make_transparent(0)
    group.append(displayio.TileGrid(image, pixel_shader=image.pixel_shader))
    return image_file


def set_text(label, text, x0, width):
    """Change a label only when its text changed, centered in [x0, x0 + width)."""
    if label.text != text:
        label.text = text
        label.x = x0 + (width - label.bounding_box[2]) // 2


def show_status(text, hold=0):
    """Show a short message in the footer; with hold, keep it for that many seconds.

    Until the interface is up the screen shows the terminal, so the message goes to the log instead.
    """
    global footer_hold_until
    if status_label is None:
        logger.info(text)
        return
    status_label.text = text[:38]  # stay clear of the footer icons
    footer_hold_until = time.time() + hold if hold else 0


def show_day(tiles, gregorian_label, hijri_label, times, gregorian, hijri):
    for i in range(5):
        set_text(tiles[i], pl.fmt_hm(times[i]), i * 96, 96)
    set_text(gregorian_label, gregorian, 0, 240)
    set_text(hijri_label, hijri, 0, 240)
    logger.info("Prayer times: " + ", ".join(f"{pl.PRAYERS[i]} {pl.fmt_hm(times[i])}" for i in range(5)))


def log_memory(tag):
    clean_memory()
    logger.info(f"{tag} - free memory: {mem_free()} B")


def fatal(err, reset=True):
    """Report an unrecoverable error on screen and in the log, then reboot."""
    message = f"{type(err).__name__}: {err}"
    try:
        logger.error(message)
    except Exception:
        pass
    try:  # show the terminal again so the error can be read on the PyPortal
        board.DISPLAY.root_group = displayio.CIRCUITPYTHON_TERMINAL
    except Exception:
        pass
    try:  # the traceback always goes to the console, whatever TERMINAL_LOGS says
        import traceback
        traceback.print_exception(err)
    except Exception:
        print(message)
    if not reset:  # e.g. missing settings: editing settings.toml reloads the code
        while True:
            time.sleep(1)
    time.sleep(RESET_AFTER_S)
    microcontroller.reset()


# ------------- Network ------------- #

def connect_to_wifi():
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


def recover_esp():
    """Reset a hung ESP32 co-processor and reconnect Wi-Fi."""
    logger.warning("Resetting ESP32 after network failure ... ")
    try:
        esp.reset()
    except Exception as e:
        logger.error(f"ESP32 reset failed: {e} ")
    time.sleep(2)
    connect_to_wifi()
    clean_memory()


def get_json(url, check=None, quick=False):
    """GET url and return the decoded JSON, retrying after an ESP32 reset.

    check(data) may raise to reject a response (it is then retried too).
    quick: two attempts and no pause, so a network outage cannot freeze the clock for long.
    """
    attempts = 2 if quick else MAX_RETRIES
    for attempt in range(1, attempts + 1):
        response = None
        try:
            connect_to_wifi()
            session = Session(get_radio_socketpool(esp), get_radio_ssl_context(esp))
            response = session.get(url, stream=True)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            data = response.json()
            if check is not None:
                check(data)
            return data
        except Exception as e:
            if attempt == attempts:
                logger.error(f"Request failed: {e} ")
                raise
            logger.warning(f"Request failed ({e}), retrying ... ")
        finally:
            if response is not None:
                response.close()
        recover_esp()
        if not quick:
            time.sleep(RETRIES_DELAY * attempt)
        clean_memory()


def check_location(data):
    if data.get("status") != "success":
        raise RuntimeError(data.get("message", "ip-api lookup failed"))
    if "offset" not in data:
        raise RuntimeError("ip-api response missing UTC offset")


def check_aladhan(data):
    if data.get("code") != 200:
        raise RuntimeError(f"Aladhan: {data.get('data', data.get('status'))}")


def fetch_location(quick=False):
    # `offset` is not in ip-api's default fields; it is requested explicitly.
    return get_json(LOCATION_URL, check_location, quick)


def fetch_day(ymd, city, country, state, method, quick=False):
    """Prayer times for ymd = (year, month, day): ([5 seconds], gregorian, hijri)."""
    url = (f"{ALADHAN_URL}{ymd[2]:02d}-{ymd[1]:02d}-{ymd[0]:04d}"
           f"?country={pl.urlquote(country)}&city={pl.urlquote(city)}&method={pl.urlquote(str(method))}")
    if state:
        url += f"&state={pl.urlquote(state)}"
    logger.info(f"Fetching prayer times for {city},{(' ' + state + ',') if state else ''} {country} "
                f"on {ymd[0]}-{ymd[1]:02d}-{ymd[2]:02d} using method {method} ")
    body = get_json(url, check_aladhan, quick)
    day = pl.parse_day(body["data"], ymd)  # keep 5 numbers and 2 strings, drop the rest
    del body
    log_memory(f"Prayer times for {ymd[0]}-{ymd[1]:02d}-{ymd[2]:02d} fetched")
    return day


def sync_rtc(offset_seconds, quick=False):
    """Set the RTC to local time from the ESP32's NTP clock (retries, then raises)."""
    # Prefer NTP over HTTPS time APIs: TLS often hangs the PyPortal ESP32 SPI stack.
    attempts = 2 if quick else MAX_RETRIES
    for attempt in range(1, attempts + 1):
        try:
            connect_to_wifi()
            ntp_unix = esp.get_time()[0]
            if ntp_unix < MIN_VALID_UNIX:
                raise RuntimeError("NTP time not ready")
            rtc.RTC().datetime = time.localtime(ntp_unix + offset_seconds)
            t = time.localtime()
            logger.info(f"RTC set to {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} (UTC offset {offset_seconds}s) ")
            clean_memory()
            return
        except Exception as e:
            if attempt == attempts:
                logger.error(f"Failed to fetch and set RTC: {e} ")
                raise
            logger.warning("Failed to fetch and set RTC, retrying ... ")
            recover_esp()
            if not quick:
                time.sleep(RETRIES_DELAY * attempt)
            clean_memory()


def refresh_clock():
    """Re-sync the RTC; also re-read the UTC offset (daylight saving) unless UTC_OFFSET is set."""
    global utc_offset
    if not offset_fixed:
        try:
            utc_offset = int(fetch_location(quick=True)["offset"])
        except Exception as e:
            logger.warning(f"UTC offset refresh failed, keeping {utc_offset}s: {e} ")
    sync_rtc(utc_offset, quick=True)


# ------------- Time helpers ------------- #

def local_clock(epoch):
    """(seconds since local midnight, (year, month, day)) for an RTC epoch."""
    t = time.localtime(epoch)
    return t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec, (t.tm_year, t.tm_mon, t.tm_mday)


def local_ymd(epoch):
    return local_clock(epoch)[1]


# ------------- Adhans ------------- #

def list_adhans():
    try:
        names = [n for n in listdir(ADHAN_DIR) if n.lower().endswith(".wav") and not n.startswith(".")]
    except OSError:
        names = []
    names.sort()
    return names


def load_adhans(available):
    """Adhan file per prayer: the saved choice if it still exists, else the default."""
    files = list(DEFAULT_ADHANS)
    try:
        with open(ADHAN_CONFIG) as fp:
            saved = load(fp)
        for i in range(5):
            name = saved.get(pl.PRAYERS[i])
            if name in available:
                files[i] = name
    except Exception:  # no / invalid file: keep the defaults
        pass
    return files


def save_adhans(files):
    try:
        with open(ADHAN_CONFIG, "w") as fp:
            dump({pl.PRAYERS[i]: files[i] for i in range(5)}, fp)
    except OSError as e:
        logger.error(f"Cannot save the adhan choice: {e} ")


def adhan_footer(files, shown, next_idx):
    name = pl.adhan_label(files[shown])
    return (name if shown == next_idx else f"{pl.PRAYERS[shown]}: {name}")[:38]  # clear of the icons


def play_adhan(audio, speaker_enable, filename):
    """Start playing an adhan without blocking; returns the open file, or None on failure."""
    logger.info(f"Playing adhan {filename} ... ")
    wavfile = None
    try:
        clean_memory()
        wavfile = open(ADHAN_DIR + "/" + filename, "rb")
        speaker_enable.value = True
        audio.play(audiocore.WaveFile(wavfile))
        return wavfile
    except Exception as e:
        logger.error(f"Cannot play {filename}: {e} ")
        speaker_enable.value = False
        if wavfile is not None:
            wavfile.close()
        return None


# ------------- Run ------------- #

def main():
    global esp, utc_offset, offset_fixed, footer_hold_until, status_label
    log_memory("Boot")

    if SECRETS["ssid"] is None or SECRETS["password"] is None:
        fatal(ValueError("Wi-Fi secrets missing in settings.toml"), reset=False)

    esp = ESP_SPIcontrol(
        board.SPI(),
        DigitalInOut(board.ESP_CS),
        DigitalInOut(board.ESP_BUSY),
        DigitalInOut(board.ESP_RESET),
    )

    # --- Network bootstrap ---
    show_status("Wi-Fi: connecting ...")
    connect_to_wifi()
    show_status("Finding location ...")
    place = fetch_location()
    offset_env = getenv("UTC_OFFSET")
    offset_fixed = offset_env is not None
    utc_offset = int(offset_env) if offset_fixed else int(place["offset"])
    timezone = getenv("TIMEZONE", place["timezone"])
    city = getenv("CITY", place["city"])
    country = getenv("COUNTRY", place["country"])
    state = getenv("STATE", "")
    method = getenv("CALCULATION_METHOD", 2)
    logger.info(f"Location: {city}, {country} ({timezone}, UTC offset {utc_offset}s) ")
    del place

    show_status("Setting the clock ...")
    sync_rtc(utc_offset)
    show_status("Fetching prayer times ...")
    times_ymd = local_ymd(time.time())
    times, gregorian, hijri = fetch_day(times_ymd, city, country, state, method)
    tomorrow = None  # (times, gregorian, hijri) of the next day, fetched after Isha
    tomorrow_ymd = None
    log_memory("Network ready")

    # --- Audio and touch ---
    speaker_enable = DigitalInOut(board.SPEAKER_ENABLE)
    speaker_enable.switch_to_output(False)
    if hasattr(board, "AUDIO_OUT"):
        audio = audioio.AudioOut(board.AUDIO_OUT)
    else:
        audio = audioio.AudioOut(board.SPEAKER)
    touch = adafruit_touchscreen.Touchscreen(
        board.TOUCH_XL, board.TOUCH_XR, board.TOUCH_YD, board.TOUCH_YU,
        calibration=((5200, 59000), (5800, 57000)),
        size=(SCREEN_WIDTH, SCREEN_HEIGHT),
    )
    available = list_adhans()
    adhan_files = load_adhans(available)

    # --- Screen ---
    font_16 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-16.bdf")
    font_16.load_glyphs("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :'-.,()/!")
    font_24 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-24-AlphaNum.bdf")
    font_24.load_glyphs("FajrDhuhrAsrMaghribIsha0123456789 :hm")
    font_48 = bitmap_font.load_font("/sd/fonts/Helvetica-Bold-48-CurrentTime.bdf")
    font_48.load_glyphs("0123456789:")

    splash = displayio.Group()
    bg_group = displayio.Group()
    bg_file = set_image(bg_group, "/sd/images/bg1.bmp")
    splash.append(bg_group)
    template_group = displayio.Group()
    template_file = set_image(template_group, "/sd/images/template.bmp")
    splash.append(template_group)

    tiles = []  # one time label per prayer
    for _ in range(5):
        tile = Label(y=71, font=font_16, color=WHITE)
        splash.append(tile)
        tiles.append(tile)
    ct_label = Label(y=151, font=font_48, color=WHITE)
    gregorian_label = Label(y=242, font=font_16, color=WHITE)
    hijri_label = Label(y=274, font=font_16, color=WHITE)
    np_name_label = Label(y=127, font=font_24, color=WHITE)
    np_adhan_label = Label(y=198, font=font_24, color=WHITE)
    np_countdown_label = Label(y=269, font=font_24, color=WHITE)
    for label in (ct_label, gregorian_label, hijri_label, np_name_label, np_adhan_label, np_countdown_label):
        splash.append(label)
    status_label = Label(x=28, y=307, font=font_16, color=WHITE)
    splash.append(status_label)

    show_day(tiles, gregorian_label, hijri_label, times, gregorian, hijri)
    board.DISPLAY.root_group = splash  # replaces the terminal shown since boot
    clean_memory()

    night_level = None  # optional: NIGHT_BRIGHTNESS (percent) dims the screen at night
    if getenv("NIGHT_BRIGHTNESS") is not None:
        try:
            night_level = max(0.05, min(1.0, int(getenv("NIGHT_BRIGHTNESS")) / 100))
        except ValueError:
            logger.warning("NIGHT_BRIGHTNESS must be a whole percentage, ignoring it ")
    dimmed = None
    log_memory("Screen ready")

    # --- Loop ---
    trigger = pl.AdhanTrigger(ADHAN_LEAD_S)
    playing = None  # open WAV file while an adhan is playing
    next_idx = 0  # index of the next prayer
    shown = 0  # prayer whose adhan the footer shows
    shown_until = 0
    next_sync = time.time() + SYNC_EVERY_S
    next_fetch = 0  # earliest time for the next prayer-times request
    last_epoch = -1
    last_touch = 0.0

    while True:
        # Touch: tap a prayer tile to select it, tap the footer to change its adhan.
        point = touch.touch_point
        if point is not None and time.monotonic() - last_touch > 0.6:
            last_touch = time.monotonic()
            now = time.time()
            if point[1] < 75:
                shown = min(point[0] // 96, 4)
                shown_until = now + HOLD_S
                footer_hold_until = 0
                status_label.text = adhan_footer(adhan_files, shown, next_idx)
            elif point[1] >= 295 and point[0] < 380 and available:
                if now >= shown_until:
                    shown = next_idx
                adhan_files[shown] = pl.cycle(available, adhan_files[shown])
                save_adhans(adhan_files)
                shown_until = now + HOLD_S
                footer_hold_until = 0
                status_label.text = adhan_footer(adhan_files, shown, next_idx)
                logger.info(f"{pl.PRAYERS[shown]} adhan set to {adhan_files[shown]} ")

        epoch = time.time()
        if epoch != last_epoch:  # once per second
            now_s, ymd = local_clock(epoch)
            networked = False

            # New day: use the times fetched yesterday evening, or fetch them.
            if ymd != times_ymd:
                if tomorrow is not None and tomorrow_ymd == ymd:
                    times, gregorian, hijri = tomorrow
                    times_ymd = ymd
                    tomorrow = None
                    show_day(tiles, gregorian_label, hijri_label, times, gregorian, hijri)
                elif epoch >= next_fetch and playing is None:
                    networked = True
                    try:
                        times, gregorian, hijri = fetch_day(ymd, city, country, state, method, quick=True)
                        times_ymd = ymd
                        show_day(tiles, gregorian_label, hijri_label, times, gregorian, hijri)
                    except Exception as e:
                        logger.error(f"Prayer times for {ymd} unavailable: {e} ")
                        show_status("Prayer times: retrying", HOLD_S)
                        next_fetch = epoch + RETRY_AFTER_S

            # After Isha: fetch tomorrow's times (Fajr is the next prayer).
            if (tomorrow is None and ymd == times_ymd and now_s >= times[4]
                    and epoch >= next_fetch and playing is None):
                networked = True
                try:
                    tomorrow_ymd = local_ymd(epoch + pl.DAY_S)
                    tomorrow = fetch_day(tomorrow_ymd, city, country, state, method, quick=True)
                    logger.info("Tomorrow's prayer times are ready. ")
                except Exception as e:
                    logger.error(f"Tomorrow's prayer times unavailable: {e} ")
                    show_status("Prayer times: retrying", HOLD_S)
                    next_fetch = epoch + RETRY_AFTER_S

            # Hourly clock re-sync (and daylight-saving offset refresh).
            if epoch >= next_sync and playing is None:
                networked = True
                try:
                    refresh_clock()
                    next_sync = time.time() + SYNC_EVERY_S
                except Exception as e:
                    logger.error(f"Clock sync failed, keeping the RTC time: {e} ")
                    show_status("Clock sync: retrying", HOLD_S)
                    next_sync = time.time() + RETRY_AFTER_S

            if networked:  # requests can take a while, so read the clock again
                epoch = time.time()
                now_s, ymd = local_clock(epoch)
            last_epoch = epoch

            # Adhan playback ended?
            if playing is not None and not audio.playing:
                audio.stop()
                playing.close()
                playing = None
                speaker_enable.value = False
                logger.info("Adhan has finished. ")

            # Next prayer, its adhan and the countdown to it.
            next_idx, prayer_s = pl.next_prayer(now_s, times, tomorrow[0] if tomorrow else None)
            adhan_s = prayer_s - ADHAN_LEAD_S
            previous = trigger.key
            if trigger.update(next_idx, prayer_s, now_s):
                if playing is None:
                    playing = play_adhan(audio, speaker_enable, adhan_files[next_idx])
            if trigger.changed:
                if previous is not None and previous[0] != next_idx:
                    logger.info(f"{pl.PRAYERS[previous[0]]} ({pl.fmt_hm(previous[1])}) has passed. ")
                logger.info(f"RTC {pl.fmt_hm(now_s)}:{now_s % 60:02d} - next prayer is {pl.PRAYERS[next_idx]} "
                            f"at {pl.fmt_hm(prayer_s)}, adhan at {pl.fmt_hm(adhan_s)} ")

            set_text(ct_label, pl.fmt_hm(now_s), 0, 240)
            set_text(np_name_label, pl.PRAYERS[next_idx], 240, 240)
            set_text(np_adhan_label, pl.fmt_hm(adhan_s), 240, 240)
            set_text(np_countdown_label, pl.fmt_countdown(adhan_s - now_s), 240, 240)

            if epoch >= footer_hold_until:
                text = adhan_footer(adhan_files, shown if epoch < shown_until else next_idx, next_idx)
                if status_label.text != text:
                    status_label.text = text

            if night_level is not None:
                night = now_s >= times[4] + 3600 or now_s < times[0] - 3600
                if night != dimmed:
                    dimmed = night
                    try:
                        board.DISPLAY.brightness = night_level if night else 1.0
                    except Exception as e:
                        logger.warning(f"Cannot change the brightness: {e} ")
                        night_level = None

            if now_s % 60 == 0:
                clean_memory()

        time.sleep(0.1)  # also the touch polling period


# No root group is set until the interface is ready: the screen shows the CircuitPython terminal,
# so the log lines and any startup error can be read on the PyPortal itself.
board.DISPLAY.rotation = 0

try:
    main()
except Exception as error:  # last resort: show the error, then reboot
    fatal(error)
