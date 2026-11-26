import os
from datetime import timedelta

import numpy as np
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
firebase_admin.initialize_app(credentials.Certificate(key))
db = firestore.client()


def to_df(docs):
    df = pd.DataFrame([d.to_dict() for d in docs])
    for c in ["Timestamp", "ServerTime", "Time", "Slot"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True).astype("datetime64[ns, UTC]")
    return df


def fix(v):
    # Firestore can't store numpy types or NaN
    if isinstance(v, (float, np.floating)) and np.isnan(v):
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def last_run():
    doc = db.collection("state").document("analysis").get()
    if not doc.exists:
        return None
    # back to the start of the 15 min slot so a half-finished window gets rebuilt
    return pd.Timestamp(doc.to_dict()["LastRun"]).floor("15min")


def set_last_run(t):
    db.collection("state").document("analysis").set({"LastRun": t})


def fetch(collection, time_field=None, since=None):
    q = db.collection(collection)
    if since is not None:
        q = q.where(filter=FieldFilter(time_field, ">=", since))
    return to_df(q.stream())


def save_windows(w):
    batch, n = db.batch(), 0
    for row in w.to_dict("records"):
        row = {k: fix(v) for k, v in row.items()}
        doc_id = f"{row['Library']}_{row['Floor']}_{row['Device_ID']}_{row['Slot']:%Y-%m-%dT%H-%M}"
        batch.set(db.collection("windows").document(doc_id), row)
        n += 1
        if n == 400:
            batch.commit()
            batch, n = db.batch(), 0
    batch.commit()


def save_stats(stats):
    for lib, fields in stats.items():
        db.collection("library_stats").document(lib).set({k: fix(v) for k, v in fields.items()})
