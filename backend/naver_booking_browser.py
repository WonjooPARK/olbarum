"""Check Naver Booking availability through the rendered booking page."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import webbrowser
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


BUSINESS_ID = "798392"


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


TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    if end < start:
        raise ValueError("end date must be on or after start date")
    days: list[dt.date] = []
    current = start
    while current <= end:
        days.append(current)
        current += dt.timedelta(days=1)
    return days


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
        f"/items/{product.biz_item_id}?{urlencode(params)}"
    )


def selected_products(value: str) -> list[Product]:
    if value == "all":
        return list(PRODUCTS.values())
    if value not in PRODUCTS:
        choices = ", ".join(["all", *PRODUCTS])
        raise ValueError(f"unknown product '{value}'. Choose one of: {choices}")
    return [PRODUCTS[value]]


def extract_visible_slots(page: Any) -> list[dict[str, str]]:
    return page.evaluate(
        """() => {
          const slots = [];
          let period = "";
          const nodes = Array.from(document.querySelectorAll("main *"));
          for (const node of nodes) {
            const text = (node.textContent || "").replace(/\\s+/g, " ").trim();
            if (text === "오전" || text === "오후") {
              period = text;
              continue;
            }
            if (node.tagName === "BUTTON" && /^\\d{1,2}:\\d{2}$/.test(text)) {
              const disabled = node.disabled || node.getAttribute("aria-disabled") === "true";
              if (!disabled) {
                slots.push({ period, time: text });
              }
            }
          }
          return slots;
        }"""
    )


def check_slots(product: Product, day: dt.date, headed: bool = False) -> list[dict[str, str]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Python Playwright is required. Install with: "
            "pip install playwright && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page(locale="ko-KR")
        page.goto(booking_url(product, day), wait_until="domcontentloaded")
        page.wait_for_selector("text=날짜와 시간을 선택해 주세요", timeout=20000)
        page.wait_for_timeout(1200)
        slots = extract_visible_slots(page)
        title = page.title()
        browser.close()

    return [
        {
            "product": product.slug,
            "productName": product.name,
            "date": day.isoformat(),
            "period": slot["period"],
            "time": slot["time"],
            "pageTitle": title,
            "url": booking_url(product, day),
        }
        for slot in slots
    ]


def print_slots(slots: list[dict[str, str]]) -> None:
    if not slots:
        print("가능한 시간이 없습니다.")
        return
    for slot in slots:
        print(
            f"{slot['date']} {slot['period']} {slot['time']} | "
            f"{slot['product']} | {slot['productName']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Olbarum Naver Booking slots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-products", help="show configured booking products")

    check = subparsers.add_parser("check", help="check available slots")
    check.add_argument("--start", required=True, type=parse_date)
    check.add_argument("--end", required=True, type=parse_date)
    check.add_argument("--product", default="director", help="product slug or all")
    check.add_argument("--json", action="store_true", help="print JSON output")
    check.add_argument("--headed", action="store_true", help="show browser while checking")

    open_page = subparsers.add_parser("open", help="open a booking page")
    open_page.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    open_page.add_argument("--date", type=parse_date)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-products":
        for product in PRODUCTS.values():
            print(f"{product.slug}: {product.name} (bizItemId={product.biz_item_id})")
        return 0

    if args.command == "open":
        url = booking_url(PRODUCTS[args.product], args.date)
        print(url)
        webbrowser.open(url)
        return 0

    try:
        slots: list[dict[str, str]] = []
        for product in selected_products(args.product):
            for day in date_range(args.start, args.end):
                slots.extend(check_slots(product, day, headed=args.headed))
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
