from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import db


def make_windows(readings, weather):
    r = readings.copy()
    r.loc[r["Brightness"] == 0, "Brightness"] = np.nan  # 0 = camera covered, keep the noise

    # 4 second readings -> one row per library/floor/phone every 15 min (same as weather)
    r["Slot"] = r["Timestamp"].dt.floor("15min")
    w = r.groupby(["Library", "Floor", "Device_ID", "Slot"])[["Noise", "Brightness"]].median().reset_index()

    # attach outdoor light: latest weather reading at or before each window
    weather = weather.rename(columns={"shortwave_radiation": "Radiation"})[["Time", "Radiation"]]
    w = pd.merge_asof(
        w.sort_values("Slot"), weather.sort_values("Time"),
        left_on="Slot", right_on="Time",
        direction="backward", tolerance=pd.Timedelta("1h"),
    )
    return w.drop(columns="Time")


def normalise(w):
    # phone with the most windows is the reference, other phones are shifted to match it
    # using windows where both were in the same place at the same time
    ref = w["Device_ID"].value_counts().idxmax()
    r = w[w["Device_ID"] == ref][["Library", "Floor", "Slot", "Noise", "Brightness"]]
    m = w.merge(r, on=["Library", "Floor", "Slot"], suffixes=("", "_ref"))

    for col in ["Noise", "Brightness"]:
        offset = (m[col + "_ref"] - m[col]).groupby(m["Device_ID"]).median()
        w[col] = w[col] + w["Device_ID"].map(offset).fillna(0)

    # busyness 0 (quietest seen) to 1 (loudest seen)
    lo, hi = w["Noise"].min(), w["Noise"].max()
    w["Busy"] = (w["Noise"] - lo) / (hi - lo) if hi > lo else 0.5
    return w


def library_stats(w, now):
    stats = {}
    w["Hour"] = w["Slot"].dt.tz_convert("Europe/Dublin").dt.hour

    for lib, g in w.groupby("Library"):
        s = {}

        # brightness = Baseline + Slope * outdoor radiation
        d = g.dropna(subset=["Brightness", "Radiation"])
        if d["Radiation"].nunique() >= 2:
            slope, base = np.polyfit(d["Radiation"], d["Brightness"], 1)
            s["Slope"], s["Baseline"] = round(float(slope), 3), round(float(base), 1)

        # typical busyness per hour, plus live busyness from the last 30 min
        s["Hours"] = {str(h): round(float(b), 3) for h, b in g.groupby("Hour")["Busy"].mean().items()}
        live = g[g["Slot"] >= now - timedelta(minutes=30)]
        s["LiveBusy"] = round(float(live["Busy"].mean()), 3) if len(live) else None

        stats[lib] = s
        print(lib, s)
    return stats


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    since = db.last_run()

    readings = db.fetch("readings", "ServerTime", since)
    if not readings.empty:
        weather = db.fetch("weather", "Time", since - timedelta(hours=1) if since else None)
        w = make_windows(readings, weather)
        db.save_windows(w)
        print("saved", len(w), "windows from", len(readings), "readings")

    w = db.fetch("windows")
    if not w.empty:
        db.save_stats(library_stats(normalise(w), now))

    db.set_last_run(now)
