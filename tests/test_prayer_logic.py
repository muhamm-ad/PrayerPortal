"""Host-side tests for sd/prayer_logic.py (run: python3 -I -m unittest discover -s tests)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sd"))

import prayer_logic as pl  # noqa: E402

LEAD = 300
# Times from the bug report (Montreal), as seconds since midnight.
TODAY = [pl.parse_hhmm(t) for t in ("05:40", "12:42", "15:48", "18:21", "19:42")]
TOMORROW = [pl.parse_hhmm(t) for t in ("05:41", "12:42", "15:46", "18:19", "19:40")]


def hms(h, m=0, s=0):
    return h * 3600 + m * 60 + s


SAMPLE = {
    "timings": {
        "Fajr": "05:40 (EDT)", "Sunrise": "07:06 (EDT)", "Dhuhr": "12:42 (EDT)",
        "Asr": "15:48 (EDT)", "Sunset": "18:21 (EDT)", "Maghrib": "18:21 (EDT)",
        "Isha": "19:42 (EDT)",
    },
    "date": {
        "gregorian": {"day": "08", "month": {"number": 10, "en": "October"}, "year": "2026"},
        "hijri": {"day": "26", "month": {"number": 4, "en": "x"}, "year": "1448"},
    },
}


class Formatting(unittest.TestCase):
    def test_parse_hhmm(self):
        self.assertEqual(pl.parse_hhmm("05:40"), hms(5, 40))
        self.assertEqual(pl.parse_hhmm("19:42 (EDT)"), hms(19, 42))
        self.assertEqual(pl.parse_hhmm("00:00"), 0)

    def test_fmt_hm_wraps(self):
        self.assertEqual(pl.fmt_hm(hms(5, 35)), "05:35")
        self.assertEqual(pl.fmt_hm(pl.DAY_S + hms(5, 35)), "05:35")
        self.assertEqual(pl.fmt_hm(0), "00:00")

    def test_fmt_countdown(self):
        self.assertEqual(pl.fmt_countdown(hms(3, 18)), "03 h 18 m")
        self.assertEqual(pl.fmt_countdown(hms(3, 17, 30)), "03 h 18 m")  # rounds up
        self.assertEqual(pl.fmt_countdown(1), "00 h 01 m")
        self.assertEqual(pl.fmt_countdown(0), "00 h 00 m")
        self.assertEqual(pl.fmt_countdown(-42), "00 h 00 m")

    def test_urlquote(self):
        self.assertEqual(pl.urlquote("Montreal"), "Montreal")
        self.assertEqual(pl.urlquote("New York"), "New%20York")
        self.assertEqual(pl.urlquote("Saint-Étienne"), "Saint-%C3%89tienne")

    def test_adhan_label(self):
        self.assertEqual(pl.adhan_label("AhmadAlNafees.wav"), "Ahmad Al Nafees")
        self.assertEqual(pl.adhan_label("MisharyRashidAlafasy2.wav"), "Mishary Rashid Alafasy2")
        self.assertEqual(pl.adhan_label("KarlJenkins.wav"), "Karl Jenkins")

    def test_cycle(self):
        items = ["a.wav", "b.wav", "c.wav"]
        self.assertEqual(pl.cycle(items, "a.wav"), "b.wav")
        self.assertEqual(pl.cycle(items, "c.wav"), "a.wav")
        self.assertEqual(pl.cycle(items, "gone.wav"), "a.wav")
        self.assertEqual(pl.cycle([], "x.wav"), "x.wav")


class ParseDay(unittest.TestCase):
    def test_parse(self):
        times, greg, hijri = pl.parse_day(SAMPLE, (2026, 10, 8))
        self.assertEqual(times, TODAY)
        self.assertEqual(greg, "08 October 2026")
        self.assertEqual(hijri, "26 Rabi' al-thani 1448")

    def test_date_mismatch(self):
        with self.assertRaises(ValueError):
            pl.parse_day(SAMPLE, (2026, 10, 9))


class NextPrayer(unittest.TestCase):
    def test_bug_report_case(self):
        """09:19 must give Dhuhr / adhan 12:37 / 03 h 18 m (was Fajr / 05:35 / 20 h 20 m)."""
        for now in (hms(9, 19, 0), hms(9, 19, 30), hms(9, 19, 59)):
            idx, prayer_s = pl.next_prayer(now, TODAY, TOMORROW)
            self.assertEqual(pl.PRAYERS[idx], "Dhuhr")
            adhan_s = prayer_s - LEAD
            self.assertEqual(pl.fmt_hm(adhan_s), "12:37")
            self.assertEqual(pl.fmt_countdown(adhan_s - now), "03 h 18 m")

    def test_before_fajr(self):
        self.assertEqual(pl.next_prayer(hms(4), TODAY, TOMORROW), (0, TODAY[0]))

    def test_prayer_second_counts_as_passed(self):
        self.assertEqual(pl.next_prayer(TODAY[1], TODAY, TOMORROW)[0], 2)

    def test_after_isha_uses_tomorrow(self):
        idx, prayer_s = pl.next_prayer(hms(21), TODAY, TOMORROW)
        self.assertEqual((idx, prayer_s), (0, pl.DAY_S + TOMORROW[0]))
        self.assertEqual(pl.fmt_countdown(prayer_s - LEAD - hms(21)), "08 h 36 m")

    def test_after_isha_without_tomorrow_falls_back(self):
        self.assertEqual(pl.next_prayer(hms(21), TODAY), (0, pl.DAY_S + TODAY[0]))


class AdhanTriggerTest(unittest.TestCase):
    def test_fires_once_inside_window(self):
        trig = pl.AdhanTrigger(LEAD)
        fired = [now for now in range(hms(12, 30), hms(12, 45))
                 if trig.update(1, TODAY[1], now)]
        self.assertEqual(fired, [TODAY[1] - LEAD])

    def test_starting_inside_window_fires_immediately(self):
        trig = pl.AdhanTrigger(LEAD)
        self.assertTrue(trig.update(1, TODAY[1], TODAY[1] - 100))
        self.assertFalse(trig.update(1, TODAY[1], TODAY[1] - 99))

    def test_not_fired_outside_window(self):
        trig = pl.AdhanTrigger(LEAD)
        self.assertFalse(trig.update(1, TODAY[1], hms(9, 19)))
        self.assertFalse(trig.update(1, TODAY[1], TODAY[1] - LEAD - 1))


class FullDaySimulation(unittest.TestCase):
    """Replays the main loop second by second, including the midnight swap."""

    def run_sim(self, start_s, end_s):
        times, tomorrow = TODAY, TOMORROW
        trig = pl.AdhanTrigger(LEAD)
        shown, fired, offset = [], [], 0
        for abs_s in range(start_s, end_s):
            now_s = abs_s - offset
            if now_s >= pl.DAY_S:  # local midnight: tomorrow becomes today
                offset += pl.DAY_S
                now_s -= pl.DAY_S
                times, tomorrow = tomorrow, TOMORROW
            idx, prayer_s = pl.next_prayer(now_s, times, tomorrow)
            countdown = prayer_s - LEAD - now_s
            if trig.update(idx, prayer_s, now_s):
                fired.append((abs_s, idx))
            if not shown or shown[-1] != idx:
                shown.append(idx)
            self.assertGreaterEqual(prayer_s - now_s, 1)
            self.assertLessEqual(prayer_s - now_s, pl.DAY_S)
            self.assertTrue(pl.fmt_countdown(countdown).endswith(" m"))
        return shown, fired

    def test_start_before_fajr_never_sticks_on_fajr(self):
        """The reported bug: once Fajr was 'next', it stayed 'next' forever."""
        shown, fired = self.run_sim(hms(4), pl.DAY_S + hms(1))
        self.assertEqual(shown, [0, 1, 2, 3, 4, 0])
        self.assertEqual([i for _, i in fired], [0, 1, 2, 3, 4])
        self.assertEqual([s for s, _ in fired], [t - LEAD for t in TODAY])

    def test_start_mid_morning(self):
        shown, fired = self.run_sim(hms(9, 19), pl.DAY_S + hms(7))
        # Ends at 07:00 on day 2: Fajr (05:41) has passed, so Dhuhr is next again.
        self.assertEqual(shown, [1, 2, 3, 4, 0, 1])
        self.assertEqual([i for _, i in fired], [1, 2, 3, 4, 0])  # Fajr adhan fires after midnight

    def test_start_after_isha(self):
        shown, fired = self.run_sim(hms(21), pl.DAY_S + hms(7))
        self.assertEqual(shown, [0, 1])  # Fajr, then Dhuhr once Fajr has passed
        self.assertEqual(len(fired), 1)


if __name__ == "__main__":
    unittest.main()
