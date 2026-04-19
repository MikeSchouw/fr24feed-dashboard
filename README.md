# fr24feeds-dashboard

A self-hosted ADS-B flight tracking dashboard that goes beyond what FlightRadar24's default feeder dashboard offers.

## Why I built this

The built-in FR24 feeder dashboard tells you useful but shallow things: how many aircraft you're seeing, your range, your feed status. What it doesn't tell you is anything *interesting* about what's flying over your antenna.

I wanted to know:
- **Which airlines and operators** are in my coverage area
- **The actual tail numbers** (registrations) of aircraft I'm tracking
- **Flight numbers** linked to physical airframes
- **Local persistent data** — something I own and can query, not just live stats that disappear

So I built a small collector that polls my local dump1090 feed, enriches each aircraft with data from the OpenSky Network aircraft database and the readsb operators database, and writes it all into InfluxDB. Grafana sits on top and turns it into a dashboard I actually want to look at.

## Screenshot

<!-- Add a screenshot of your Grafana dashboard here -->

## How it works

```
RTL-SDR dongle
     │
     ▼
fr24feed-piaware  ◄──── feeds data to FlightRadar24 & FlightAware
     │
     │  dump1090 JSON API (port 8080)
     ▼
adsb-collector (Python)
  - polls /data/aircraft.json every 10s
  - enriches each hex code against OpenSky aircraft DB (~40 MB CSV)
  - resolves airline name from ICAO callsign prefix via readsb operators DB
  - deduplicates: one record per (hex, callsign, day)
  - writes enriched Points to InfluxDB
     │
     ▼
InfluxDB 2  ──────────────────────────────────►  Grafana
  - stores: hex, callsign, registration,           - Total flights today/week
    type, model, operator, altitude                - Top operators by count
                                                   - Aircraft type breakdown
                                                   - Flight number list
```

The collector runs inside Docker alongside the other services. Aircraft and operator databases are downloaded on first start and cached in a Docker volume.

## Stack

| Service | Image |
|---------|-------|
| ADS-B decoder + feeder | `thomx/fr24feed-piaware` |
| Data collector | custom Python (this repo) |
| Time-series database | `influxdb:2` |
| Dashboard | `grafana/grafana` |

## Setup

1. Copy the example env file and fill in your values:
   ```bash
   cp .env.example .env
   ```

2. Required values to change:
   - `FR24KEY` — your FlightRadar24 sharing key
   - `PIAWARE_ID` — your PiAware feeder ID
   - `LAT` / `LON` — your antenna location
   - `NAME` — a label for your station
   - `INFLUXDB_PASSWORD` / `INFLUXDB_TOKEN` / `GRAFANA_PASSWORD` — set strong secrets

3. Start everything:
   ```bash
   make update
   ```

4. Open Grafana at `http://localhost:3000` (default credentials in your `.env`)

## Commands

```bash
make update          # pull latest images and restart all services
make clear-database  # wipe InfluxDB and start fresh
```

## Grafana provisioning

The dashboard and InfluxDB datasource are auto-provisioned from `grafana/provisioning/`. No manual setup needed after first boot.

## Data sources

- Aircraft database: [OpenSky Network](https://opensky-network.org/datasets/metadata/)
- Operators database: [mictronics/readsb-protobuf](https://github.com/mictronics/readsb-protobuf)
