from __future__ import annotations

import hmac

import streamlit as st

from .config import get_settings


def require_admin() -> None:
    settings = get_settings()
    if not settings.admin_password:
        st.error("Admin password is not configured.")
        st.stop()

    if st.session_state.get("admin_authenticated"):
        return

    st.title("Admin")
    password = st.text_input("Admin password", type="password")
    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(password, settings.admin_password):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()
