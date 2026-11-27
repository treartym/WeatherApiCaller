import os
import numpy as np
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
firebase_admin.initialize_app(credentials.Certificate(key))
db = firestore.client()


def dateManage(docs):
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    for col in ["Timestamp", "ServerTime", "Time", "Slot"]:
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True).astype("datetime64[ns, UTC]")
    return df


def fixTypes(variable):
    if isinstance(variable, (float, np.floating)) and np.isnan(variable):
        return None
    if isinstance(variable, np.generic):
        return variable.item()
    return variable


def lastRun():
    doc = db.collection("state").document("analysis").get()
    if not doc.exists:
        return None
    return pd.Timestamp(doc.to_dict()["LastRun"]).floor("15min")


def setLastRun(time):
    db.collection("state").document("analysis").set({"LastRun": time})


def fetch(collection, time_field=None, since=None):
    docs = db.collection(collection)
    if since is not None:
        docs = docs.where(filter=FieldFilter(time_field, ">=", since))
    return dateManage(docs.stream())


def saveWindows(slots):
    batch = db.batch() 
    n = 0
    for row in slots.to_dict("records"):
        for k in row:
            row[k] = fixTypes(row[k])
        slot = row["Slot"].strftime("%Y-%m-%dT%H-%M")
        doc_id = f"{row['Library']}_{row['Floor']}_{row['Device_ID']}_{slot}"
        batch.set(db.collection("windows").document(doc_id), row)
        n += 1
        if n == 400:
            batch.commit()
            batch = db.batch()
            n = 0
    batch.commit()


def saveStats(stats):
    for lib, fields in stats.items():
        for k in fields:
            fields[k] = fixTypes(fields[k])
        db.collection("libraryStats").document(lib).set(fields)