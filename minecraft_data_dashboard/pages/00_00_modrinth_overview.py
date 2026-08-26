import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from utils.db import (
    get_modrinth_overview_kpis,
    get_project_type_distribution,
    get_modrinth_project_listings_time_series,
    get_modrinth_overview_preview,
)
from utils.theme import (
    apply_modrinth_theme,
    brand_page_title,
    brand_subheader,
    style_modrinth_figure,
)

st.set_page_config(
    page_icon="assets/modrinth_icon_light.png",
    layout="wide",
)

title_col, refresh_col = st.columns([6, 2], vertical_alignment="center")

# with title_col:
#     brand_page_title(
#         "Overview",
#         "High-level Modrinth metrics, category distribution, and time-based listing trends."
#     )

apply_modrinth_theme('Modrinth Source Overview')


# ---- LOAD DATA ----
@st.cache_data(ttl=30)
def load_kpis():
    return get_modrinth_overview_kpis()

@st.cache_data(ttl=30)
def load_project_types():
    return get_project_type_distribution()

@st.cache_data(ttl=30)
def load_project_counts():
    return get_modrinth_project_listings_time_series()

@st.cache_data(ttl=30)
def load_preview():
    return get_modrinth_overview_preview()

kpi_df = load_kpis()
project_types_df = load_project_types()
project_counts_df = load_project_counts()
preview_df = load_preview()

# ---- KPIs ----
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
            LAST REFRESH: {kpis['last_refresh_date']}
        </div>
        """,
        unsafe_allow_html=True
    )
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric("Total Projects", f"{kpis['total_projects']:,}")
with kpi2:
    st.metric("Total Authors", f"{kpis['total_authors']:,}")
with kpi3:
    st.metric("Total Downloads", f"{kpis['total_downloads']:,}")
with kpi4:
    st.metric('Total Project Types', f'{len(project_types_df)}')
    

st.divider()
# ---- Project Type Distribution ----
brand_subheader("Project Type Distribution")

type_fig = px.pie(
    project_types_df,
    names="project_type",
    values="project_type_count",
)
style_modrinth_figure(type_fig)
st.plotly_chart(type_fig, width="stretch")

st.divider()
# ---- Project Listings Over Time (Stacked) ----
brand_subheader("Project Listings Over Time")

project_counts_df = project_counts_df.sort_values("pull_date").copy()
project_counts_df["pull_date"] = project_counts_df["pull_date"].astype(str)

stack_fig = go.Figure()

date_order = project_counts_df["pull_date"].drop_duplicates().tolist()

project_type_order = (
    project_counts_df.groupby("project_type", as_index=False)["project_count"]
    .sum()
    .sort_values("project_count", ascending=False)["project_type"]
    .tolist()
)

for project_type in project_type_order:
    project_type_df = project_counts_df[
        project_counts_df["project_type"] == project_type
    ].sort_values("pull_date")

    stack_fig.add_trace(
        go.Bar(
            x=project_type_df["pull_date"],
            y=project_type_df["project_count"],
            name=project_type,
        )
    )

stack_fig.update_layout(
    barmode="stack",
    xaxis_title="Date",
    yaxis_title="Project Count",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

style_modrinth_figure(stack_fig)
st.plotly_chart(stack_fig, width="stretch")

# ---- Project Listings Trend by Category ----
brand_subheader("Project Listings Trend by Category")

line_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = project_counts_df[
        project_counts_df["project_type"] == project_type
    ].sort_values("pull_date")

    line_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["project_count"],
            name=project_type,
            mode="lines+markers",
        )
    )

line_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Project Count",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

style_modrinth_figure(line_fig)
st.plotly_chart(line_fig, width="stretch")
st.divider()

# ---- Data Preview ----
brand_subheader("Data Preview")
st.dataframe(preview_df, width="stretch", hide_index=True)