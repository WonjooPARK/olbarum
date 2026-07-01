import datetime as dt
from pathlib import Path
import unittest

from backend import naver_booking_api


def make_slot(time: str, unit_stock: int = 1, date: str = "2026-07-22"):
    return {
        "unitStartDateTime": f"{date}T{time}:00",
        "unitStartTime": f"{date} {time}:00",
        "isBusinessDay": True,
        "isSaleDay": True,
        "isUnitSaleDay": True,
        "isUnitBusinessDay": True,
        "isHoliday": False,
        "unitStock": unit_stock,
        "unitBookingCount": 0,
        "stock": None,
        "bookingCount": 0,
        "occupiedBookingCount": 0,
        "minBookingCount": 1,
        "maxBookingCount": 4,
    }


class NaverBookingBrowserTests(unittest.TestCase):
    def test_director_product_id_is_correct(self):
        product = naver_booking_api.PRODUCTS["director"]

        self.assertEqual(product.name, "BodyCare 대표원장 '황세영'")
        self.assertEqual(product.biz_item_id, "4725840")

    def test_booking_url_contains_start_date(self):
        url = naver_booking_api.booking_url(
            naver_booking_api.PRODUCTS["director"], dt.date(2026, 7, 22)
        )

        self.assertIn("/bizes/798392/items/4725840", url)
        self.assertIn("startDate=2026-07-22", url)

    def test_date_range_inclusive(self):
        days = list(
            naver_booking_api.date_range(
                dt.date(2026, 7, 22), dt.date(2026, 7, 24)
            )
        )

        self.assertEqual(
            days,
            [
                dt.date(2026, 7, 22),
                dt.date(2026, 7, 23),
                dt.date(2026, 7, 24),
            ],
        )

    def test_selected_products_rejects_unknown_slug(self):
        with self.assertRaises(ValueError):
            naver_booking_api.selected_products("missing")

    def test_month_window_matches_naver_calendar_request(self):
        self.assertEqual(
            naver_booking_api.month_window(dt.date(2026, 7, 22)),
            ("2026-07-01T00:00:00", "2026-08-01T23:59:59"),
        )

    def test_available_stock_uses_unit_stock_when_total_stock_is_null(self):
        slot = {
            "isBusinessDay": True,
            "isSaleDay": True,
            "isUnitSaleDay": True,
            "isUnitBusinessDay": True,
            "isHoliday": False,
            "unitStock": 1,
            "unitBookingCount": 0,
            "stock": None,
            "bookingCount": 5,
            "occupiedBookingCount": 0,
            "minBookingCount": 1,
            "maxBookingCount": 4,
        }

        self.assertTrue(naver_booking_api.is_available(slot))

    def test_available_slots_require_consecutive_30_minute_units(self):
        original = naver_booking_api.request_monthly_schedule
        naver_booking_api.request_monthly_schedule = lambda product, day: [
            make_slot("13:30"),
            make_slot("14:30"),
        ]
        try:
            slots = naver_booking_api.available_slots(
                naver_booking_api.PRODUCTS["director"], dt.date(2026, 7, 22), 60
            )
        finally:
            naver_booking_api.request_monthly_schedule = original

        self.assertEqual(slots, [])

    def test_available_slots_include_required_segment_times(self):
        original = naver_booking_api.request_monthly_schedule
        naver_booking_api.request_monthly_schedule = lambda product, day: [
            make_slot("13:30"),
            make_slot("14:00"),
            make_slot("14:30"),
            make_slot("15:00"),
        ]
        try:
            slots = naver_booking_api.available_slots(
                naver_booking_api.PRODUCTS["director"], dt.date(2026, 7, 22), 90
            )
        finally:
            naver_booking_api.request_monthly_schedule = original

        self.assertEqual(slots[0]["time"], "13:30")
        self.assertEqual(slots[0]["requiredSlots"], 3)
        self.assertEqual(slots[0]["segmentTimes"], ["13:30", "14:00", "14:30"])

    def test_available_slots_for_range_reuses_monthly_schedule(self):
        calls = []
        original = naver_booking_api.request_monthly_schedule

        def fake_request(product, day):
            calls.append(day)
            return [
                make_slot("13:30", date="2026-07-15"),
                make_slot("14:00", date="2026-07-15"),
                make_slot("10:00", date="2026-07-31"),
                make_slot("10:30", date="2026-07-31"),
            ]

        naver_booking_api.request_monthly_schedule = fake_request
        try:
            slots = naver_booking_api.available_slots_for_range(
                [naver_booking_api.PRODUCTS["director"]],
                dt.date(2026, 7, 15),
                dt.date(2026, 7, 31),
                60,
            )
        finally:
            naver_booking_api.request_monthly_schedule = original

        self.assertEqual(len(calls), 1)
        self.assertEqual([slot["date"] for slot in slots], ["2026-07-15", "2026-07-31"])
        self.assertEqual([slot["segmentTimes"] for slot in slots], [["13:30", "14:00"], ["10:00", "10:30"]])

    def test_reserve_prepare_command_defaults_to_safe_prepare(self):
        command = naver_booking_api.reserve_prepare_command(
            dt.date(2026, 7, 22),
            "director",
            "13:30",
            90,
        )

        self.assertIn(Path(command[0]).name.lower(), {"node", "node.exe"})
        self.assertEqual(command[1], "backend/naver_reserve_prepare.cjs")
        self.assertIn("--date", command)
        self.assertIn("2026-07-22", command)
        self.assertNotIn("--submit", command)


if __name__ == "__main__":
    unittest.main()
