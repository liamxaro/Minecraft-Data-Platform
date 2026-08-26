import streamlit as st

st.title("CurseForge")
st.write("CurseForge-specific dashboard content goes here.")

col1, col2, col3 = st.columns(3)
col1.metric("Projects", "9,875")
col2.metric("Latest Run", "2026-03-23")
col3.metric("Source", "CurseForge")