import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from utils.db import (
    get_distinct_gameplay_categories,
    get_distinct_platform_loaders,
    get_distinct_mod_release_versions,
    get_mod_category_distribution,
    get_modrinth_kpis,
    get_most_popular_modrinth_projects)
from utils.theme import (
    apply_modrinth_theme,
    brand_page_title,
    brand_subheader,
    style_modrinth_figure,
    format_compact_number
)

st.set_page_config(
    page_icon="assets/modrinth_icon_light.png",
    layout="wide",
)

title_col, refresh_col = st.columns([6, 2], vertical_alignment="center")
apply_modrinth_theme('Modrinth Mod Analysis')

# ---- Useful functions for page ----
def format_metric_delta(current_value, previous_value, compact: bool = False) -> str | None:
    if previous_value is None:
        return None

    delta_value = current_value - previous_value

    if compact:
        return f"{'+' if delta_value >= 0 else ''}{format_compact_number(delta_value)}"

    return f"{delta_value:+,}"

# ---- LOAD DATA ----
@st.cache_data(ttl=30)
def load_kpis():
    return get_modrinth_kpis(project_type='mod')
def load_prev_kpis():
    return get_modrinth_kpis(project_type='mod')
@st.cache_data(ttl=30)
def load_popular_projects(gameplay_categories:str, platform_loaders: str, versions: str):
    return get_most_popular_modrinth_projects(
        project_type='mod',
        limit=100000,
        gameplay_categories=gameplay_categories,
        platform_loaders=platform_loaders,
        versions=versions)
@st.cache_data(ttl=30)
def load_gameplay_categories():
    return get_distinct_gameplay_categories(project_type='mod')
@st.cache_data(ttl=30)
def load_platform_loaders():
    return get_distinct_platform_loaders(project_type='mod')
@st.cache_data(ttl=30)
def load_versions():
    return get_distinct_mod_release_versions()
@st.cache_data(ttl=30)
def load_category_distribution():
    return get_mod_category_distribution()

kpi_df = load_kpis()
category_distribution_df = load_category_distribution()
gameplay_categories_df = load_gameplay_categories()
platform_loaders_df = load_platform_loaders()
versions_df = load_versions()

#---- KPIs ----
kpis = kpi_df.iloc[0]

with refresh_col:
    st.markdown(
        f"""
        <div style="
            text-align: right;
            font-style: italic;
            font-size: 14px;
            color: #bbbbbb;
        ">
            LAST REFRESH: {kpis['current_refresh_date']}
        </div>
        """,
        unsafe_allow_html=True
    )
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

with kpi1:
    st.metric("Total Mods", f"{kpis['total_mods']:,}")
with kpi2:
    st.metric("Total Mod Authors", f"{kpis['total_mod_authors']:,}")
with kpi3:
    st.metric("Total Mod Downloads", f"{format_compact_number(kpis['total_mod_downloads'])}")
with kpi4:
    st.metric('Total Mod Loaders', f'{kpis["total_distinct_platform_loaders"]:,}')
with kpi5:
    st.metric('Total Mod Gameplay Categories', f'{kpis["total_distinct_gameplay_categories"]:,}')
with kpi6:
    st.metric(label='Total Mod License Types', 
              value=f'{kpis["total_distinct_licenses"]:,}')

st.divider()

#---- General Mod Selection ----
brand_subheader("General Mod Selection")

gameplay_category_options = ["All"] + gameplay_categories_df["gameplay_category"].tolist()
platform_loader_options = ["All"] + platform_loaders_df["platform_loader"].tolist()
version_options = ["All"] + versions_df["version_id"].tolist()

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    selected_gameplay_categories = st.multiselect(
        "Filter Mods by Gameplay Category",
        options=gameplay_category_options,
        default=[],
    )

with filter_col2:
    selected_platform_loaders = st.multiselect(
        "Filter Mods by Platform Loader",
        options=platform_loader_options,
        default=[],
    )
    
with filter_col3:
    selected_versions = st.multiselect(
        "Filter Mods by Minecraft Version",
        options=version_options,
        default=[],
        placeholder="All versions",
    )

selected_gameplay_categories = [
    value for value in selected_gameplay_categories
    if value != "All"
]

selected_platform_loaders = [
    value for value in selected_platform_loaders
    if value != "All"
]

popular_mods_df = load_popular_projects(
    selected_gameplay_categories,
    selected_platform_loaders,
    selected_versions
)
st.dataframe(
    popular_mods_df,
    column_config={
        "latest_version": None,
        "description": st.column_config.TextColumn(
            "description",
            width="medium",
        ),
        "download_count": st.column_config.NumberColumn(
            "download_count",
            format="%,d",
        ),
        "follows": st.column_config.NumberColumn(
            "follows",
            format="%,d",
        ),
    },
    hide_index=True,
    width="stretch"
)
st.divider()

#---- CATEGORY DISTRIBUTION ----
brand_subheader("Mod Gameplay Category Distribution")
# sort once for downloads
downloads_df = (
    category_distribution_df
    .sort_values("total_downloads", ascending=False)
    .copy()
)

# sort once for project count
project_count_df = (
    category_distribution_df
    .sort_values("project_count", ascending=False)
    .copy()
)

# ---- Gameplay Categories by Total Downloads ----
brand_subheader("Gameplay Categories by Total Downloads")

downloads_fig = px.bar(
    downloads_df,
    x="total_downloads",
    y="gameplay_category",
    orientation="h",
)

downloads_fig.update_layout(
    xaxis_title="Total Downloads",
    yaxis_title="Gameplay Category",
    yaxis={"categoryorder": "total ascending"},
)

style_modrinth_figure(downloads_fig)
st.plotly_chart(downloads_fig, width="stretch")


# ---- Gameplay Categories by Project Count ----
brand_subheader("Gameplay Categories by Project Count")

project_count_fig = px.bar(
    project_count_df,
    x="project_count",
    y="gameplay_category",
    orientation="h",
)

project_count_fig.update_layout(
    xaxis_title="Project Count",
    yaxis_title="Gameplay Category",
    yaxis={"categoryorder": "total ascending"},
)

style_modrinth_figure(project_count_fig)
st.plotly_chart(project_count_fig, width="stretch")