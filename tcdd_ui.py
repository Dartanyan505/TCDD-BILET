from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from tcdd_watcher import (
    TCDDHttpClient,
    WatcherService,
    candidate_to_dict,
    config_from_mapping,
    config_to_dict,
    filter_candidates_with_diagnostics,
    load_config,
    save_config,
    station_to_dict,
    train_availability_candidates,
)


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"

app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
watcher_service = WatcherService()
http_client: TCDDHttpClient | None = None


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
    payload = request.get_json(force=True) or {}
    config = config_from_mapping(payload)
    save_config(CONFIG_PATH, config)
    return jsonify({"ok": True, "config": config_to_dict(config)})


@app.get("/api/stations")
def api_stations() -> Any:
    client = get_client()
    stations = sorted(client.stations, key=lambda station: station.label)
    return jsonify([station_to_dict(station) for station in stations])


@app.post("/api/search")
def api_search() -> Any:
    payload = request.get_json(force=True) or {}
    config = config_from_mapping(payload)
    client = get_client()
    raw_payload = client.search(config)
    candidates = train_availability_candidates(raw_payload)
    matches, filter_reasons = filter_candidates_with_diagnostics(candidates, config)
    return jsonify(
        {
            "ok": True,
            "raw_candidate_count": len(candidates),
            "filter_rejections": filter_reasons,
            "matches": [candidate_to_dict(match) for match in matches],
            "first_candidates": [candidate_to_dict(candidate) for candidate in candidates[:20]],
        }
    )


@app.post("/api/watcher/start")
def api_watcher_start() -> Any:
    payload = request.get_json(force=True) or {}
    config = config_from_mapping(payload)
    save_config(CONFIG_PATH, config)
    watcher_service.start(config)
    return jsonify({"ok": True, "status": watcher_service.status_dict()})


@app.post("/api/watcher/stop")
def api_watcher_stop() -> Any:
    watcher_service.stop()
    return jsonify({"ok": True, "status": watcher_service.status_dict()})


@app.get("/api/watcher/status")
def api_watcher_status() -> Any:
    return jsonify({"ok": True, "status": watcher_service.status_dict()})


if __name__ == "__main__":
    host = os.environ.get("TCDD_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("TCDD_UI_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
