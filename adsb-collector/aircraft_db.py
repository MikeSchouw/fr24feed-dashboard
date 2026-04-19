import csv
import json
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get('DATA_DIR', '/data'))
AIRCRAFT_CSV = DATA_DIR / 'aircraftDatabase.csv'
OPERATORS_JSON = DATA_DIR / 'operators.json'

AIRCRAFT_DB_URL = 'https://opensky-network.org/datasets/metadata/aircraftDatabase.csv'
OPERATORS_DB_URL = 'https://raw.githubusercontent.com/mictronics/readsb-protobuf/dev/webapp/src/db/operators.json'


def _download(url: str, dest: Path, description: str) -> bool:
    logger.info(f'Downloading {description}...')
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        logger.info(f'{description} saved to {dest}')
        return True
    except Exception as e:
        logger.warning(f'Failed to download {description}: {e}')
        return False


def load_aircraft_db() -> dict:
    if not AIRCRAFT_CSV.exists():
        ok = _download(AIRCRAFT_DB_URL, AIRCRAFT_CSV, 'aircraft database (~40MB)')
        if not ok:
            logger.warning('Aircraft type/operator enrichment unavailable — type/model tags will be empty')
            return {}

    db: dict = {}
    try:
        with open(AIRCRAFT_CSV, newline='', encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                hex_code = row.get('icao24', '').lower().strip()
                if not hex_code:
                    continue
                db[hex_code] = {
                    'registration': row.get('registration', '').strip(),
                    'type': row.get('typecode', '').strip(),
                    'model': row.get('model', '').strip(),
                    'operator': row.get('operator', '').strip(),
                    'operator_icao': row.get('operatoricao', '').strip(),
                }
        logger.info(f'Loaded {len(db):,} aircraft records')
    except Exception as e:
        logger.error(f'Failed to parse aircraft database: {e}')
        return {}
    return db


def load_operators_db() -> dict:
    if not OPERATORS_JSON.exists():
        ok = _download(OPERATORS_DB_URL, OPERATORS_JSON, 'operators database')
        if not ok:
            return {}

    try:
        with open(OPERATORS_JSON) as f:
            raw = json.load(f)
        # {"KLM": {"n": "KLM Royal Dutch Airlines", ...}, ...}
        return {code: info.get('n', code) for code, info in raw.items()}
    except Exception as e:
        logger.error(f'Failed to parse operators database: {e}')
        return {}
