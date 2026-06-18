# TCDD Site Map

Inspection date: 2026-06-17.

Exploration method: live Chrome/DevTools Protocol inspection and screenshots. Playwright was not used for exploration.

## Main Page Flow

- Main search form is on `https://ebilet.tcddtasimacilik.gov.tr/`.
- `https://ebilet.tcddtasimacilik.gov.tr/sefer-listesi` is the result route after a search.
- Opening `/sefer-listesi` directly without search state can render only the site chrome/footer or an empty search-result state.
- Result page shows a stepper:
  - `Sefer Seçimi`
  - `Koltuk Seçimi`
  - `Ödeme İşlemi`
  - `İşlem Özeti`
- The inspected successful search navigation showed:
  - `Seferlerinizi Seçin`
  - route summary such as `ANKARA GAR ↔ İSTANBUL(PENDİK)`
  - result heading pattern `Gidiş - ANKARA GAR → İSTANBUL(PENDİK)`

## Route Input Behavior

- Departure field selector candidate: `#fromTrainInput`.
- Departure dropdown search input selector candidate: `[aria-label="departureInput"]`.
- Arrival field selector candidate: `#toTrainInput`.
- Arrival dropdown search input selector candidate: `[aria-label="arrivalInput"]`.
- Station options render as `button.dropdown-item.station`.
- Departure station option IDs use the pattern `gidis-{stationId}`.
  - Observed example: `gidis-98` for `ANKARA GAR`.
- Arrival station option IDs use the pattern `donus-{stationId}`.
  - Observed example: `donus-48` for `İSTANBUL(PENDİK)`.
- Station option visible text pattern:
  - `İstasyon {STATION} , {CITY} {TRAIN_TYPES}`
  - Example: `İstasyon ANKARA GAR , ANKARA ANAHAT BÖLGESEL TURİSTİK TREN YHT`
- After selecting departure, the arrival dropdown becomes route-dependent. For `ANKARA GAR`, it showed reachable stations such as `ARİFİYE`, `GEBZE`, and `İSTANBUL(PENDİK)`.
- The CDN station data endpoint is:
  - `https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/stations.json`
- The station-pair endpoint is:
  - `https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/station-pairs-INTERNET.json`

## Date Input Behavior

- Quick buttons are visible:
  - `Bugün`
  - `Yarın`
  - `Aynı Gün`
  - `Sonraki Gün`
- Date input selector candidate: `input.calenderPurpleImg`.
- Date input visible format example: `17 Haziran Çarşamba`.
- Date picker opens a two-month calendar.
  - Observed month headings: `Haziran 2026`, `Temmuz 2026`.
  - Weekday headings: `Pzt`, `Sal`, `Çar`, `Per`, `Cum`, `Cmt`, `Paz`.
- Search API request converted `17 Haziran 2026` local Istanbul time into payload date `16-06-2026 21:00:00`.

## Search Button Behavior

- Main search button selector: `#searchSeferButton`.
- Button text on home page: `Sefer Ara`.
- Search results route: `/sefer-listesi`.
- Missing-arrival validation text observed:
  - `Tren varış alanı gereklidir..`
- No-results text observed:
  - `Aradığınız tarihlerde sefer bulunamamıştır.`
  - `Önceki veya sonraki tarihlere giderek aramanıza devam edebilirsiniz.`

## Result List Structure

- Result page includes a date carousel around the selected date.
- No available trip row was observed during inspection for `ANKARA GAR` to `İSTANBUL(PENDİK)` on `17 Haziran 2026`; the page showed the no-results text above.
- Candidate result-row text patterns to parse when trips exist:
  - route section: `Gidiş - {FROM} → {TO}`
  - time values: `HH:MM`
  - train/service names such as `YHT`
  - class names such as `Ekonomi`, `Business`
  - fare text ending in `TL`
  - availability text such as `Uygun`, `Boş`, `Dolu`, `Tükendi`

## Train Time Appearance

- Available rows were not observed live.
- Candidate time pattern is `HH:MM`.
- Bundle code contains conversion logic for train times and date fields such as `trainDate`, `departureTime`, and `arrivalTime`, converting from UTC to `Europe/Istanbul`.

## Train/Service Name Appearance

- Search and station UI use train category labels including:
  - `YHT`
  - `ANAHAT`
  - `BÖLGESEL`
  - `TURİSTİK TREN`
- Candidate service-name text in result rows should be matched by user keyword, for example `YHT`.

## Seat/Class Type Appearance

- Candidate visible class names from bundle/UI strings:
  - `Ekonomi`
  - `Business`
  - `Koltuk`
- Seat selection and seat maps are separate later steps. The watcher must not open or interact with them.

## Availability Appearance

- Positive candidate patterns:
  - `Uygun`
  - `Boş`
  - price text with `TL`
- Negative/unavailable patterns:
  - `Dolu`
  - `Tükendi`
  - `Aradığınız tarihlerde sefer bulunamamıştır.`
  - `seferde ve tarifede tüm yerlerimiz doludur`

## Candidate Selectors

- Home route form:
  - `#fromTrainInput`
  - `[aria-label="departureInput"]`
  - `#toTrainInput`
  - `[aria-label="arrivalInput"]`
  - `input.calenderPurpleImg`
  - `[aria-label="Yolcu Sayısı"]`
  - `#searchSeferButton`
- Station options:
  - `button.dropdown-item.station`
  - `#gidis-{stationId}`
  - `#donus-{stationId}`
- Result route:
  - text anchors: `Seferlerinizi Seçin`, `Gidiş -`, `Yeniden Ara`
  - no-results text: `Aradığınız tarihlerde sefer bulunamamıştır.`

## Candidate API Endpoints

- Station data:
  - `https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/stations.json`
- Station pairs:
  - `https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/station-pairs-INTERNET.json`
- Browser-origin train availability:
  - `https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms/train/train-availability?environment=dev&userId=1`
- Observed POST body shape:

```json
{
  "searchRoutes": [
    {
      "departureStationId": 98,
      "departureStationName": "ANKARA GAR",
      "arrivalStationId": 48,
      "arrivalStationName": "İSTANBUL(PENDİK)",
      "departureDate": "16-06-2026 21:00:00"
    }
  ],
  "passengerTypeCounts": [
    {
      "id": 0,
      "count": 1
    }
  ],
  "searchReservation": false,
  "searchType": "DOMESTIC",
  "blTrainTypes": [
    "TURISTIK_TREN"
  ]
}
```

Direct shell/API calls returned `403`, so the watcher should use browser automation as the primary search path.

## Uncertainty

- A live available-result row was not observed, so final result-card selectors are uncertain.
- The first watcher version should parse visible result text and, when available, the browser-captured availability API JSON.
- Date picker class names may change; keep quick buttons for today/tomorrow and a fallback calendar click strategy for arbitrary dates.
