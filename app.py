import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import time
import json

# ---------------- CONFIG ----------------
DATABASE_URL = "https://conductivity-monitor-default-rtdb.asia-southeast1.firebasedatabase.app/"

# ---------------- FIREBASE INIT ----------------
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_KEY"])
    cred = credentials.Certificate(cred_dict)

    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })

# ---------------- SESSION STATE ----------------
if "running" not in st.session_state:
    st.session_state.running = False

if "paused" not in st.session_state:
    st.session_state.paused = False

if "csv_data" not in st.session_state:
    st.session_state.csv_data = []

if "start_ref" not in st.session_state:
    st.session_state.start_ref = None

# ---------------- UI ----------------
st.set_page_config(page_title="Conductivity Dashboard", layout="wide")

st.title("🔬 Advanced Conductivity Dashboard")

experiment = st.text_input("Experiment Name", "experiment_1")

col1, col2, col3 = st.columns(3)

start_btn = col1.button("▶ Start")
pause_btn = col2.button("⏸ Pause / Resume")
stop_btn  = col3.button("⏹ Stop")

live_placeholder = st.empty()
graph_placeholder = st.empty()
table_placeholder = st.empty()

# ---------------- FUNCTIONS ----------------
def fetch_data(exp):
    ref = db.reference(f'conductivity_data/{exp}')
    data = ref.get()

    if data is None:
        return pd.DataFrame()

    df = pd.DataFrame(data).T
    df.index = pd.to_datetime(df.index.astype(int), unit='s')

    return df.sort_index()

def delete_experiment_data(exp):
    root_ref = db.reference('conductivity_data')
    root_ref.child(exp).delete()

# ---------------- BUTTON LOGIC ----------------
if start_btn:
    st.session_state.running = True
    st.session_state.paused = False
    st.session_state.csv_data = []
    st.session_state.start_ref = None

if pause_btn:
    st.session_state.paused = not st.session_state.paused

if stop_btn:
    st.session_state.running = False
    st.session_state.paused = False
    st.session_state.start_ref = None

    # -------- SAVE CSV --------
    if st.session_state.csv_data:
        df_csv = pd.DataFrame(st.session_state.csv_data)
        filename = f"{experiment}.csv"
        df_csv.to_csv(filename, index=False)

        with open(filename, "rb") as f:
            st.download_button("📥 Download CSV", f, file_name=filename)

    # -------- DELETE FIREBASE --------
    delete_experiment_data(experiment)

    # -------- RESET --------
    st.session_state.csv_data = []

    live_placeholder.empty()
    graph_placeholder.empty()
    table_placeholder.empty()

    st.success("✅ Experiment stopped, Firebase cleared & reset")

    time.sleep(1)
    st.rerun()

# ---------------- MAIN LOOP ----------------
if st.session_state.running:

    if not st.session_state.paused:

        df = fetch_data(experiment)

        if df.empty:
            st.warning("⏳ Waiting for ESP32 data...")
        else:
            # -------- SET START TIME --------
            if st.session_state.start_ref is None:
                st.session_state.start_ref = df.index[0]

            # -------- TIME RESET --------
            elapsed = (df.index - st.session_state.start_ref).total_seconds() / 60
            df["time_min"] = elapsed

            # -------- LIVE VALUE --------
            latest = df.iloc[-1]["conductivity"]
            live_placeholder.metric("Live Conductivity (uS/cm)", round(latest, 2))

            # -------- GRAPH --------
            graph_df = df[["time_min", "conductivity"]]
            graph_df = graph_df[graph_df["time_min"] >= 0]
            graph_df.set_index("time_min", inplace=True)

            graph_placeholder.line_chart(graph_df)

            # -------- TABLE (5 MIN INTERVAL) --------
            table_df = df.copy()
            table_df = table_df[table_df["time_min"] >= 0]

            table_df["time_5min"] = (table_df["time_min"] // 5) * 5
            table_df = table_df.groupby("time_5min").last().reset_index()

            table_display = table_df[["time_5min", "conductivity"]]
            table_display.rename(columns={"time_5min": "Time (min)"}, inplace=True)

            table_placeholder.dataframe(table_display)

            # -------- CSV STORAGE --------
            if len(st.session_state.csv_data) == 0 or \
               table_display.iloc[-1]["Time (min)"] != st.session_state.csv_data[-1]["Time (min)"]:

                st.session_state.csv_data.append({
                    "Time (min)": table_display.iloc[-1]["Time (min)"],
                    "Conductivity": table_display.iloc[-1]["conductivity"]
                })

    else:
        st.warning("⏸ Experiment Paused")

    # -------- UPDATE EVERY 1 MIN --------
    time.sleep(60)
    st.rerun()

else:
    st.info("Press ▶ Start to begin experiment")