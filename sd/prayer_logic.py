"""Pure prayer-schedule helpers.

No hardware imports: everything here also runs on a PC, which is what
tests/test_prayer_logic.py relies on. All times are integer seconds since
local midnight, so "tomorrow's Fajr" is simply ``86400 + fajr``.
"""

DAY_S = 86400
PRAYERS = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
HIJRI_MONTHS = (
    "Muharram",
    "Safar",
    "Rabi' al-awwal",
    "Rabi' al-thani",
    "Jumada al-awwal",
    "Jumada al-thani",
    "Rajab",
    "Sha'ban",
    "Ramadan",
    "Shawwal",
    "Dhu al-Qi'dah",
    "Dhu al-Hijjah",
)
_URL_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"


def parse_hhmm(text):
    """'05:40' or '05:40 (EDT)' -> seconds since midnight."""
    hm = text.split(" ")[0].split(":")
    return int(hm[0]) * 3600 + int(hm[1]) * 60


def fmt_hm(seconds):
    """Seconds since midnight -> 'HH:MM' (wraps at 24 h)."""
    seconds %= DAY_S
    return "%02d:%02d" % (seconds // 3600, seconds % 3600 // 60)


def fmt_countdown(seconds):
    """Seconds -> 'HH h MM m'. Minutes round up so it matches the clock
    (09:19 -> 12:37 reads '03 h 18 m'); never negative."""
    if seconds < 0:
        seconds = 0
    minutes = (seconds + 59) // 60
    return "%02d h %02d m" % (minutes // 60, minutes % 60)


def next_prayer(now_s, today, tomorrow=None):
    """Return ``(index, prayer_s)`` of the next prayer.

    ``prayer_s`` is relative to today's midnight, so it is >= 86400 when the
    next prayer is tomorrow's Fajr. Without tomorrow's times, today's Fajr is
    used as the estimate (it moves by only a minute or two per day).
    """
    for i in range(5):
        if today[i] > now_s:
            return i, today[i]
    return 0, DAY_S + (tomorrow if tomorrow else today)[0]


def adhan_due(now_s, prayer_s, lead_s):
    """True from ``lead_s`` seconds before the prayer until the prayer."""
    return prayer_s - lead_s <= now_s < prayer_s


class AdhanTrigger:
    """Fires once per prayer, from ``lead_s`` seconds before it starts."""

    def __init__(self, lead_s):
        self.lead_s = lead_s
        self.key = None
        self.armed = False
        self.changed = False

    def update(self, idx, prayer_s, now_s):
        """Feed the current next prayer; True exactly once when the adhan is due.

        ``changed`` tells whether the next prayer differs from the last call.
        """
        key = (idx, prayer_s)
        self.changed = key != self.key
        if self.changed:
            self.key = key
            self.armed = True
        if self.armed and adhan_due(now_s, prayer_s, self.lead_s):
            self.armed = False
            return True
        return False


def format_dates(date):
    """Aladhan 'date' dict -> ('08 November 2026', '25 Jumada al-awwal 1448')."""
    gregorian = date["gregorian"]
    hijri = date["hijri"]
    return (
        str(gregorian["day"]) + " " + gregorian["month"]["en"] + " " + str(gregorian["year"]),
        str(hijri["day"]) + " " + HIJRI_MONTHS[int(hijri["month"]["number"]) - 1] + " " + str(hijri["year"]),
    )


def parse_day(data, ymd=None):
    """Reduce Aladhan's ``data`` dict to ``([5 seconds], gregorian, hijri)``.

    If ``ymd`` (year, month, day) is given, the response must be for that day.
    """
    if ymd is not None:
        gregorian = data["date"]["gregorian"]
        got = (int(gregorian["year"]), int(gregorian["month"]["number"]), int(gregorian["day"]))
        if got != tuple(ymd):
            raise ValueError("Aladhan returned %s, wanted %s" % (got, tuple(ymd)))
    timings = data["timings"]
    greg, hijri = format_dates(data["date"])
    return [parse_hhmm(timings[name]) for name in PRAYERS], greg, hijri


def urlquote(text):
    """Percent-encode ``text`` for use in a URL query string."""
    out = ""
    for byte in text.encode("utf-8"):
        char = chr(byte)
        out += char if char in _URL_SAFE else "%%%02X" % byte
    return out


def adhan_label(filename):
    """'AhmadAlNafees.wav' -> 'Ahmad Al Nafees'."""
    name = filename.rsplit(".", 1)[0]
    out = ""
    prev = ""
    for char in name:
        if out and char.isupper() and not prev.isupper():
            out += " "
        out += char
        prev = char
    return out


def cycle(items, current):
    """Item after ``current`` in ``items`` (wrapping); first item if unknown."""
    if not items:
        return current
    if current in items:
        return items[(items.index(current) + 1) % len(items)]
    return items[0]
