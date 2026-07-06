from __future__ import annotations

import streamlit as st

from .bootstrap import initialize_app_data


@st.cache_resource(show_spinner="Initializing quiz data...")
def initialize_streamlit_app_data() -> bool:
    initialize_app_data()
    return True
