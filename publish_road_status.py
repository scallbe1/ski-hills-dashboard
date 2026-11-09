#!/usr/bin/env python3
"""Alberta 511 road conditions from the Hwy 1/22 junction (Jct Hwy 1/22) to each ski resort.

Publishes retained MQTT discovery configs + state payloads to the Mosquitto
broker (see BROKER below) so Home Assistant shows one sensor per route.
Intended to run hourly from cron. Stdlib + paho-mqtt only.
"""
import json, time, urllib.request, urllib.parse, sys

BROKER = "192.168.1.183"  # <-- your MQTT broker host
JCT = (51.2247, -114.4993)  # Hwy 1/Hwy 22 interchange (Jct Hwy 1/22), west of Cochrane
RESORTS = {
    "nakiska":       ("Nakiska",          51.1005, -115.4923),
    "sunshine":      ("Sunshine Village", 51.0580, -115.7700),
    "lake_louise":   ("Lake Louise",      51.4490, -116.1790),
    "norquay":       ("Mt Norquay",       51.2100, -115.6400),
    "castle":        ("Castle Mountain",  49.3180, -114.4120),
    "panorama":      ("Panorama",         50.4420, -116.2124),
    "kicking_horse": ("Kicking Horse",    51.2940, -117.0600),
    "fernie":        ("Fernie",           49.4900, -114.7900),
}
RANK = {"closed": 9, "black ice": 8, "ice covered": 7, "partially covered": 6,
        "snow covered": 6, "bare wet": 4, "wet": 3, "bare": 2, "bare dry": 1,
        "clear": 0, "": 0}
DEVICE = {"ids": "road_ski_511", "name": "Ski Roads"}
RESORT_DEVICE = {"ids": "ski_resort_cams", "name": "Ski Resort Cams"}

# 511 CCTV cameras closest to each corridor (Alberta side only)
CAMERAS = {
    "kananaskis":  ("Kananaskis Hwy 742",   145),
    "banff":       ("Banff Hwy 1",          282),
    "lake_louise": ("Lake Louise TCH",      281),
    "westcastle":  ("Hwy 3 Westcastle",      86),
    "crowsnest":   ("Crowsnest Pass Hwy 3",  85),
    "hwy1_west":   ("Hwy 1 W of Hwy 22", 284),
}


def worst(conds):
    w, ws = -1, ""
    for c in conds:
        r = RANK.get(c.lower(), 5)
        if r > w:
            w, ws = r, c
    return ws or "Clear"


def fetch_route(name, lat, lon):
    body = {
        "Waypoints[0][name]": "Hwy 1 & Hwy 22",
        "Waypoints[0][point][latitude]": JCT[0],
        "Waypoints[0][point][longitude]": JCT[1],
        "Waypoints[1][name]": name,
        "Waypoints[1][point][latitude]": lat,
        "Waypoints[1][point][longitude]": lon,
    }
    req = urllib.request.Request(
        "https://511.alberta.ca/api/route/getroutes",
        data=urllib.parse.urlencode(body).encode(),
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "application/x-www-form-urlencoded"})
    st = json.load(urllib.request.urlopen(req, timeout=25))[0]["statistics"]
    conds = [lc["statusName"] for i in st["instructions"]
             for lc in i.get("linkConditions", [])]
    return {"km": round(st["lengthMeters"] / 1000, 1),
            "time": st["travelTimeDisplay"],
            "closed": bool(st["hasCurrentClosure"]),
            "condition": worst(conds)}


def main():
    results = {}
    for slug, (name, lat, lon) in RESORTS.items():
        try:
            results[slug] = fetch_route(name, lat, lon)
        except Exception as e:  # noqa: BLE001
            results[slug] = {"error": str(e)[:60]}
        time.sleep(0.4)

    ok = [r for r in results.values() if "error" not in r]
    n_ok = len(ok)
    alert = any(r.get("closed") or r.get("condition", "").lower()
                in ("black ice", "ice covered") for r in ok)
    overall = "Stale" if n_ok < 5 else ("Alert" if alert else "Clear")

    from paho.mqtt.client import Client, MQTTv311
    cli = Client(client_id="roadcheck-publisher", protocol=MQTTv311)
    cli.username_pw_set("roadcheck", open("/home/sean/.mqtt_pw").read().strip())  # <-- your broker password file
    cli.connect(BROKER, 1883, 30)
    cli.loop_start()

    def pub(topic, payload):
        cli.publish(topic, json.dumps(payload) if not isinstance(payload, str)
                    else payload, retain=True, qos=1)

    # discovery (retained; re-publishing is idempotent)
    def discover(slug, label, icon, **extra):
        cfg = {
            "name": label,
            "unique_id": f"road_ski_{slug}",
            "state_topic": f"road/ski/{slug}",
            "icon": icon,
            "device": DEVICE,
        }
        cfg.update({k: v for k, v in extra.items() if v is not None})
        pub(f"homeassistant/sensor/road_{slug}/config", cfg)

    discover("overall", "Roads to ski resorts", "mdi:car-arrow-right")
    for slug, (name, _, _) in RESORTS.items():
        discover(slug, f"{name} road", "mdi:snowboard")

    # corridor cameras (MQTT camera discovery: `topic` carries the JPEG bytes)
    for key, (label, cam_id) in CAMERAS.items():
        pub(f"homeassistant/camera/roadcam_{key}/config", {
            "name": label,
            "unique_id": f"road_cam_{key}",
            "topic": f"road/cams/{key}/image",
            "icon": "mdi:cctv",
            "device": DEVICE,
        })

    # resort webcams (one official camera per resort)
    RESORT_CAMS = {
        "nakiska":     ("Nakiska mountain cam",
                        "https://secure.skircr.com/cams/nacam3/nacam3.jpg"),
        "sunshine":    ("Sunshine Village cam",
                        "https://cameras.skibanff.com/dynamic/136m"),
        "lake_louise": ("Lake Louise summit cam",
                        "https://cams.skilouise.com/cam3hd.jpg"),
        "norquay":     ("Mt Norquay cam",
                        "https://opencctv.org/still/315276.jpg"),
        "castle":      ("Castle Mountain cam",
                        "https://skicastle.ca/images/7082/webcamimage.jpg"),
        "panorama":    ("Panorama mountain cam",
                        "https://opencctv.org/still/298980.jpg"),
        "kicking_horse": ("Kicking Horse Crystal Bowl cam",
                          "https://secure.skircr.com/cams/KHCAM7/CrystalBowl.jpg"),
        "fernie":      ("Fernie mountain cam",
                        "https://secure.skircr.com/cams/fecam1/image.jpg"),
    }
    for key, (label, _) in RESORT_CAMS.items():
        pub(f"homeassistant/camera/resortcam_{key}/config", {
            "name": label,
            "unique_id": f"ski_resort_cam_{key}",
            "topic": f"road/cams/resort_{key}/image",
            "icon": "mdi:cctv",
            "device": RESORT_DEVICE,
        })

    time.sleep(0.5)  # let queued discovery packets flush before states

    # camera images
    for key, (label, cam_id) in CAMERAS.items():
        try:
            req = urllib.request.Request(
                f"https://511.alberta.ca/map/Cctv/{cam_id}",
                headers={"User-Agent": "Mozilla/5.0"})
            img = urllib.request.urlopen(req, timeout=20).read()
            if img[:2] == b"\xff\xd8":
                cli.publish(f"road/cams/{key}/image", img, retain=True, qos=1)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)

    # resort webcam images (convert non-JPEG, e.g. Panorama's webp, to JPEG)
    for key, (label, url) in RESORT_CAMS.items():
        try:
            u = url + (f"?t={int(time.time())}" if "skibanff" in url else "")
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            img = urllib.request.urlopen(req, timeout=20).read()
            if img[:2] != b"\xff\xd8":
                import io
                from PIL import Image
                buf = io.BytesIO()
                Image.open(io.BytesIO(img)).convert("RGB").save(buf, "JPEG", quality=80)
                img = buf.getvalue()
            if len(img) > 8000:
                cli.publish(f"road/cams/resort_{key}/image", img, retain=True, qos=1)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)

    pub("road/ski/overall",
        f"{overall} · {n_ok}/8 routes from Jct Hwy 1/22 open · updated {time.strftime('%H:%M')}")
    for slug, (name, _, _) in RESORTS.items():
        r = results[slug]
        if "error" in r:
            pub(f"road/ski/{slug}", "no data")
        else:
            cond = r["condition"]
            icon = {"closed": "CLOSED"}.get(cond.lower(), cond)
            state = ("CLOSED · " if r["closed"] else "") + f"{r['time']} · {r['km']} km · {icon}"
            pub(f"road/ski/{slug}", state)

    time.sleep(20)  # flush ~1.5 MB of images before disconnect
    cli.loop_stop()
    cli.disconnect()
    print(json.dumps({"overall": overall, "ok": n_ok, "results": results}))


if __name__ == "__main__":
    sys.exit(main())
