import json
import logging
import os
import time
from datetime import date
from pathlib import Path

import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from aircraft_db import load_aircraft_db, load_operators_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DUMP1090_URL = os.environ.get("DUMP1090_URL", "http://fr24feed:8080")
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.environ["INFLUXDB_TOKEN"]
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "adsb")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "adsb")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SEEN_FILE = DATA_DIR / "seen_today.json"


def load_seen_set() -> tuple[set, date]:
    """Restore today's seen set from disk. Returns empty set if file is from a previous day."""
    try:
        data = json.loads(SEEN_FILE.read_text())
        saved_date = date.fromisoformat(data["date"])
        if saved_date == date.today():
            seen = set(data["seen"])
            logger.info(f"Restored {len(seen)} seen flights from {SEEN_FILE}")
            return seen, saved_date
    except Exception:
        pass
    return set(), date.today()


def save_seen_set(seen: set, today: date) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(
            json.dumps({"date": today.isoformat(), "seen": list(seen)})
        )
    except Exception as e:
        logger.warning(f"Failed to persist seen set: {e}")


def resolve_operator(callsign: str, ac_info: dict, operators_db: dict) -> str:
    if ac_info.get("operator"):
        return ac_info["operator"]
    op_icao = ac_info.get("operator_icao", "").upper()
    if op_icao and op_icao in operators_db:
        return operators_db[op_icao]
    if callsign and len(callsign) >= 3:
        prefix = callsign[:3].upper()
        if prefix in operators_db:
            return operators_db[prefix]
    return "unknown"


def wait_for_influxdb(client: InfluxDBClient) -> None:
    while True:
        try:
            client.ping()
            logger.info("InfluxDB is ready")
            return
        except Exception:
            logger.info("Waiting for InfluxDB...")
            time.sleep(5)


def main() -> None:
    logger.info("Loading databases...")
    aircraft_db = load_aircraft_db()
    operators_db = load_operators_db()

    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    wait_for_influxdb(client)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    seen, current_day = load_seen_set()

    logger.info(f"Polling {DUMP1090_URL}/data/aircraft.json every {POLL_INTERVAL}s")

    while True:
        today = date.today()
        if today != current_day:
            seen.clear()
            current_day = today
            save_seen_set(seen, today)
            logger.info("New day — seen set reset")

        try:
            resp = requests.get(f"{DUMP1090_URL}/data/aircraft.json", timeout=5)
            resp.raise_for_status()
            aircraft_list = resp.json().get("aircraft", [])
        except Exception as e:
            logger.warning(f"Fetch failed: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        points = []
        for ac in aircraft_list:
            hex_code = ac.get("hex", "").lower().strip()
            callsign = ac.get("flight", "").strip()
            if not hex_code:
                continue

            # One record per (hex, callsign, day).
            # - Same aircraft, same callsign, same day → dedup.
            # - Same aircraft, different callsign (new flight) → new hit.
            # - Same aircraft, same callsign, next day → new hit.
            key = f"{hex_code}:{callsign}:{today}"
            if key in seen:
                continue
            seen.add(key)

            ac_info = aircraft_db.get(hex_code, {})
            altitude = ac.get("altitude", 0)
            if altitude == "ground":
                altitude = 0

            point = (
                Point("flights")
                .tag("hex", hex_code)
                .tag("callsign", callsign or "unknown")
                .tag("type", ac_info.get("type") or "unknown")
                .tag("model", ac_info.get("model") or "unknown")
                .tag("operator", resolve_operator(callsign, ac_info, operators_db))
                .tag("registration", ac_info.get("registration") or "unknown")
                .field("count", 1)
                .field("altitude_ft", int(altitude) if altitude else 0)
            )
            points.append(point)

        if points:
            write_api.write(bucket=INFLUXDB_BUCKET, record=points)
            save_seen_set(seen, today)
            logger.info(f"Wrote {len(points)} new flight(s)")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
