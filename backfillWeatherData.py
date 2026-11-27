import sys
from datetime import datetime, timezone

from weatherDataInput import VARS, initDb, getJson, parseTime, makeDoc

def backfill(db, days):
    hourly = getJson({"hourly": ",".join(VARS), "past_days": days, "forecast_days": 1})["hourly"]
    now = datetime.now(timezone.utc)
    batch = db.batch()
    n = 0

    for i, text in enumerate(hourly["time"]):
        time = parseTime(text)
        if time > now:
            continue
        row = {k: hourly[k][i] for k in VARS}
        doc = makeDoc(row, time, "historical", "hourly")
        batch.set(db.collection("weather").document("hist_" + time.strftime("%Y-%m-%dT%H-%M")), doc)
        n += 1
        if n == 400:
            batch.commit()
            batch = db.batch()
            n = 0
    batch.commit()


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    backfill(initDb(), days)