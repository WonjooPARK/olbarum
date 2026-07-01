"""Check Naver Booking availability through the same GraphQL call the page uses."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Any, Iterable

from backend.settings import load_naver_credentials


BUSINESS_ID = "798392"
BUSINESS_TYPE_ID = 13
GRAPHQL_URL = "https://m.booking.naver.com/graphql?opName=hourlySchedule"
DEFAULT_CODEX_NODE = Path(
    r"C:\Users\wjpark\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
)


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    biz_item_id: str


PRODUCTS = {
    "director": Product("director", "BodyCare 대표원장 '황세영'", "4725840"),
    "manager": Product("manager", "BodyCare 실장 '권혁민'", "5000239"),
    "sunday": Product("sunday", "'일요일' 관리예약 전용", "6775999"),
    "trial30": Product(
        "trial30",
        "30분 무료체험 (스포츠마사지・통증원인분석・체형교정상담)",
        "6155711",
    ),
}


HOURLY_SCHEDULE_QUERY = """
query hourlySchedule($scheduleParams: ScheduleParams) {
  schedule(input: $scheduleParams) {
    bizItemSchedule {
      hourly {
        id
        unitStartDateTime
        unitStartTime
        unitBookingCount
        unitStock
        bookingCount
        occupiedBookingCount
        stock
        isBusinessDay
        isSaleDay
        isUnitSaleDay
        isUnitBusinessDay
        isHoliday
        duration
        minBookingCount
        maxBookingCount
        desc
      }
    }
  }
}
""".strip()


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    if end < start:
        raise ValueError("end date must be on or after start date")
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def month_window(day: dt.date) -> tuple[str, str]:
    last_day = calendar.monthrange(day.year, day.month)[1]
    start = dt.date(day.year, day.month, 1)
    # Naver's page asks through the first day of the next month at 23:59:59.
    next_month = start + dt.timedelta(days=last_day)
    return (
        f"{start.isoformat()}T00:00:00",
        f"{next_month.isoformat()}T23:59:59",
    )


def booking_url(product: Product, day: dt.date | None = None) -> str:
    params = {
        "area": "pll",
        "lang": "ko",
        "service-target": "map-pc",
        "theme": "place",
    }
    if day is not None:
        params["startDate"] = day.isoformat()
    return (
        f"https://m.booking.naver.com/booking/13/bizes/{BUSINESS_ID}"
        f"/items/{product.biz_item_id}?{urllib.parse.urlencode(params)}"
    )


def request_monthly_schedule(product: Product, day: dt.date) -> list[dict[str, Any]]:
    start_date_time, end_date_time = month_window(day)
    payload = {
        "operationName": "hourlySchedule",
        "variables": {
            "scheduleParams": {
                "businessTypeId": BUSINESS_TYPE_ID,
                "businessId": BUSINESS_ID,
                "bizItemId": product.biz_item_id,
                "startDateTime": start_date_time,
                "endDateTime": end_date_time,
                "fixedTime": True,
                "includesHolidaySchedules": True,
            }
        },
        "query": HOURLY_SCHEDULE_QUERY,
    }
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://m.booking.naver.com",
            "Referer": booking_url(product, day),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Naver returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to Naver Booking: {exc}") from exc

    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))

    hourly = (
        data.get("data", {})
        .get("schedule", {})
        .get("bizItemSchedule", {})
        .get("hourly")
    )
    return hourly or []


def remaining_stock(slot: dict[str, Any]) -> int:
    unit_stock = slot.get("unitStock")
    unit_booking_count = slot.get("unitBookingCount") or 0
    stock = slot.get("stock")
    booking_count = slot.get("bookingCount") or 0
    occupied_booking_count = slot.get("occupiedBookingCount") or 0

    unit_remaining = (
        unit_stock - unit_booking_count if isinstance(unit_stock, int) else 1_000_000
    )
    total_remaining = (
        stock - booking_count - occupied_booking_count
        if isinstance(stock, int)
        else 1_000_000
    )
    return min(unit_remaining, total_remaining)


def duration_slot_count(option_minutes: int) -> int:
    if option_minutes <= 0 or option_minutes % 30 != 0:
        raise ValueError("option minutes must be a positive 30-minute multiple")
    return option_minutes // 30


def slot_start_datetime(slot: dict[str, Any]) -> dt.datetime | None:
    raw_value = slot.get("unitStartTime") or slot.get("unitStartDateTime")
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.replace(" ", "T")
    try:
        return dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def is_available(slot: dict[str, Any], selected_count: int = 1) -> bool:
    if not all(
        slot.get(key) is True
        for key in (
            "isBusinessDay",
            "isSaleDay",
            "isUnitSaleDay",
            "isUnitBusinessDay",
        )
    ):
        return False
    if slot.get("isHoliday") is True:
        return False
    min_count = slot.get("minBookingCount") or 0
    max_count = slot.get("maxBookingCount") or 0
    remaining = remaining_stock(slot)
    return (
        remaining >= selected_count
        and (not min_count or remaining >= min_count)
        and (not max_count or selected_count <= max_count)
    )


def available_slots_from_schedule(
    product: Product,
    day: dt.date,
    schedule: list[dict[str, Any]],
    option_minutes: int = 60,
) -> list[dict[str, Any]]:
    prefix = day.isoformat()
    required_slots = duration_slot_count(option_minutes)
    raw_slots = [
        slot
        for slot in schedule
        if (slot.get("unitStartTime") or "").startswith(prefix)
    ]
    slots_by_start = {
        start: slot
        for slot in raw_slots
        if (start := slot_start_datetime(slot)) is not None
    }
    slots = []
    for start in sorted(slots_by_start):
        segment = [
            slots_by_start.get(start + dt.timedelta(minutes=30 * offset))
            for offset in range(required_slots)
        ]
        if all(slot is not None and is_available(slot) for slot in segment):
            remaining = min(remaining_stock(slot) for slot in segment if slot is not None)
            slots.append(
                {
                    "product": product.slug,
                    "productName": product.name,
                    "date": prefix,
                    "time": start.strftime("%H:%M"),
                    "endTime": (start + dt.timedelta(minutes=option_minutes)).strftime(
                        "%H:%M"
                    ),
                    "dateTime": start.isoformat(),
                    "optionMinutes": option_minutes,
                    "requiredSlots": required_slots,
                    "segmentTimes": [
                        (start + dt.timedelta(minutes=30 * offset)).strftime("%H:%M")
                        for offset in range(required_slots)
                    ],
                    "remaining": remaining,
                    "url": booking_url(product, day),
                }
            )
    return slots


def available_slots(
    product: Product, day: dt.date, option_minutes: int = 60
) -> list[dict[str, Any]]:
    return available_slots_from_schedule(
        product, day, request_monthly_schedule(product, day), option_minutes
    )


def available_slots_for_range(
    products: Iterable[Product],
    start: dt.date,
    end: dt.date,
    option_minutes: int = 60,
) -> list[dict[str, Any]]:
    slots = []
    schedule_cache: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for product in products:
        for day in date_range(start, end):
            cache_key = (product.biz_item_id, day.year, day.month)
            if cache_key not in schedule_cache:
                schedule_cache[cache_key] = request_monthly_schedule(product, day)
            slots.extend(
                available_slots_from_schedule(
                    product, day, schedule_cache[cache_key], option_minutes
                )
            )
    return slots


def selected_products(value: str) -> list[Product]:
    if value == "all":
        return list(PRODUCTS.values())
    if value not in PRODUCTS:
        choices = ", ".join(["all", *PRODUCTS])
        raise ValueError(f"unknown product '{value}'. Choose one of: {choices}")
    return [PRODUCTS[value]]


def find_node_executable() -> str | None:
    configured = os.environ.get("NODE_EXE")
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)

    from_path = shutil.which("node")
    if from_path:
        return from_path

    if DEFAULT_CODEX_NODE.exists():
        return str(DEFAULT_CODEX_NODE)

    return None


def reserve_prepare_command(
    date: dt.date,
    product: str,
    time: str,
    option_minutes: int,
    *,
    headless: bool = False,
    auto_required: bool = True,
) -> list[str]:
    node_executable = find_node_executable() or "node"
    command = [
        node_executable,
        "backend/naver_reserve_prepare.cjs",
        "--date",
        date.isoformat(),
        "--product",
        product,
        "--time",
        time,
        "--option",
        str(option_minutes),
    ]
    if headless:
        command.append("--headless")
    if not auto_required:
        command.append("--no-auto-required")
    return command


def run_reserve_prepare(args: argparse.Namespace) -> int:
    credentials = load_naver_credentials()
    if not credentials.is_complete:
        print(
            "error: NAVER_ID/NAVER_PASSWORD are not configured. "
            "Create .env from .env.example first.",
            file=sys.stderr,
        )
        return 1
    command = reserve_prepare_command(
        args.date,
        args.product,
        args.time,
        args.option,
        headless=args.headless,
        auto_required=not args.no_auto_required,
    )
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        print(
            "error: node executable was not found. Install Node.js or set NODE_EXE "
            "to node.exe path.",
            file=sys.stderr,
        )
        return 1
    return completed.returncode


def print_slots(slots: list[dict[str, Any]]) -> None:
    if not slots:
        print("가능한 시간이 없습니다.")
        return
    for slot in slots:
        segment = ",".join(slot["segmentTimes"])
        print(
            f"{slot['date']} {slot['time']}~{slot['endTime']} | "
            f"{slot['optionMinutes']}분 | 선택 {segment} | "
            f"{slot['product']} | {slot['productName']} | 잔여 {slot['remaining']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Olbarum Naver Booking slots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-products", help="show configured booking products")
    subparsers.add_parser("config", help="show local credential configuration status")

    check = subparsers.add_parser("check", help="check available slots")
    check.add_argument("--start", required=True, type=parse_date)
    check.add_argument("--end", required=True, type=parse_date)
    check.add_argument("--product", default="director", help="product slug or all")
    check.add_argument("--option", default=60, type=int, choices=[60, 90, 120])
    check.add_argument("--json", action="store_true", help="print JSON output")

    open_page = subparsers.add_parser("open", help="open a booking page")
    open_page.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    open_page.add_argument("--date", type=parse_date)

    reserve = subparsers.add_parser(
        "reserve",
        help="prepare a reservation in Chrome, stopping before final submission",
    )
    reserve.add_argument("--date", required=True, type=parse_date)
    reserve.add_argument("--product", default="director", choices=sorted(PRODUCTS))
    reserve.add_argument("--time", required=True, help="24-hour time, e.g. 13:30")
    reserve.add_argument("--option", required=True, type=int, choices=[60, 90, 120])
    reserve.add_argument("--headless", action="store_true")
    reserve.add_argument("--no-auto-required", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-products":
        for product in PRODUCTS.values():
            print(f"{product.slug}: {product.name} (bizItemId={product.biz_item_id})")
        return 0

    if args.command == "config":
        credentials = load_naver_credentials()
        print(f"NAVER_ID: {credentials.masked_user_id}")
        print(f"NAVER_PASSWORD: {'set' if credentials.password else '(not set)'}")
        print(f"ready_for_login: {str(credentials.is_complete).lower()}")
        return 0

    if args.command == "open":
        url = booking_url(PRODUCTS[args.product], args.date)
        print(url)
        webbrowser.open(url)
        return 0

    if args.command == "reserve":
        return run_reserve_prepare(args)

    try:
        slots = available_slots_for_range(
            selected_products(args.product), args.start, args.end, args.option
        )
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(slots, ensure_ascii=False, indent=2))
    else:
        print_slots(slots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
