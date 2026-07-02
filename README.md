# olbarum

올바름바디케어 네이버 예약 가능 시간을 확인하고, 필요하면 예약 화면 준비까지 도와주는 도구입니다.

## 주요 기능

- 네이버 예약 상품별 가능 시간 확인
- 날짜 구간별 예약 가능 시간 확인
- 60분, 90분, 120분 예약에 필요한 연속 30분 슬롯 검사
- Chrome을 열어 예약 화면 준비
- `.env` 파일을 이용한 네이버 로그인 정보 관리

## 프로젝트 구조

- `backend/` - 예약 조회와 브라우저 자동화 코드
- `frontend/` - 프론트엔드 코드 위치
- `docs/` - 프로젝트 문서
- `tests/` - 자동화 테스트

## 초기 설정

로그인 기반 예약 준비 기능을 쓰려면 `.env.example`을 복사해 `.env`를 만듭니다.

```powershell
Copy-Item .env.example .env
```

`.env`에 네이버 계정 정보를 입력합니다.

```text
NAVER_ID=your_naver_id
NAVER_PASSWORD=your_naver_password
```

`.env` 파일은 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.

## 사용법

설정된 예약 상품 목록을 확인합니다.

```powershell
python -m backend.naver_booking_api list-products
```

로그인 정보가 설정되어 있는지 확인합니다.

```powershell
python -m backend.naver_booking_api config
```

대표원장 상품의 60분 예약 가능 시간을 날짜 구간으로 확인합니다.

```powershell
python -m backend.naver_booking_api check --start 2026-07-15 --end 2026-07-31 --product director --option 60
```

60분 예약은 연속된 30분 슬롯 2개가 모두 가능할 때만 표시됩니다. 90분은 3개, 120분은 4개의 연속 슬롯이 필요합니다.

예약 페이지를 수동으로 엽니다.

```powershell
python -m backend.naver_booking_api open --product director --date 2026-07-22
```

Chrome에서 예약 화면을 준비합니다. 이 명령은 최종 예약 제출 버튼을 누르지 않습니다.

```powershell
python -m backend.naver_booking_api reserve --date 2026-07-22 --product director --time 13:30 --option 90
```

## 예약 상품 코드

- `director` - BodyCare 대표원장 '황세영'
- `manager` - BodyCare 실장 '권혁민'
- `sunday` - '일요일' 관리예약 전용
- `trial30` - 30분 무료체험

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 주의사항

- 실제 최종 예약 제출은 사용자가 직접 확인 후 진행합니다.
- 네이버 로그인 중 2단계 인증이나 추가 확인이 나오면 브라우저에서 직접 처리해야 합니다.
- 네이버 예약 페이지 구조가 바뀌면 브라우저 자동화 코드 수정이 필요할 수 있습니다.
