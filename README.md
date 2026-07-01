# olbarum

Naver Booking helper for checking Olbarum reservation availability.

## Structure

- `backend/` - Server-side application code and APIs.
- `frontend/` - Client-side application code.
- `docs/` - Project documentation, notes, and specifications.
- `tests/` - Automated tests and test fixtures.

## Getting Started

Create a local credential file if you want future login-based automation:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```text
NAVER_ID=your_naver_id
NAVER_PASSWORD=your_naver_password
```

Check whether credentials are configured:

```powershell
python -m backend.naver_booking_api config
```

List configured booking products:

```powershell
python -m backend.naver_booking_api list-products
```

Check available times for `BodyCare 대표원장 '황세영'`:

```powershell
python -m backend.naver_booking_api check --start 2026-07-15 --end 2026-07-31 --product director --option 60
```

For 60-minute reservations, the checker only returns times where two consecutive
30-minute slots are available. Use `--option 90` or `--option 120` for longer
reservations.

Open the booking page manually:

```powershell
python -m backend.naver_booking_api open --product director --date 2026-07-22
```

Prepare a reservation in Chrome, stopping before final submission:

```powershell
python -m backend.naver_booking_api reserve --date 2026-07-22 --product director --time 13:30 --option 90
```

The `reserve` command uses `.env` credentials, selects the time and duration,
and leaves the browser open for final manual review.

Known product slugs are `director`, `manager`, `sunday`, and `trial30`.
