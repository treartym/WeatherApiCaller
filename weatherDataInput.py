import argparse, os, json, urllib.parse, urllib.request
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

#Trinity College Dublin corrdinates
LAT, LON = 53.34, -6.25
API = "https://api.open-meteo.com/v1/forecast"
VARS = [
    "cloud_cover",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "wind_speed_10m",
]


def init_db():
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
    cred = credentials.Certificate(key)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def get_json(params):
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def parse_time(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


def doc_id(prefix, t):
    return prefix + t.strftime("%Y-%m-%dT%H-%M")


def collectLive(db):
    
    data = get_json({
        "latitude": LAT, "longitude": LON,
        "current": ",".join(VARS), "timezone": "UTC",
    })

    cur = data["current"]
    t = parse_time(cur["time"])

    doc = {k: cur.get(k) for k in VARS}
    doc.update({
        "Time": t,
        "Kind": "live",
        "Resolution": "15min",
        "Latitude": LAT,
        "Longitude": LON,
    })
    db.collection("weather").document(doc_id("", t)).set(doc)


def backfill(db, days):
    data = get_json({
        "latitude": LAT, "longitude": LON,
        "hourly": ",".join(VARS), "timezone": "UTC",
        "past_days": days, "forecast_days": 1,
    })
    h = data["hourly"]
    now = datetime.now(timezone.utc)
    batch, n = db.batch(), 0

    for i, ts in enumerate(h["time"]):
        t = parse_time(ts)
        if t > now:
            continue
        doc = {k: h[k][i] for k in VARS}
        doc.update({
            "Time": t,
            "Kind": "historical",
            "Resolution": "hourly",
            "Latitude": LAT,
            "Longitude": LON,
        })
        batch.set(db.collection("weather").document(doc_id("hist_", t)), doc)
        n += 1
        if n == 400:
            batch.commit()
            batch = db.batch()
            n = n - 400
    batch.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int)
    args = ap.parse_args()

    db = init_db()
    if args.backfill:
        backfill(db, args.backfill)
    else:
        collectLive(db)