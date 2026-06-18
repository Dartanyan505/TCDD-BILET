from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.request
from datetime import date as Date
from datetime import datetime, time as Time
from datetime import timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from curl_cffi import requests

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback.
    import tomli as tomllib  # type: ignore


BASE_URL = "https://ebilet.tcddtasimacilik.gov.tr"
TMS_API_URL = "https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms"
STATIONS_URL = "https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/stations.json"
AVAILABILITY_URL = f"{TMS_API_URL}/train/train-availability?environment=dev&userId=1"
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

UNAVAILABLE_PATTERNS = (
    "dolu",
    "tukendi",
    "tükendi",
    "sefer bulunamamistir",
    "sefer bulunamamıştır",
    "yerlerimiz doludur",
    "uygun sefer bulunamamıştır",
)

AVAILABLE_PATTERNS = (
    "uygun",
    "bos",
    "boş",
    "tl",
    "available",
)


@dataclasses.dataclass(frozen=True)
class Config:
    departure_station: str
    arrival_station: str
    date: Date
    preferred_departure_time: str = ""
    departure_time_from: str = ""
    departure_time_to: str = ""
    train_keyword: str = ""
    seat_class_keyword: str = ""
    check_interval_seconds: int = 300
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"


@dataclasses.dataclass(frozen=True)
class Candidate:
    departure_time: str
    train_name: str
    class_name: str
    availability: str
    raw_text: str

    @property
    def key(self) -> str:
        return "|".join(
            normalize_text(part)
            for part in (
                self.departure_time,
                self.train_name,
                self.class_name,
                self.availability,
            )
        )


@dataclasses.dataclass(frozen=True)
class Station:
    id: int
    name: str
    city: str
    active: bool
    show_on_query: bool
    raw: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.name}, {self.city}" if self.city else self.name


class TCDDHttpClient:
    def __init__(self) -> None:
        self.session = requests.Session(impersonate="chrome99")
        self.token = load_public_token()
        self.stations = load_stations()

    def search(self, config: Config) -> dict[str, Any]:
        departure = resolve_station(self.stations, config.departure_station)
        arrival = resolve_station(self.stations, config.arrival_station)
        payload = build_availability_payload(config, departure, arrival)
        headers = self.headers()

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self.session.post(
                    AVAILABILITY_URL,
                    headers=headers,
                    json=payload,
                    timeout=35,
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code in {401, 403} and attempt == 1:
                    self.token = load_public_token()
                    headers = self.headers()
                    continue
                raise RuntimeError(
                    f"train-availability returned HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(attempt)
                    continue
        raise RuntimeError(f"train-availability request failed: {last_error}")

    def headers(self) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "tr",
            "authorization": self.token,
            "content-type": "application/json",
            "origin": BASE_URL,
            "referer": f"{BASE_URL}/",
            "unit-id": "3895",
        }


@dataclasses.dataclass
class WatcherStatus:
    running: bool = False
    last_check_started: str = ""
    last_check_finished: str = ""
    last_error: str = ""
    last_matches: list[dict[str, str]] = dataclasses.field(default_factory=list)
    total_checks: int = 0


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip().casefold()


def search_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.translate(str.maketrans({"ı": "i", "İ": "I"}))
    value = value.casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def load_config(path: Path) -> Config:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    try:
        travel_date = datetime.strptime(str(raw["date"]), "%Y-%m-%d").date()
        interval = int(raw.get("check_interval_seconds", 300))
        if interval < 1:
            raise ValueError("check_interval_seconds must be at least 1")
        return Config(
            departure_station=str(raw["departure_station"]).strip(),
            arrival_station=str(raw["arrival_station"]).strip(),
            date=travel_date,
            preferred_departure_time=str(raw.get("preferred_departure_time", "")).strip(),
            departure_time_from=str(raw.get("departure_time_from", "")).strip(),
            departure_time_to=str(raw.get("departure_time_to", "")).strip(),
            train_keyword=str(raw.get("train_keyword", "")).strip(),
            seat_class_keyword=str(raw.get("seat_class_keyword", "")).strip(),
            check_interval_seconds=interval,
            ntfy_topic=str(raw.get("ntfy_topic", "")).strip(),
            ntfy_server=str(raw.get("ntfy_server", "https://ntfy.sh")).strip() or "https://ntfy.sh",
        )
    except KeyError as exc:
        raise SystemExit(f"Missing required config key: {exc.args[0]}") from exc


def config_to_dict(config: Config) -> dict[str, Any]:
    return {
        "departure_station": config.departure_station,
        "arrival_station": config.arrival_station,
        "date": config.date.isoformat(),
        "preferred_departure_time": config.preferred_departure_time,
        "departure_time_from": config.departure_time_from,
        "departure_time_to": config.departure_time_to,
        "train_keyword": config.train_keyword,
        "seat_class_keyword": config.seat_class_keyword,
        "check_interval_seconds": config.check_interval_seconds,
        "ntfy_topic": config.ntfy_topic,
        "ntfy_server": config.ntfy_server,
    }


def save_config(path: Path, config: Config) -> None:
    data = config_to_dict(config)
    lines = [
        f'departure_station = {json.dumps(data["departure_station"], ensure_ascii=False)}',
        f'arrival_station = {json.dumps(data["arrival_station"], ensure_ascii=False)}',
        f'date = "{data["date"]}"',
        "",
        "# Use either preferred_departure_time for an exact HH:MM match, or a range.",
        f'preferred_departure_time = "{data["preferred_departure_time"]}"',
        f'departure_time_from = "{data["departure_time_from"]}"',
        f'departure_time_to = "{data["departure_time_to"]}"',
        "",
        "# Leave empty to accept any train/service or class text.",
        f'train_keyword = {json.dumps(data["train_keyword"], ensure_ascii=False)}',
        f'seat_class_keyword = {json.dumps(data["seat_class_keyword"], ensure_ascii=False)}',
        "",
        f'check_interval_seconds = {int(data["check_interval_seconds"])}',
        "",
        "# Optional phone push notification via ntfy.",
        f'ntfy_topic = {json.dumps(data["ntfy_topic"], ensure_ascii=False)}',
        f'ntfy_server = {json.dumps(data["ntfy_server"], ensure_ascii=False)}',
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_hhmm(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def minutes(value: str) -> int | None:
    parsed = parse_hhmm(value)
    if parsed is None:
        return None
    return parsed[0] * 60 + parsed[1]


def time_matches(candidate_time: str, config: Config) -> bool:
    if not candidate_time:
        return False
    if config.preferred_departure_time:
        return candidate_time == config.preferred_departure_time

    current = minutes(candidate_time)
    start = minutes(config.departure_time_from)
    end = minutes(config.departure_time_to)
    if current is None:
        return False
    if start is None and end is None:
        return True
    if start is not None and current < start:
        return False
    if end is not None and current > end:
        return False
    return True


def has_unavailable_text(text: str) -> bool:
    normalized = normalize_text(text)
    return any(pattern in normalized for pattern in UNAVAILABLE_PATTERNS)


def has_available_text(text: str) -> bool:
    normalized = normalize_text(text)
    return any(pattern in normalized for pattern in AVAILABLE_PATTERNS)


def keyword_matches(text: str, keyword: str) -> bool:
    return not keyword or search_key(keyword) in search_key(text)


def filter_rejection_reason(candidate: Candidate, config: Config) -> str | None:
    searchable = " ".join(
        [
            candidate.raw_text,
            candidate.train_name,
            candidate.class_name,
            candidate.availability,
        ]
    )
    if not time_matches(candidate.departure_time, config):
        return "time"
    if not keyword_matches(searchable, config.train_keyword):
        return "train_keyword"
    if not keyword_matches(searchable, config.seat_class_keyword):
        return "seat_class_keyword"
    if has_unavailable_text(searchable):
        return "unavailable"
    if not has_available_text(searchable):
        return "no_availability_signal"
    return None


def filter_candidates_with_diagnostics(
    candidates: list[Candidate],
    config: Config,
) -> tuple[list[Candidate], dict[str, int]]:
    matches: list[Candidate] = []
    seen: set[str] = set()
    reasons = {
        "duplicate": 0,
        "time": 0,
        "train_keyword": 0,
        "seat_class_keyword": 0,
        "unavailable": 0,
        "no_availability_signal": 0,
    }

    for candidate in candidates:
        if candidate.key in seen:
            reasons["duplicate"] += 1
            continue
        reason = filter_rejection_reason(candidate, config)
        if reason:
            reasons[reason] += 1
            continue
        seen.add(candidate.key)
        matches.append(candidate)

    return matches, reasons


def filter_candidates(candidates: list[Candidate], config: Config) -> list[Candidate]:
    matches, _ = filter_candidates_with_diagnostics(candidates, config)
    return matches


def epoch_to_hhmm(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", str(value))
        if match:
            return f"{int(match.group(1)):02d}:{match.group(2)}"
        return ""
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, ISTANBUL_TZ).strftime("%H:%M")


def first_price_text(*objects: Any) -> str:
    for value in objects:
        price = find_price_amount(value)
        if price is not None:
            return f"{price:g} TL"
    return ""


def find_price_amount(value: Any) -> float | None:
    if isinstance(value, dict):
        if isinstance(value.get("priceAmount"), (int, float)):
            return float(value["priceAmount"])
        if isinstance(value.get("minPrice"), (int, float)):
            return float(value["minPrice"])
        for child in value.values():
            price = find_price_amount(child)
            if price is not None:
                return price
    elif isinstance(value, list):
        for child in value:
            price = find_price_amount(child)
            if price is not None:
                return price
    return None


def train_availability_candidates(payload: dict[str, Any]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for leg in payload.get("trainLegs", []) if isinstance(payload, dict) else []:
        for availability_group in leg.get("trainAvailabilities", []) or []:
            for train in availability_group.get("trains", []) or []:
                candidates.extend(train_candidates(train))
    return candidates


def train_candidates(train: dict[str, Any]) -> list[Candidate]:
    segments = train.get("segments") or []
    departure_time = epoch_to_hhmm(segments[0].get("departureTime") if segments else "")
    arrival_time = epoch_to_hhmm(segments[-1].get("arrivalTime") if segments else "")
    if not departure_time:
        return []

    train_name = " ".join(
        str(part)
        for part in (
            train.get("type"),
            train.get("number"),
            train.get("commercialName"),
            train.get("name"),
        )
        if part
    )
    min_price = train.get("minPrice")
    grouped: dict[str, dict[str, Any]] = {}

    for car in train.get("cars", []) or []:
        for availability in car.get("availabilities", []) or []:
            count = availability.get("availability")
            if not isinstance(count, (int, float)) or count <= 0:
                continue
            class_name = availability_class_name(availability) or "Unknown class"
            price_text = first_price_text(availability.get("pricingList"), availability, min_price)
            group = grouped.setdefault(
                class_name,
                {"availability": 0, "price": price_text, "raw": []},
            )
            group["availability"] += int(count)
            if not group["price"] and price_text:
                group["price"] = price_text
            group["raw"].append(availability)

    candidates: list[Candidate] = []
    for class_name, group in grouped.items():
        availability_text = f"{group['availability']} uygun"
        if group["price"]:
            availability_text = f"{availability_text} {group['price']}"
        raw_text = stringify_json_object(
            {
                "train": train_name,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "class": class_name,
                "availability": availability_text,
                "raw_availability": group["raw"],
            }
        )
        candidates.append(
            Candidate(
                departure_time=departure_time,
                train_name=train_name,
                class_name=class_name,
                availability=availability_text,
                raw_text=raw_text,
            )
        )

    return candidates


def availability_class_name(availability: dict[str, Any]) -> str:
    parts: list[str] = []
    cabin = availability.get("cabinClass") or {}
    if cabin.get("name"):
        parts.append(str(cabin["name"]))
    for pricing in availability.get("pricingList", []) or []:
        booking = pricing.get("bookingClass") or {}
        fare_family = booking.get("fareFamily") or {}
        if booking.get("name"):
            parts.append(str(booking["name"]))
        if fare_family.get("name"):
            parts.append(str(fare_family["name"]))
    return " ".join(dict.fromkeys(parts))


def stringify_json_object(value: dict[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def fetch_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str, timeout: int = 30) -> Any:
    return json.loads(fetch_text(url, timeout=timeout))


def load_public_token() -> str:
    html = fetch_text(f"{BASE_URL}/")
    script_urls = [
        urllib.request.urljoin(f"{BASE_URL}/", src)
        for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html)
    ]
    for script_url in reversed(script_urls):
        if not script_url.startswith(BASE_URL):
            continue
        try:
            script = fetch_text(script_url)
        except Exception:
            continue
        if "var F=null;switch" not in script or "TCDD-PROD" not in script:
            continue
        start = script.find("var F=null;switch")
        chunk = script[start : start + 20000]
        for match in re.finditer(r'case"([^"]+)":F="([^"]+)"', chunk):
            if match.group(1) == "TCDD-PROD":
                return match.group(2)
    raise RuntimeError("Could not locate TCDD-PROD public API token in site bundle")


def load_stations() -> list[Station]:
    raw_stations = fetch_json(STATIONS_URL)
    stations: list[Station] = []
    for raw in raw_stations:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), int):
            continue
        city = ""
        city_value = raw.get("city") or raw.get("cityName")
        if isinstance(city_value, dict):
            city = str(city_value.get("name") or "")
        elif city_value:
            city = str(city_value)
        elif raw.get("cityId"):
            city = str(raw.get("cityId"))
        stations.append(
            Station(
                id=int(raw["id"]),
                name=str(raw.get("name") or "").strip(),
                city=city,
                active=bool(raw.get("active", True)),
                show_on_query=bool(raw.get("showOnQuery", True)),
                raw=raw,
            )
        )
    if not stations:
        raise RuntimeError("No stations loaded from TCDD station data")
    return stations


def resolve_station(stations: list[Station], query: str) -> Station:
    query_key = search_key(query.split(",")[0])
    exact = [station for station in stations if search_key(station.name) == query_key]
    if exact:
        return sorted(exact, key=station_sort_key)[0]

    contains = [
        station
        for station in stations
        if query_key and (query_key in search_key(station.name) or search_key(station.name) in query_key)
    ]
    if contains:
        return sorted(contains, key=station_sort_key)[0]

    examples = ", ".join(station.name for station in stations[:8])
    raise RuntimeError(f"Station not found: {query}. Example station names: {examples}")


def station_sort_key(station: Station) -> tuple[int, int, int]:
    return (
        0 if station.active else 1,
        0 if station.show_on_query else 1,
        len(station.name),
    )


def station_to_dict(station: Station) -> dict[str, Any]:
    return {
        "id": station.id,
        "name": station.name,
        "city": station.city,
        "label": station.label,
        "active": station.active,
        "show_on_query": station.show_on_query,
    }


def build_availability_payload(config: Config, departure: Station, arrival: Station) -> dict[str, Any]:
    return {
        "searchRoutes": [
            {
                "departureStationId": departure.id,
                "departureStationName": departure.name,
                "arrivalStationId": arrival.id,
                "arrivalStationName": arrival.name,
                "departureDate": api_departure_date(config.date),
            }
        ],
        "passengerTypeCounts": [{"id": 0, "count": 1}],
        "searchReservation": False,
        "searchType": "DOMESTIC",
        "blTrainTypes": ["TURISTIK_TREN"],
    }


def api_departure_date(travel_date: Date) -> str:
    local_midnight = datetime.combine(travel_date, Time.min, tzinfo=ISTANBUL_TZ)
    api_time = local_midnight.astimezone(timezone.utc)
    return api_time.strftime("%d-%m-%Y %H:%M:%S")


def search_once(client: TCDDHttpClient, config: Config, dry_run: bool) -> list[Candidate]:
    payload = client.search(config)
    candidates = train_availability_candidates(payload)
    matches, filter_reasons = filter_candidates_with_diagnostics(candidates, config)

    if dry_run:
        departure = resolve_station(client.stations, config.departure_station)
        arrival = resolve_station(client.stations, config.arrival_station)
        print(f"Selected departure: {departure.label} (id={departure.id})")
        print(f"Selected arrival: {arrival.label} (id={arrival.id})")
        print(f"API endpoint: {AVAILABILITY_URL}")
        print("Availability API status: 200")
        print(f"Raw candidates: {len(candidates)}")
        print(f"Filter rejections: {filter_reasons}")
        print(f"Candidate matches: {len(matches)}")
        print("First parsed candidates:")
        for candidate in candidates[:10]:
            print(f"  {format_candidate(candidate)}")
        for match in matches:
            print(format_candidate(match))

    return matches


def format_candidate(candidate: Candidate) -> str:
    details = [
        f"time={candidate.departure_time}",
        f"train={candidate.train_name or 'unknown'}",
        f"class={candidate.class_name or 'unknown'}",
        f"availability={candidate.availability or 'unknown'}",
    ]
    return "; ".join(details)


def candidate_to_dict(candidate: Candidate) -> dict[str, str]:
    return {
        "departure_time": candidate.departure_time,
        "train_name": candidate.train_name,
        "class_name": candidate.class_name,
        "availability": candidate.availability,
        "raw_text": candidate.raw_text,
        "formatted": format_candidate(candidate),
    }


def config_from_mapping(values: dict[str, Any]) -> Config:
    return Config(
        departure_station=str(values.get("departure_station", "")).strip(),
        arrival_station=str(values.get("arrival_station", "")).strip(),
        date=datetime.strptime(str(values.get("date", "")), "%Y-%m-%d").date(),
        preferred_departure_time=str(values.get("preferred_departure_time", "")).strip(),
        departure_time_from=str(values.get("departure_time_from", "")).strip(),
        departure_time_to=str(values.get("departure_time_to", "")).strip(),
        train_keyword=str(values.get("train_keyword", "")).strip(),
        seat_class_keyword=str(values.get("seat_class_keyword", "")).strip(),
        check_interval_seconds=max(1, int(values.get("check_interval_seconds", 300))),
        ntfy_topic=str(values.get("ntfy_topic", "")).strip(),
        ntfy_server=str(values.get("ntfy_server", "https://ntfy.sh")).strip() or "https://ntfy.sh",
    )


def send_ntfy_message(config: Config, title: str, message: str) -> None:
    if not config.ntfy_topic:
        return

    server = config.ntfy_server.rstrip("/")
    response = requests.post(
        f"{server}/{config.ntfy_topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Tags": "train,rotating_light",
        },
        timeout=10,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"ntfy returned HTTP {response.status_code}: {response.text[:200]}")


def notify(candidate: Candidate, config: Config, dry_run: bool) -> None:
    title = "TCDD bilet bulundu"
    message = (
        f"{config.departure_station} -> {config.arrival_station} "
        f"{config.date.isoformat()} {format_candidate(candidate)}"
    )
    print(f"[FOUND] {title}: {message}", flush=True)
    if dry_run:
        return

    try:
        send_ntfy_message(config, title, message)
    except Exception as exc:
        print(f"ntfy notification failed: {exc}", file=sys.stderr)


class WatcherService:
    def __init__(self, log_callback: Callable[[str, str], None] | None = None) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status = WatcherStatus()
        self._config: Config | None = None
        self._notified: set[str] = set()
        self._log_callback = log_callback

    def start(self, config: Config) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._config = config
                self._log("Watcher config güncellendi.")
                return
            self._config = config
            self._notified = set()
            self._stop_event = threading.Event()
            self._status = WatcherStatus(running=True)
            self._thread = threading.Thread(target=self._run, name="tcdd-watcher", daemon=True)
            self._thread.start()
            self._log("Watcher thread başlatıldı.")

    def stop(self) -> None:
        thread: threading.Thread | None
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread:
            thread.join(timeout=2)
        with self._lock:
            self._status.running = False
        self._log("Watcher thread durduruldu.")

    def status_dict(self) -> dict[str, Any]:
        with self._lock:
            status = dataclasses.asdict(self._status)
        return status

    def _run(self) -> None:
        client = TCDDHttpClient()
        while not self._stop_event.is_set():
            with self._lock:
                config = self._config
                self._status.running = True
                self._status.total_checks += 1
                self._status.last_check_started = datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds")
                self._status.last_error = ""
            if config is None:
                break
            try:
                self._log(f"Kontrol başladı: {config.departure_station} -> {config.arrival_station}")
                matches = search_once(client, config, dry_run=False)
                match_dicts = [candidate_to_dict(match) for match in matches]
                with self._lock:
                    self._status.last_matches = match_dicts
                self._log(f"Kontrol tamamlandı. Eşleşme: {len(matches)}")
                for match in matches:
                    key = (
                        f"{config.date.isoformat()}|{config.departure_station}|"
                        f"{config.arrival_station}|{match.key}"
                    )
                    if key in self._notified:
                        continue
                    self._notified.add(key)
                    self._log(f"Yeni uygun sefer: {format_candidate(match)}", "success")
                    notify(match, config, dry_run=False)
            except Exception as exc:
                with self._lock:
                    self._status.last_error = str(exc)
                self._log(f"Kontrol hata verdi: {exc}", "error")
            finally:
                with self._lock:
                    self._status.last_check_finished = datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds")
            if self._stop_event.wait(config.check_interval_seconds):
                break
        with self._lock:
            self._status.running = False

    def _log(self, message: str, level: str = "info") -> None:
        if self._log_callback:
            self._log_callback(message, level)


def run(config: Config, once: bool, dry_run: bool) -> None:
    client = TCDDHttpClient()
    while True:
        started = datetime.now(ISTANBUL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{started}] Checking {config.departure_station} -> {config.arrival_station}")
        try:
            matches = search_once(client, config, dry_run=dry_run)
            if matches:
                print(f"  {len(matches)} uygun sefer bulundu:")
                for match in matches:
                    print(f"  [UYGUN] {format_candidate(match)}", flush=True)
                    notify(match, config, dry_run=dry_run)
            else:
                print("  Uygun sefer bulunamadı.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"Check failed: {exc}", file=sys.stderr)

        if once:
            return
        time.sleep(config.check_interval_seconds)


def parser_self_test() -> None:
    config = Config(
        departure_station="ANKARA GAR",
        arrival_station="İSTANBUL(PENDİK)",
        date=Date(2026, 6, 17),
        departure_time_from="06:00",
        departure_time_to="12:00",
        train_keyword="YHT",
        seat_class_keyword="Ekonomi",
    )
    sample_payload = {
        "trainLegs": [
            {
                "trainAvailabilities": [
                    {
                        "trains": [
                            {
                                "type": "YHT",
                                "number": "81001",
                                "commercialName": "YHT ANKARA-İSTANBUL",
                                "name": "81001 ANKARA-İSTANBUL",
                                "minPrice": {"priceAmount": 225.0},
                                "segments": [
                                    {
                                        "departureTime": int(
                                            datetime(
                                                2026,
                                                6,
                                                17,
                                                6,
                                                0,
                                                tzinfo=ISTANBUL_TZ,
                                            ).timestamp()
                                            * 1000
                                        ),
                                        "arrivalTime": int(
                                            datetime(
                                                2026,
                                                6,
                                                17,
                                                10,
                                                5,
                                                tzinfo=ISTANBUL_TZ,
                                            ).timestamp()
                                            * 1000
                                        ),
                                    }
                                ],
                                "cars": [
                                    {
                                        "availabilities": [
                                            {
                                                "cabinClass": {"name": "EKONOMİ"},
                                                "availability": 12,
                                                "pricingList": [
                                                    {
                                                        "bookingClass": {
                                                            "name": "EKONOMİ STANDART",
                                                            "fareFamily": {"name": "STANDART"},
                                                        },
                                                        "fareBasis": {
                                                            "price": {"priceAmount": 225.0}
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "cabinClass": {"name": "BUSİNESS"},
                                                "availability": 2,
                                            },
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    parsed = train_availability_candidates(sample_payload)
    matches = filter_candidates(parsed, config)
    assert len(matches) == 1, matches
    assert matches[0].departure_time == "06:00"
    assert "EKONOMİ" in matches[0].class_name
    print("Parser self-test passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search TCDD tickets and notify on matches.")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config file.")
    parser.add_argument("--once", action="store_true", help="Run one search and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without notifications.")
    parser.add_argument("--self-test", action="store_true", help="Run parser self-test and exit.")
    args = parser.parse_args()

    if args.self_test:
        parser_self_test()
        return

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(
            f"Config file not found: {config_path}. Create the file and try again."
        )

    config = load_config(config_path)
    run(config, once=args.once, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
