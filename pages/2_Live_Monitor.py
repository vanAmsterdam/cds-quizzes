from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - optional UI fallback
    st_autorefresh = None

from cds_quizzes.admin_auth import require_admin
from cds_quizzes.database import get_session_factory
from cds_quizzes.services import monitor_rows
from cds_quizzes.streamlit_runtime import initialize_streamlit_app_data


st.set_page_config(page_title="Live Monitor", page_icon=":material/monitoring:", layout="wide")
initialize_streamlit_app_data()
require_admin()

st.title("Live Monitor")
auto_refresh = st.toggle("Auto-refresh", value=True)
interval_seconds = st.slider("Refresh interval", min_value=2, max_value=30, value=5, step=1)
if auto_refresh and st_autorefresh is not None:
    st_autorefresh(interval=interval_seconds * 1000, key="live-monitor-refresh")
elif auto_refresh:
    st.caption("Install streamlit-autorefresh to enable automatic refresh.")

db = get_session_factory()()
try:
    df = pd.DataFrame(monitor_rows(db))
finally:
    db.close()

if df.empty:
    st.info("No rostered students yet.")
else:
    total = len(df)
    signed_in = int(df["signed_in"].sum())
    round0_done = int(df["round0_done"].sum())
    stale = df[(df["signed_in"]) & (~df["round0_done"])]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rostered", total)
    col2.metric("Signed in", signed_in)
    col3.metric("Round 0 done", round0_done)
    col4.metric("Signed in, missing Round 0", len(stale))

    st.subheader("Students")
    st.dataframe(df, width="stretch", hide_index=True)

    missing = df[~df["round0_done"]][["student_id", "group_id", "signed_in", "last_seen_at"]]
    if not missing.empty:
        st.subheader("Missing Round 0")
        st.dataframe(missing, width="stretch", hide_index=True)
