import os, json, urllib.parse, urllib.request
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

# Trinity College Dublin coordinates
LAT, LON = 53.34, -6.25
API = "https://api.open-meteo.com/v1/forecast"
VARS = ["cloud_cover", "shortwave_radiation", "direct_radiation", "diffuse_radiation", "wind_speed_10m"]


def initDb():
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
    firebase_admin.initialize_app(credentials.Certificate(key))
    return firestore.client()


def getJson(params):
    params.update({"latitude": LAT, "longitude": LON, "timezone": "UTC"})
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def parseTime(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


def makeDoc(values, time, kind, resolution):
    doc = {k: values.get(k) for k in VARS}
    doc.update({"Time": time, "Kind": kind, "Resolution": resolution, "Latitude": LAT, "Longitude": LON})
    return doc


def collectLive(db):
    current = getJson({"current": ",".join(VARS)})["current"]
    time = parseTime(current["time"])
    doc = makeDoc(current, time, "live", "15min")
    db.collection("weather").document(time.strftime("%Y-%m-%dT%H-%M")).set(doc)


if __name__ == "__main__":
    collectLive(initDb())