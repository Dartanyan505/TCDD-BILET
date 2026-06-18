from __future__ import annotations

import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from tcdd_watcher import (
    Config,
    TCDDHttpClient,
    WatcherService,
    candidate_to_dict,
    config_from_mapping,
    config_to_dict,
    filter_candidates_with_diagnostics,
    format_candidate,
    ISTANBUL_TZ,
    load_config,
    save_config,
    send_ntfy_message,
    station_to_dict,
    train_availability_candidates,
)


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"

app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
http_client: TCDDHttpClient | None = None
log_buffer: deque[dict[str, str]] = deque(maxlen=200)


def push_log(message: str, level: str = "info") -> None:
    log_buffer.appendleft(
        {
            "time": datetime.now(ISTANBUL_TZ).strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
    )


watcher_service = WatcherService(push_log)


def candidate_card(candidate: Any, reason: str = "Saat, tren ve sınıf filtreleri eşleşti.") -> dict[str, str]:
    data = candidate_to_dict(candidate)
    data["summary"] = format_candidate(candidate)
    data["reason"] = reason
    return data


def get_client() -> TCDDHttpClient:
    global http_client
    if http_client is None:
        http_client = TCDDHttpClient()
    return http_client


def current_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return config_to_dict(load_config(CONFIG_PATH))
    return {
        "departure_station": "",
        "arrival_station": "",
        "date": "",
        "preferred_departure_time": "",
        "departure_time_from": "",
        "departure_time_to": "",
        "train_keyword": "",
        "seat_class_keyword": "",
        "check_interval_seconds": 300,
        "ntfy_topic": "",
        "ntfy_server": "https://ntfy.sh",
    }


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/config")
def api_config() -> Any:
    return jsonify(current_config())


@app.post("/api/config")
def api_save_config() -> Any:
    try:
        payload = request.get_json(force=True) or {}
        config = config_from_mapping(payload)
        save_config(CONFIG_PATH, config)
        push_log("Config kaydedildi.")
        return jsonify({"ok": True, "config": config_to_dict(config), "message": "Config kaydedildi."})
    except Exception as exc:
        push_log(f"Config kaydedilemedi: {exc}", "error")
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/stations")
def api_stations() -> Any:
    client = get_client()
    stations = sorted(client.stations, key=lambda station: station.label)
    return jsonify([station_to_dict(station) for station in stations])


@app.post("/api/search")
def api_search() -> Any:
    try:
        payload = request.get_json(force=True) or {}
        config = config_from_mapping(payload)
        client = get_client()
        raw_payload = client.search(config)
        candidates = train_availability_candidates(raw_payload)
        matches, filter_reasons = filter_candidates_with_diagnostics(candidates, config)
        push_log(f"Tek seferlik arama tamamlandı. Eşleşme: {len(matches)}")
        return jsonify(
            {
                "ok": True,
                "raw_candidate_count": len(candidates),
                "match_count": len(matches),
                "filter_rejections": filter_reasons,
                "matches": [candidate_card(match) for match in matches],
                "first_candidates": [candidate_card(candidate, "İlk ham aday") for candidate in candidates[:20]],
            }
        )
    except Exception as exc:
        push_log(f"Tek seferlik arama hata verdi: {exc}", "error")
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/watcher/start")
def api_watcher_start() -> Any:
    try:
        payload = request.get_json(force=True) or {}
        config = config_from_mapping(payload)
        save_config(CONFIG_PATH, config)
        watcher_service.start(config)
        push_log("Watcher başlatıldı.")
        return jsonify({"ok": True, "status": watcher_service.status_dict()})
    except Exception as exc:
        push_log(f"Watcher başlatılamadı: {exc}", "error")
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/watcher/stop")
def api_watcher_stop() -> Any:
    watcher_service.stop()
    push_log("Watcher durduruldu.")
    return jsonify({"ok": True, "status": watcher_service.status_dict()})


@app.get("/api/watcher/status")
def api_watcher_status() -> Any:
    return jsonify({"ok": True, "status": watcher_service.status_dict()})


@app.get("/api/logs")
def api_logs() -> Any:
    return jsonify({"ok": True, "logs": list(log_buffer)})


@app.post("/api/ntfy/test")
def api_ntfy_test() -> Any:
    try:
        payload = request.get_json(force=True) or {}
        config = Config(
            departure_station="",
            arrival_station="",
            date=datetime.now(ISTANBUL_TZ).date(),
            ntfy_topic=str(payload.get("ntfy_topic", "")).strip(),
            ntfy_server=str(payload.get("ntfy_server", "https://ntfy.sh")).strip() or "https://ntfy.sh",
        )
        title = "TCDD test bildirimi"
        message = "Bu bir test bildirimidir."
        send_ntfy_message(config, title, message)
        push_log("ntfy test bildirimi gönderildi.")
        return jsonify({"ok": True, "message": "ntfy test bildirimi gönderildi."})
    except Exception as exc:
        push_log(f"ntfy test bildirimi gönderilemedi: {exc}", "error")
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    host = os.environ.get("TCDD_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("TCDD_UI_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
