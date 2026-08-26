import streamlit as st

st.title("Combined")
st.write("Combined dashboard content goes here.")

col1, col2, col3 = st.columns(3)
col1.metric("Projects", "22,215")
col2.metric("Latest Run", "2026-03-23")
col3.metric("Sources", "2")