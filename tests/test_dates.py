"""Real dates for `rate once` and `rate schedule`: --time takes HH:MM, 2026-11-03T20:00, "03/11 20:00" and a weekday name
in English or Italian (always the NEXT one, never today); a date in the past is refused. The tests give the parser a fixed
"now" and never create a real Windows task (schtasks is replaced). Run: python -m unittest discover tests"""

import os
import types
import unittest
from datetime import datetime
from unittest import mock

from test_quotient import Base, pv  # noqa: E402
from quotient_lib import q_schedules as qs  # noqa: E402

NOW = datetime(2026, 11, 1, 19, 48, 30)   # Sunday 01/11/2026, 19:48:30


def parse(text, now=NOW):
    return pv.parse_when(text, now)


class TestParseWhen(unittest.TestCase):
    def test_the_fixed_now_is_a_sunday(self):
        self.assertEqual(NOW.weekday(), 6)

    def test_hh_mm_alone_works_as_before(self):
        self.assertEqual(parse("20:00"), datetime(2026, 11, 1, 20, 0))        # later today
        self.assertEqual(parse("19:00"), datetime(2026, 11, 2, 19, 0))        # passed: tomorrow
        self.assertEqual(parse("19:48"), datetime(2026, 11, 2, 19, 48))       # this very minute is already past
        self.assertEqual(parse("9:05"), datetime(2026, 11, 2, 9, 5))
        self.assertEqual(parse(" 03:00 "), datetime(2026, 11, 2, 3, 0))
        self.assertEqual(parse("23:59", datetime(2026, 12, 31, 23, 59, 30)), datetime(2027, 1, 1, 23, 59))

    def test_tomorrow_is_the_same_clock_time_on_the_next_calendar_day(self):
        # the clocks went back on 25/10/2026 in Italy: tomorrow at 03:00 is 03:00 on the wall, not 86400 s later
        self.assertEqual(parse("03:00", datetime(2026, 10, 24, 23, 0)), datetime(2026, 10, 25, 3, 0))
        self.assertEqual(parse("02:00", datetime(2026, 10, 25, 22, 0)), datetime(2026, 10, 26, 2, 0))

    def test_an_iso_date(self):
        self.assertEqual(parse("2026-11-03T20:00"), datetime(2026, 11, 3, 20, 0))
        self.assertEqual(parse("2026-11-03t20:00"), datetime(2026, 11, 3, 20, 0))
        self.assertEqual(parse("2026-11-03 20:00"), datetime(2026, 11, 3, 20, 0))
        self.assertEqual(parse("2027-02-28T08:05"), datetime(2027, 2, 28, 8, 5))
        self.assertEqual(parse("2026-11-01T19:49"), datetime(2026, 11, 1, 19, 49))   # today, a minute from now

    def test_day_and_month(self):
        self.assertEqual(parse("03/11 20:00"), datetime(2026, 11, 3, 20, 0))        # this year
        self.assertEqual(parse("3/11 8:30"), datetime(2026, 11, 3, 8, 30))
        self.assertEqual(parse("24/12 18:00"), datetime(2026, 12, 24, 18, 0))
        self.assertEqual(parse("03/11/2027 20:00"), datetime(2027, 11, 3, 20, 0))    # a year given
        self.assertEqual(parse("29/02/2028 10:00"), datetime(2028, 2, 29, 10, 0))
        self.assertEqual(parse("03/11   20:00"), datetime(2026, 11, 3, 20, 0))       # extra spaces

    def test_a_weekday_in_english_or_italian_is_the_next_one(self):
        want = datetime(2026, 11, 3, 20, 0)                                          # Tuesday 03/11
        for text in ("tuesday 20:00", "Tuesday 20:00", "TUESDAY 20:00", "martedì 20:00", "martedi 20:00", "Martedì 20:00",
                     "MARTEDI 20:00", "martedi' 20:00", "martedì 20:00", "tue 20:00", "mar 20:00"):
            self.assertEqual(parse(text), want, text)
        self.assertEqual(parse("lunedì 08:30"), datetime(2026, 11, 2, 8, 30))        # tomorrow
        self.assertEqual(parse("monday 8:30"), datetime(2026, 11, 2, 8, 30))
        self.assertEqual(parse("mercoledì 9:00"), datetime(2026, 11, 4, 9, 0))
        self.assertEqual(parse("giovedì 9:00"), datetime(2026, 11, 5, 9, 0))
        self.assertEqual(parse("venerdì 9:00"), datetime(2026, 11, 6, 9, 0))
        self.assertEqual(parse("sabato 9:00"), datetime(2026, 11, 7, 9, 0))
        self.assertEqual(parse("saturday 9:00"), datetime(2026, 11, 7, 9, 0))

    def test_a_weekday_is_never_today(self):
        # now is Sunday 19:48: "sunday 20:00" is later today, and still means next Sunday
        self.assertEqual(parse("sunday 20:00"), datetime(2026, 11, 8, 20, 0))
        self.assertEqual(parse("domenica 20:00"), datetime(2026, 11, 8, 20, 0))
        self.assertEqual(parse("domenica 19:00"), datetime(2026, 11, 8, 19, 0))
        self.assertEqual(parse("dom 23:59"), datetime(2026, 11, 8, 23, 59))

    def test_every_weekday_is_between_one_and_seven_days_ahead(self):
        for day in range(7):
            for words in qs.WEEKDAY_WORDS[day]:
                moment = parse("%s 10:00" % words)
                self.assertEqual(moment.weekday(), day, words)
                self.assertTrue(1 <= (moment.date() - NOW.date()).days <= 7, words)
        for day in range(7):                       # from every day of a week
            for ahead in range(7):
                now = datetime(2026, 11, 2 + ahead, 12, 0)
                moment = pv.parse_when(qs.WEEKDAYS[day] + " 10:00", now)
                self.assertTrue(1 <= (moment.date() - now.date()).days <= 7)
                self.assertEqual(moment.weekday(), day)

    def test_a_weekday_across_the_end_of_a_month_and_year(self):
        self.assertEqual(pv.parse_when("friday 20:00", datetime(2026, 12, 30, 9, 0)), datetime(2027, 1, 1, 20, 0))
        self.assertEqual(pv.parse_when("tuesday 20:00", datetime(2027, 2, 27, 9, 0)), datetime(2027, 3, 2, 20, 0))

    def test_weekday_names(self):
        self.assertEqual(pv.weekday_of("martedì"), 1)
        self.assertEqual(pv.weekday_of("Sunday"), 6)
        self.assertEqual(pv.weekday_of("lunedi"), 0)
        self.assertIsNone(pv.weekday_of("march"))
        self.assertIsNone(pv.weekday_of("tomorrow"))
        self.assertIsNone(pv.weekday_of(""))

    def test_the_past_is_refused_with_a_clear_message(self):
        for text in ("2026-10-31T20:00", "2026-11-01T19:48", "2026-11-01T08:00", "01/11 19:00", "31/10 20:00",
                     "01/11/2026 19:48", "2025-11-03T20:00"):
            with self.assertRaises(ValueError, msg=text) as raised:
                parse(text)
            self.assertIn("in the past", str(raised.exception), text)
            self.assertIn("Sunday 01/11 at 19:48", str(raised.exception), text)    # now, in words
        with self.assertRaises(ValueError) as raised:
            parse("2026-10-31T20:00")
        self.assertIn("Saturday 31/10 at 20:00", str(raised.exception))             # what was asked, in words

    def test_a_past_day_without_a_year_says_how_to_ask_for_next_year(self):
        with self.assertRaises(ValueError) as raised:
            parse("03/10 20:00")
        self.assertIn("03/10/2027 20:00", str(raised.exception))
        with self.assertRaises(ValueError) as raised:
            parse("03/10/2026 20:00")                        # a year was given: no such hint
        self.assertNotIn("write the year", str(raised.exception))

    def test_what_cannot_be_read_is_refused_with_the_formats(self):
        for text in ("", None, "tuesday", "martedì", "20", "20:60", "24:00", "tuesday 25:00", "next tuesday 20:00", "tomorrow 20:00",
                     "domani 20:00", "2026-11-03", "03/11", "2026/11/03 20:00", "03-11 20:00", "03/11/26 20:00",
                     "march 20:00", "20.00", "8pm"):
            with self.assertRaises(ValueError, msg=repr(text)) as raised:
                parse(text)
            self.assertIn("cannot read the time", str(raised.exception), repr(text))
            self.assertIn("tuesday 20:00", str(raised.exception))

    def test_a_date_that_does_not_exist_is_refused(self):
        for text in ("31/02 20:00", "2026-02-30T20:00", "29/02/2027 10:00", "00/11 20:00", "10/13 20:00", "2026-13-01T20:00"):
            with self.assertRaises(ValueError, msg=text) as raised:
                parse(text)
            self.assertIn("not a real date", str(raised.exception), text)

    def test_the_date_in_words(self):
        self.assertEqual(pv.describe(datetime(2026, 11, 3, 20, 0), NOW), "Tuesday 03/11 at 20:00")
        self.assertEqual(pv.describe(datetime(2027, 11, 3, 9, 5), NOW), "Wednesday 03/11/2027 at 09:05")
        self.assertEqual(pv.describe(NOW, NOW), "Sunday 01/11 at 19:48")

    def test_next_time_stops_with_a_clear_message(self):
        self.assertEqual(pv.next_time("tuesday 20:00", NOW), datetime(2026, 11, 3, 20, 0))
        with self.assertRaises(SystemExit) as raised:
            pv.next_time("2026-10-31T20:00", NOW)
        self.assertTrue(str(raised.exception).startswith("quotient: "))
        self.assertIn("in the past", str(raised.exception))
        with self.assertRaises(SystemExit) as raised:
            pv.next_time("whenever", NOW)
        self.assertIn("cannot read the time 'whenever'", str(raised.exception))

    def test_hh_mm_without_a_given_now_uses_the_clock(self):
        moment = pv.next_time(datetime.now().strftime("%H:%M"))        # this minute has begun: tomorrow
        self.assertGreater(moment, datetime.now())
        self.assertLess((moment - datetime.now()).total_seconds(), 86400 + 60)


class FakeSchtasks:
    """Stands in for subprocess.run: Task Scheduler is never touched; it keeps what was asked."""

    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")


class TestScheduleAnswer(Base):
    def run_schedule(self, at, once=True, now=NOW, **kwargs):
        fake = FakeSchtasks()
        with mock.patch.object(qs.subprocess, "run", fake):
            said = self.run_hook(lambda: pv.schedule("x", at, once, now=now, **kwargs), {})
        return said, fake

    @unittest.skipUnless(os.name == "nt", "the Windows branch")
    def test_the_answer_repeats_the_real_date_in_words(self):
        for at, words in (("tuesday 20:00", "Tuesday 03/11 at 20:00"), ("martedì 20:00", "Tuesday 03/11 at 20:00"),
                          ("2026-11-03T20:00", "Tuesday 03/11 at 20:00"), ("03/11 20:00", "Tuesday 03/11 at 20:00"),
                          ("20:00", "Sunday 01/11 at 20:00"), ("19:00", "Monday 02/11 at 19:00"),
                          ("03/11/2027 20:00", "Wednesday 03/11/2027 at 20:00")):
            said, fake = self.run_schedule(at)
            self.assertIn("Scheduled 'x' on %s." % words, said, at)
            self.assertEqual(len(fake.calls), 1)

    @unittest.skipUnless(os.name == "nt", "the Windows branch")
    def test_a_daily_task_says_from_which_day(self):
        said, fake = self.run_schedule("tuesday 20:00", once=False)
        self.assertIn("Scheduled 'x' every day from Tuesday 03/11 at 20:00.", said)
        xml = os.path.join(pv.rate_dir("x"), "task-daily.xml")
        with open(xml, encoding="utf-16") as f:
            text = f.read()
        self.assertIn("<CalendarTrigger><StartBoundary>2026-11-03T20:00:00</StartBoundary>", text)
        self.assertEqual(fake.calls[0][fake.calls[0].index("/TN") + 1], "quotient-x")

    @unittest.skipUnless(os.name == "nt", "the Windows branch")
    def test_the_task_starts_on_the_date_asked(self):
        said, fake = self.run_schedule("03/11 20:00")
        command = fake.calls[0]
        self.assertEqual(command[:3], ["schtasks", "/Create", "/F"])
        xml = command[command.index("/XML") + 1]
        with open(xml, encoding="utf-16") as f:
            text = f.read()
        self.assertIn("<TimeTrigger><StartBoundary>2026-11-03T20:00:00</StartBoundary><EndBoundary>2026-11-10T20:00:00</EndBoundary>", text)

    @unittest.skipUnless(os.name == "nt", "the Windows branch")
    def test_windows_task_names_stay_unique_per_date(self):
        names, files = set(), set()
        for at in ("03/11 20:00", "04/11 20:00", "2026-11-10T20:00", "tuesday 20:00", "03/11/2027 20:00", "20:00"):
            said, fake = self.run_schedule(at)
            command = fake.calls[0]
            names.add(command[command.index("/TN") + 1])
            files.add(command[command.index("/XML") + 1])
        # "tuesday 20:00" is the same moment as "03/11 20:00": the same task, replaced; the other five are different
        self.assertEqual(len(names), 5)
        self.assertEqual(len(files), 5)
        self.assertIn("quotient-x-once-20261103-2000", names)
        self.assertIn("quotient-x-once-20271103-2000", names)
        self.assertTrue(all(pv.once_task("x", n) for n in names))

    @unittest.skipUnless(os.name == "nt", "the Windows branch")
    def test_a_past_date_creates_no_task(self):
        fake = FakeSchtasks()
        with mock.patch.object(qs.subprocess, "run", fake):
            with self.assertRaises(SystemExit) as raised:
                pv.schedule("x", "2026-10-31T20:00", True, now=NOW)
        self.assertIn("in the past", str(raised.exception))
        self.assertEqual(fake.calls, [])
        self.assertFalse(os.path.exists(pv.rate_dir("x")))

    def test_without_windows_the_command_carries_the_whole_date(self):
        fake_os = types.SimpleNamespace(name="posix", path=os.path, makedirs=os.makedirs, environ=os.environ)
        with mock.patch.object(qs, "os", fake_os):
            said = self.run_hook(lambda: pv.schedule("x", "tuesday 20:00", True, now=NOW), {})
            daily = self.run_hook(lambda: pv.schedule("x", "tuesday 20:00", False, now=NOW), {})
        self.assertIn("on Tuesday 03/11 at 20:00", said)
        self.assertIn("| at -t 202611032000", said)
        self.assertIn("0 20 * * *", daily)
        self.assertIn("not from Tuesday 03/11 at 20:00", daily)

    def test_rate_once_takes_the_date_from_the_command_line(self):
        with mock.patch.object(qs, "schedule") as made:
            pv.main(["rate", "once", "book", "--time", "martedì 20:00"])
            pv.main(["rate", "schedule", "book", "--time", "2026-11-03T20:00"])
        self.assertEqual([(c.args[0], c.args[1], c.kwargs["once"]) for c in made.call_args_list],
                         [("book", "martedì 20:00", True), ("book", "2026-11-03T20:00", False)])

    def test_the_help_explains_the_dates(self):
        import contextlib
        import io
        for command in (["rate", "--help"], ["rate", "once", "--help"], ["rate", "schedule", "--help"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                pv.main(command)
            text = out.getvalue()
            for part in ("2026-11-03T20:00", "03/11 20:00", "tuesday 20:00", "NEXT one, never today", "in the past",
                         "Scheduled 'book' on Tuesday 03/11 at 20:00"):
                self.assertIn(part, text, "%s: %s" % (command, part))


if __name__ == "__main__":
    unittest.main()
