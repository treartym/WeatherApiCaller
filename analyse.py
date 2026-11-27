from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import db


def makeWindows(readings, weather):
    reading = readings.copy()
    reading["Brightness"] = reading["Brightness"].replace(0, np.nan) #Replace brightness=0 with None

    reading["Slot"] = reading["Timestamp"].dt.floor("15min")
    groups = reading.groupby(["Library", "Floor", "Device_ID", "Slot"])
    medians = groups[["Noise", "Brightness"]].median()
    windows = medians.reset_index()

    if weather.empty:
        weather = pd.DataFrame({"Time": pd.Series(dtype="datetime64[ns, UTC]"), "shortwave_radiation": []})
    weather = weather.rename(columns={"shortwave_radiation": "Radiation"})[["Time", "Radiation"]]

    windows = pd.merge_asof(
        windows.sort_values("Slot"), weather.sort_values("Time"),
        left_on="Slot", right_on="Time",
        direction="backward", tolerance=pd.Timedelta("1h"),
    )
    return windows.drop(columns="Time")


def normalise(windows):
    referenceID = windows["Device_ID"].value_counts().idxmax()
    reference = windows[windows["Device_ID"] == referenceID][["Library", "Floor", "Slot", "Noise", "Brightness"]]
    merged = windows.merge(reference, on=["Library", "Floor", "Slot"], suffixes=("", "ref"))

    for col in ["Noise", "Brightness"]:
        offset = (merged[col + "ref"] - merged[col]).groupby(merged["Device_ID"]).median()
        windows[col] = windows[col] + windows["Device_ID"].map(offset).fillna(0)

    low = windows["Noise"].min()
    high = windows["Noise"].max()
    windows["Busy"] = (windows["Noise"] - low) / (high - low) if high > low else 0.5
    return windows


def libraryStats(windows, now):
    stats = {}
    windows["Hour"] = windows["Slot"].dt.tz_convert("Europe/Dublin").dt.hour

    for lib, g in windows.groupby("Library"):
        stat = {}

        d = g.dropna(subset=["Brightness", "Radiation"])
        if d["Radiation"].nunique() >= 2:
            slope, base = np.polyfit(d["Radiation"], d["Brightness"], 1)
            stat["Slope"], stat["Baseline"] = round(float(slope), 3), round(float(base), 1)

        stat["Hours"] = {str(h): round(float(b), 3) for h, b in g.groupby("Hour")["Busy"].mean().items()}
        live = g[g["Slot"] >= now - timedelta(minutes=30)]
        stat["LiveBusy"] = round(float(live["Busy"].mean()), 3) if len(live) else None

        stats[lib] = stat
        print(lib, stat)
    return stats


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    since = db.lastRun()
    readings = db.fetch("readings", "ServerTime", since)
    if not readings.empty:
        weather = db.fetch("weather", "Time", since - timedelta(hours=1) if since else None)
        windows = makeWindows(readings, weather)
        db.saveWindows(windows)
        print("saved", len(windows), "windows from", len(readings), "readings")

    windows = db.fetch("windows")
    if not windows.empty:
        db.saveStats(libraryStats(normalise(windows), now))

    db.setLastRun(now)
