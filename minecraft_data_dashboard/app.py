import streamlit as st

st.set_page_config(
    page_title="Minecraft Data Dashboard",
    page_icon="assets/modrinth_icon_light.png",
    layout="wide",
)

modrinth_pages = [
    st.Page("pages/00_00_modrinth_overview.py", title="Modrinth Overview"),
    st.Page("pages/00_01_modrinth_mods.py", title="Modrinth Mods"),
]

curseforge_pages = [
    st.Page("pages/01_00_curseforge_overview.py", title="CurseForge Overview"),
]

pg = st.navigation(
    {
        "Modrinth": modrinth_pages,
        "CurseForge": curseforge_pages,
    },
    position="sidebar",
    expanded=True,
)

pg.run()