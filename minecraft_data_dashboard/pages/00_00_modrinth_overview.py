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
    page_icon="minecraft_data_dashboard/assets/modrinth_icon_light.png",
    layout="wide",
)

title_col, refresh_col = st.columns([6, 2], vertical_alignment="center")

# with title_col:
#     brand_page_title(
#         "Overview",
#         "High-level Modrinth metrics, category distribution, and time-based listing trends."
#     )

apply_modrinth_theme("Modrinth Source Overview")


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
# ---- KPI DELTAS FROM BRONZE HISTORY ----

snapshot_totals_df = (
    project_counts_df
    .groupby(
        "pull_date",
        as_index=False,
    )
    .agg(
        total_projects=(
            "project_count",
            "sum",
        ),
        total_downloads=(
            "total_downloads",
            "sum",
        ),
        total_authors=(
            "total_authors",
            "max",
        ),
    )
    .sort_values("pull_date")
)


project_delta = None
author_delta = None
download_delta = None


if len(snapshot_totals_df) >= 2:
    latest_snapshot = (
        snapshot_totals_df.iloc[-1]
    )

    previous_snapshot = (
        snapshot_totals_df.iloc[-2]
    )

    project_delta = int(
        latest_snapshot["total_projects"]
        - previous_snapshot["total_projects"]
    )

    author_delta = int(
        latest_snapshot["total_authors"]
        - previous_snapshot["total_authors"]
    )

    download_delta = int(
        latest_snapshot["total_downloads"]
        - previous_snapshot["total_downloads"]
    )

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
        unsafe_allow_html=True,
    )

kpi1, kpi2, kpi3, kpi4 = st.columns(4)


with kpi1:
    st.metric(
        "Total Projects",
        f"{kpis['total_projects']:,}",
        delta=(
            f"{project_delta:+,} since last pull"
            if project_delta is not None
            else None
        ),
    )


with kpi2:
    st.metric(
        "Total Authors",
        f"{kpis['total_authors']:,}",
        delta=(
            f"{author_delta:+,} since last pull"
            if author_delta is not None
            else None
        ),
    )


with kpi3:
    st.metric(
        "Total Downloads",
        f"{kpis['total_downloads']:,}",
        delta=(
            f"{download_delta:+,} since last pull"
            if download_delta is not None
            else None
        ),
    )


with kpi4:
    st.metric(
        "Total Project Types",
        f"{len(project_types_df)}",
    )


st.divider()


# ---- Project Type Distribution ----
brand_subheader("Project Type Distribution")

type_fig = px.pie(
    project_types_df,
    names="project_type",
    values="project_type_count",
)

style_modrinth_figure(type_fig)

st.plotly_chart(
    type_fig,
    width="stretch",
)


st.divider()


# ---- Prepare Historical Metrics ----
project_counts_df = (
    project_counts_df
    .sort_values(
        [
            "project_type",
            "pull_date",
        ]
    )
    .copy()
)

project_counts_df["pull_date"] = (
    project_counts_df["pull_date"]
    .astype(str)
)

date_order = (
    project_counts_df["pull_date"]
    .drop_duplicates()
    .tolist()
)

project_type_order = (
    project_counts_df
    .groupby(
        "project_type",
        as_index=False,
    )["project_count"]
    .sum()
    .sort_values(
        "project_count",
        ascending=False,
    )["project_type"]
    .tolist()
)


# ------------------------------------------------------------
# PROJECT LISTING METRICS
# ------------------------------------------------------------

project_counts_df["baseline_count"] = (
    project_counts_df
    .groupby("project_type")["project_count"]
    .transform("first")
)

project_counts_df["growth_pct"] = (
    (
        project_counts_df["project_count"]
        - project_counts_df["baseline_count"]
    )
    / project_counts_df["baseline_count"]
    * 100
)

project_counts_df["new_projects"] = (
    project_counts_df
    .groupby("project_type")["project_count"]
    .diff()
)


# ---- Project Type Growth Over Time ----
brand_subheader("Project Type Growth Over Time")

growth_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            project_counts_df["project_type"]
            == project_type
        ]
        .sort_values("pull_date")
    )

    growth_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["growth_pct"],
            name=project_type,
            mode="lines+markers",
            customdata=project_type_df[
                ["project_count"]
            ],
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Growth: %{y:.2f}%<br>"
                "Projects: %{customdata[0]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

growth_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Growth Since First Snapshot (%)",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

growth_fig.update_yaxes(
    ticksuffix="%"
)

style_modrinth_figure(
    growth_fig
)

st.plotly_chart(
    growth_fig,
    width="stretch",
)


# ---- Project Listings Trend by Category ----
brand_subheader("Project Listings Trend by Category")

line_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            project_counts_df["project_type"]
            == project_type
        ]
        .sort_values("pull_date")
    )

    line_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["project_count"],
            name=project_type,
            mode="lines+markers",
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Projects: %{y:,.0f}"
                "<extra></extra>"
            ),
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

style_modrinth_figure(
    line_fig
)

st.plotly_chart(
    line_fig,
    width="stretch",
)


# ---- New Projects Since Previous Snapshot ----
brand_subheader("New Projects Since Previous Snapshot")

new_projects_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            (
                project_counts_df["project_type"]
                == project_type
            )
            & (
                project_counts_df["new_projects"]
                .notna()
            )
        ]
        .sort_values("pull_date")
    )

    new_projects_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["new_projects"],
            name=project_type,
            mode="lines+markers",
            customdata=project_type_df[
                ["project_count"]
            ],
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "New Projects: %{y:+,.0f}<br>"
                "Total Projects: %{customdata[0]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

new_projects_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="New Projects",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

new_projects_fig.add_hline(
    y=0,
    line_dash="dash",
)

style_modrinth_figure(
    new_projects_fig
)

st.plotly_chart(
    new_projects_fig,
    width="stretch",
)


st.divider()


# ------------------------------------------------------------
# DOWNLOAD METRICS
# ------------------------------------------------------------

project_counts_df["baseline_downloads"] = (
    project_counts_df
    .groupby("project_type")["total_downloads"]
    .transform("first")
)

project_counts_df["download_growth_pct"] = (
    (
        project_counts_df["total_downloads"]
        - project_counts_df["baseline_downloads"]
    )
    / project_counts_df["baseline_downloads"]
    * 100
)

project_counts_df["new_downloads"] = (
    project_counts_df
    .groupby("project_type")["total_downloads"]
    .diff()
)


# ---- Total Downloads Over Time ----
brand_subheader("Total Downloads Over Time")

downloads_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            project_counts_df["project_type"]
            == project_type
        ]
        .sort_values("pull_date")
    )

    downloads_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["total_downloads"],
            name=project_type,
            mode="lines+markers",
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Downloads: %{y:,.0f}"
                "<extra></extra>"
            ),
        )
    )

downloads_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Total Downloads",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

style_modrinth_figure(
    downloads_fig
)

st.plotly_chart(
    downloads_fig,
    width="stretch",
)


# ---- Download Growth Over Time ----
brand_subheader("Download Growth Over Time")

download_growth_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            project_counts_df["project_type"]
            == project_type
        ]
        .sort_values("pull_date")
    )

    download_growth_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["download_growth_pct"],
            name=project_type,
            mode="lines+markers",
            customdata=project_type_df[
                ["total_downloads"]
            ],
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "Growth: %{y:.2f}%<br>"
                "Downloads: %{customdata[0]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

download_growth_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Growth Since First Snapshot (%)",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

download_growth_fig.update_yaxes(
    ticksuffix="%"
)

style_modrinth_figure(
    download_growth_fig
)

st.plotly_chart(
    download_growth_fig,
    width="stretch",
)


# ---- New Downloads Since Previous Snapshot ----
brand_subheader("New Downloads Since Previous Snapshot")

new_downloads_fig = go.Figure()

for project_type in project_type_order:
    project_type_df = (
        project_counts_df[
            (
                project_counts_df["project_type"]
                == project_type
            )
            & (
                project_counts_df["new_downloads"]
                .notna()
            )
        ]
        .sort_values("pull_date")
    )

    new_downloads_fig.add_trace(
        go.Scatter(
            x=project_type_df["pull_date"],
            y=project_type_df["new_downloads"],
            name=project_type,
            mode="lines+markers",
            customdata=project_type_df[
                ["total_downloads"]
            ],
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Date: %{x}<br>"
                "New Downloads: %{y:+,.0f}<br>"
                "Total Downloads: %{customdata[0]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

new_downloads_fig.update_layout(
    xaxis_title="Date",
    yaxis_title="New Downloads",
    xaxis=dict(
        type="category",
        categoryorder="array",
        categoryarray=date_order,
    ),
)

new_downloads_fig.add_hline(
    y=0,
    line_dash="dash",
)

style_modrinth_figure(
    new_downloads_fig
)

st.plotly_chart(
    new_downloads_fig,
    width="stretch",
)


st.divider()


# ---- Data Preview ----
brand_subheader("Data Preview")

st.dataframe(
    preview_df,
    width="stretch",
    hide_index=True,
)