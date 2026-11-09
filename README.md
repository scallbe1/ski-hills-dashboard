# Ski Hills dashboard — export for sharing

A Home Assistant dashboard ("Ski Hills") with two tabs:

1. **Ski Conditions** — per-resort cards (open, base, powder now, snow next 24 h,
   runs/lifts) for 8 resorts + one live webcam per resort, refreshed hourly.
2. **Road Conditions** — drive time / distance / worst surface condition per
   route from the Hwy 1 & Hwy 22 junction (Jct Hwy 1/22, west of Cochrane) to
   each resort, from the Alberta 511 route API, plus 6 Alberta 511 highway
   cameras.

## What's in this zip

| File | Purpose |
|---|---|
| `dashboard-definition.json` | The dashboard registry entry (url_path `ski-conditions`, title, icon) |
| `dashboard-tabs.json` | The full Lovelace config for both tabs |
| `publish_road_status.py` | The hourly publisher that creates ALL `sensor.*road*` and `camera.*` entities (roads + resort cams) via MQTT discovery |

## What Hal needs installed first

1. **ski_conditions custom integration** (HACS/marketplace: `4-the-vibes/ha-ski-conditions`)
   with subentries for: nakiska, sunshine_village, lake_louise, norquay,
   castle_mountain, panorama, kicking_horse, fernie.
   The Ski Conditions tab reads `sensor.<resort>_base_depth`, `_powder_depth`,
   `_snowfall_24h`, `_runs_open`, `_lifts_open`, `_resort_status`.
2. **Mosquitto broker add-on** (or any MQTT broker) + the MQTT integration in HA.
3. **Python 3 + paho-mqtt + Pillow** on any always-on machine, plus an hourly cron:
   `5 * * * * python3 publish_road_status.py`
   Edit the broker/host constants near the top of the script; set your MQTT
   password where marked `<MQTT_PASSWORD>`.
   Run it once manually — it auto-creates every sensor and camera entity
   (MQTT discovery), including the 8 resort webcams and 6 Alberta 511 cameras.

## Importing the dashboard

Option A — API (run on the HA box in the Advanced SSH add-on):

```
ha websocket  # or use the dashboard UI edit mode instead
```

Option B — UI:
1. Overview → Edit dashboards → **Add dashboard** → "New dashboard", url_path
   `ski-conditions`, title `Ski Hills`, icon `mdi:ski-cross-country`.
2. Edit the dashboard → three-dot menu → **Edit in YAML** (Raw config editor) and
   paste the contents of `dashboard-tabs.json`. Save.

## Notes

- The resort webcam feeds come from each resort's official server (or
  opencctv.org where the resort blocks scrapers); the publisher re-fetches and
  republishes them hourly and normalizes everything to JPEG.
- The road tab is Alberta 511-specific (route API + CCTV JPEGs). For a different
  origin, edit `ORIGIN` and `RESORTS` in `publish_road_status.py`.
- Cameras are MQTT cameras: the image bytes are published to
  `road/cams/<name>/image`; do not add `image_topic` in discovery (dropped key).
