import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from utils.db import (
    get_first_activity,
    get_distinct_gameplay_categories,
    get_distinct_mod_loaders,
    get_distinct_mod_release_versions,
    get_mod_category_distribution,
    get_mod_loader_distribution,
    get_mod_version_distribution,
    get_modrinth_kpis,
    get_project_listings,
    get_project_versions,
    get_modrinth_trending_signals,
    get_modrinth_hottest_signals,
    get_modrinth_fan_signals,
    get_modrinth_activity_signals,
    get_modrinth_category_momentum_signals,
    get_modrinth_story_queue
)
from utils.theme import (
    apply_modrinth_theme,
    brand_page_title,
    brand_subheader,
    style_modrinth_figure,
    format_compact_number,
)

st.set_page_config(
    page_icon="assets/modrinth_icon_light.png",
    layout="wide",
)

first_activity = get_first_activity(project_type="mod").iloc[0]["first_activity_date"]

title_col, refresh_col = st.columns([6, 2], vertical_alignment="center")
apply_modrinth_theme("Modrinth Mod Analysis",
                     f"First recorded mod activity at Modrinth: {first_activity}")


# ---- Useful functions for page ----
def format_metric_delta(
    current_value,
    previous_value,
    compact: bool = False,
) -> str | None:
    if previous_value is None:
        return None

    delta_value = current_value - previous_value

    if compact:
        return (
            f"{'+' if delta_value >= 0 else ''}"
            f"{format_compact_number(delta_value)}"
        )

    return f"{delta_value:+,}"


def display_distribution_chart(
    distribution_df,
    dimension_column: str,
    dimension_label: str,
    title: str,
    date_column: str | None = None,
):
    chart_df = distribution_df.copy()

    chart_df["download_share"] = (
        chart_df["total_downloads"]
        / chart_df["total_downloads"].sum()
        * 100
    )

    chart_df["project_share"] = (
        chart_df["project_count"]
        / chart_df["project_count"].sum()
        * 100
    )

    if date_column:
        chart_df[date_column] = pd.to_datetime(
            chart_df[date_column]
        )

        chart_df = chart_df.sort_values(
            date_column,
            ascending=False,
        )

        chart_df["dimension_display"] = (
            chart_df[date_column]
            .dt.strftime("%Y-%m-%d")
            + " - "
            + chart_df[dimension_column].astype(str)
        )

        y_column = "dimension_display"

        category_order = (
            chart_df["dimension_display"]
            .tolist()
        )

    else:
        y_column = dimension_column
        category_order = None

    chart_long_df = chart_df.melt(
        id_vars=y_column,
        value_vars=[
            "download_share",
            "project_share",
        ],
        var_name="metric",
        value_name="percentage",
    )

    chart_long_df["metric"] = (
        chart_long_df["metric"]
        .replace({
            "download_share": "Downloads",
            "project_share": "Projects",
        })
    )

    brand_subheader(title)

    fig = px.bar(
        chart_long_df,
        x="percentage",
        y=y_column,
        color="metric",
        orientation="h",
        barmode="group",
    )

    if date_column:
        fig.update_layout(
            xaxis_title="Share of Total (%)",
            yaxis_title=dimension_label,
            yaxis={
                "categoryorder": "array",
                "categoryarray": category_order,
                "autorange": "reversed",
            },
            legend_title=None,
        )

    else:
        fig.update_layout(
            xaxis_title="Share of Total (%)",
            yaxis_title=dimension_label,
            yaxis={
                "categoryorder": "total ascending",
            },
            legend_title=None,
        )

    style_modrinth_figure(fig)

    st.plotly_chart(
        fig,
        width="stretch",
    )

# ---- LOAD DATA ----
@st.cache_data(ttl=30)
def load_project_listings(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False
):
    return get_project_listings(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_project_id=selected_project_id,
        selected_author_id=selected_author_id,
        selected_search=selected_search,
    )
    
@st.cache_data(ttl=30)
def load_project_versions(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False
):
    return get_project_versions(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_project_id=selected_project_id,
        selected_author_id=selected_author_id,
        selected_search=selected_search,
    )


@st.cache_data(ttl=30)
def load_kpis():
    return get_modrinth_kpis(
        project_type="mod"
    )

@st.cache_data(ttl=30)
def load_prev_kpis():
    return get_modrinth_kpis(
        project_type="mod"
    )


@st.cache_data(ttl=30)
def load_gameplay_categories():
    return get_distinct_gameplay_categories(
        project_type="mod"
    )


@st.cache_data(ttl=30)
def load_platform_loaders():
    return get_distinct_mod_loaders()


@st.cache_data(ttl=30)
def load_versions():
    return get_distinct_mod_release_versions()


@st.cache_data(ttl=30)
def load_category_distribution():
    return get_mod_category_distribution()


@st.cache_data(ttl=30)
def load_loader_distribution():
    return get_mod_loader_distribution()


@st.cache_data(ttl=30)
def load_version_distribution():
    return get_mod_version_distribution()

@st.cache_data(ttl=30)
def load_trending_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False):
    return get_modrinth_trending_signals(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_search=selected_search,
    ) 

@st.cache_data(ttl=30)
def load_hottest_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False):
    return get_modrinth_hottest_signals(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_search=selected_search,
    )
    
@st.cache_data(ttl=30)
def load_fan_signals(project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False):
    return get_modrinth_fan_signals(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_search=selected_search,
    )

@st.cache_data(ttl=30)
def load_activity_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
):
    return get_modrinth_activity_signals(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_search=selected_search,
    )


@st.cache_data(ttl=30)
def load_category_momentum_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
):
    return get_modrinth_category_momentum_signals(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
    )


@st.cache_data(ttl=30)
def load_story_queue(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False
):
    return get_modrinth_story_queue(
        project_type=project_type,
        selected_gameplay_categories=selected_gameplay_categories,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_search=selected_search
    )

kpi_df = load_kpis()
category_distribution_df = load_category_distribution()
loader_distribution_df = load_loader_distribution()
version_distribution_df = load_version_distribution()
gameplay_categories_df = load_gameplay_categories()
platform_loaders_df = load_platform_loaders()
versions_df = load_versions()


# ---- KPIs ----
current_kpis = kpi_df.loc[
    kpi_df["snapshot"] == "current"
].iloc[0]

previous_kpis = kpi_df.loc[
    kpi_df["snapshot"] == "previous"
].iloc[0]

total_projects_delta = (
    current_kpis["total_projects"]
    - previous_kpis["total_projects"]
)

total_authors_delta = (
    current_kpis["total_authors"]
    - previous_kpis["total_authors"]
)

total_downloads_delta = (
    current_kpis["total_downloads"]
    - previous_kpis["total_downloads"]
)

mod_loaders_delta = (
    current_kpis["total_distinct_platform_loaders"]
    - previous_kpis["total_distinct_platform_loaders"]
)

mod_gameplay_categories_delta = (
    current_kpis["total_distinct_gameplay_categories"]
    - previous_kpis["total_distinct_gameplay_categories"]
)

mod_license_types_delta = (
    current_kpis["total_distinct_licenses"]
    - previous_kpis["total_distinct_licenses"]
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
            LAST REFRESH: {current_kpis['current_refresh_date']}
        </div>
        """,
        unsafe_allow_html=True,
    )

current_kpi1, current_kpi2, current_kpi3, current_kpi4, current_kpi5, current_kpi6 = st.columns(6)

with current_kpi1:
    st.metric(
        "Mods",
        f"{current_kpis['total_projects']:,}",
        delta=total_projects_delta
    )

with current_kpi2:
    st.metric(
        "Mod Authors",
        f"{current_kpis['total_authors']:,}",
        delta=total_authors_delta
    )

with current_kpi3:
    st.metric(
        "Mod Downloads",
        f"{format_compact_number(current_kpis['total_downloads'])}",
        delta=total_downloads_delta
    )

with current_kpi4:
    st.metric(
        "Mod Loaders",
        f"{current_kpis['total_distinct_platform_loaders']:,}",
        delta=mod_loaders_delta
    )

with current_kpi5:
    st.metric(
        "Mod Gameplay Categories",
        f"{current_kpis['total_distinct_gameplay_categories']:,}",
        delta=mod_gameplay_categories_delta
    )

with current_kpi6:
    st.metric(
        label="Mod License Types",
        value=f"{current_kpis['total_distinct_licenses']:,}",
        delta=mod_license_types_delta
    )

st.divider()


# ---- General Mod Selection ----
brand_subheader("Project Listing Selection for Mods")

gameplay_category_options = (
    ["All"]
    + gameplay_categories_df["name"].tolist()
)

platform_loader_options = (
    ["All"]
    + platform_loaders_df["platform_loaders"].tolist()
)

version_options = (
    ["All"]
    + versions_df["version"].tolist()
)

row_count_placeholder = st.empty()

with st.form("project_listings_filter_form"):

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    filter_col4, filter_col5, filter_col6 = st.columns(3)

    with filter_col1:
        selected_listings_gameplay_categories = st.multiselect(
            "Filter Mods by Gameplay Category",
            options=gameplay_category_options,
            default=[],
            key="listings_gameplay_category_multiselect"
        )

    with filter_col2:
        selected_listings_platform_loaders = st.multiselect(
            "Filter Mods by Platform Loader",
            options=platform_loader_options,
            default=[],
            key="listings_platform_loader_multiselect"
        )

    with filter_col3:
        selected_listings_versions = st.multiselect(
            "Filter Mods by Minecraft Version",
            options=version_options,
            default=[],
            placeholder="All versions",
            key="listings_version_multiselect"
        )

    with filter_col4:
        selected_listings_project_id = st.text_input(
            "Filter Mods by Project ID",
            placeholder="Enter a specific project ID (CASE SENSITIVE)",
            key="listings_project_id_input"
        )

    with filter_col5:
        selected_listings_author_id = st.text_input(
            "Filter Mods by Author ID",
            placeholder="Enter a specific author ID (CASE SENSITIVE)",
            key="listings_author_id_input"
        )

    with filter_col6:
        selected_listings_search = st.toggle(
            "Match All Filters (ON) or Any Filter (OFF)",
            value=False,
            key="listings_search_toggle"
        )

    search_col1, search_col2 = st.columns([4,1])

    with search_col2:
        selected_listings_submit = st.form_submit_button(
            "Search Mods",
            type="primary",
            use_container_width=True,
        )

selected_listings_gameplay_categories = [
    value
    for value in selected_listings_gameplay_categories
    if value != "All"
]

selected_listings_platform_loaders = [
    value
    for value in selected_listings_platform_loaders
    if value != "All"
]

selected_listings_versions = [
    value
    for value in selected_listings_versions
    if value != "All"
]

if selected_listings_submit:
    
    st.session_state["project_listings_df"] =load_project_listings(
        project_type="mod",
        selected_gameplay_categories=selected_listings_gameplay_categories,
        selected_platform_loaders=selected_listings_platform_loaders,
        selected_versions=selected_listings_versions,
        selected_project_id=selected_listings_project_id if selected_listings_project_id else None,
        selected_author_id=selected_listings_author_id if selected_listings_author_id else None,
        selected_search=selected_listings_search
    )
    
    project_listings_df = st.session_state["project_listings_df"]

    row_count_placeholder.caption(
        f"{len(project_listings_df):,} records loaded"
    )

    st.dataframe(
        project_listings_df,
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
        width="stretch",
    )


brand_subheader("Project Version Selection for Mods")

row_count_placeholder = st.empty()

with st.form("project_versions_filter_form"):

    filter_version_col1, filter_version_col2, filter_version_col3 = st.columns(3)
    filter_version_col4, filter_version_col5, filter_version_col6 = st.columns(3)

    with filter_version_col1:
        selected_versions_gameplay_categories = st.multiselect(
            "Filter Mods by Gameplay Category",
            options=gameplay_category_options,
            default=[],
            key="versions_gameplay_category_multiselect"
        )

    with filter_version_col2:
        selected_versions_platform_loaders = st.multiselect(
            "Filter Mods by Platform Loader",
            options=platform_loader_options,
            default=[],
            key="versions_platform_loader_multiselect"
        )

    with filter_version_col3:
        selected_versions_versions = st.multiselect(
            "Filter Mods by Minecraft Version",
            options=version_options,
            default=[],
            placeholder="All versions",
            key="versions_version_multiselect"
        )

    with filter_version_col4:
        selected_versions_project_id = st.text_input(
            "Filter Mods by Project ID",
            placeholder="Enter a specific project ID (CASE SENSITIVE)",
            key="versions_project_id_input"
        )

    with filter_version_col5:
        selected_versions_author_id = st.text_input(
            "Filter Mods by Author ID",
            placeholder="Enter a specific author ID (CASE SENSITIVE)",
            key="versions_author_id_input"
        )

    with filter_version_col6:
        selected_versions_search = st.toggle(
            "Match All Filters (ON) or Any Filter (OFF)",
            value=False,
            key="versions_search_toggle"
        )

    search_col1, search_col2 = st.columns([4,1])

    with search_col2:
        selected_versions_submit = st.form_submit_button(
            "Search Mods",
            type="primary",
            use_container_width=True,
        )
    
selected_versions_gameplay_categories = [
    value
    for value in selected_versions_gameplay_categories
    if value != "All"
]

selected_versions_platform_loaders = [
    value
    for value in selected_versions_platform_loaders
    if value != "All"
]

selected_versions_versions = [ #yes its supposed to be selected_versions_versions (selected mod versions from the modrinth_versions table)
    value
    for value in selected_versions_versions
    if value != "All"
]

if selected_versions_submit:
    st.session_state["project_versions_df"] = load_project_versions(
        project_type="mod",
        selected_gameplay_categories=selected_versions_gameplay_categories,
        selected_platform_loaders=selected_versions_platform_loaders,
        selected_versions=selected_versions_versions,
        selected_project_id=selected_versions_project_id if selected_versions_project_id else None,
        selected_author_id=selected_versions_author_id if selected_versions_author_id else None,
        selected_search=selected_versions_search
    )
    
    project_versions_df = st.session_state["project_versions_df"]

    row_count_placeholder.caption(
        f"{len(project_versions_df):,} records loaded"
    )

    st.dataframe(
        project_versions_df,
        column_config={
            "downloads": st.column_config.NumberColumn(
                "downloads",
                format="%,d",
        )
    },
    hide_index=True,
    width="stretch",
)


st.divider()


# ---- DISTRIBUTIONS ----
display_distribution_chart(
    distribution_df=category_distribution_df,
    dimension_column="gameplay_category",
    dimension_label="Gameplay Category",
    title="Gameplay Category Distribution",
)

display_distribution_chart(
    distribution_df=loader_distribution_df,
    dimension_column="platform_loader",
    dimension_label="Platform Loader",
    title="Platform Loader Distribution",
)

display_distribution_chart(
    distribution_df=version_distribution_df,
    dimension_column="version",
    dimension_label="Minecraft Version",
    title="Minecraft Version Distribution",
    date_column="release_time",
)

st.divider()

##############################
######Trends and Momentum#####
##############################
def build_trend_velocity_comparison_figure(
    trending_signals_df,
    limit: int = 30,
):
    chart_df = (
        trending_signals_df
        .sort_values(
            "trend_rank",
            ascending=True,
        )
        .head(limit)
        .sort_values(
            "trend_rank",
            ascending=False,
        )
    )

    figure = px.bar(
        chart_df,
        x=[
            "baseline_velocity",
            "current_velocity",
        ],
        y="title",
        orientation="h",
        barmode="group",
        hover_data={
            "trend_rank": True,
            "trend_score": ":.1f",
            "current_downloads_gained": ":,",
            "velocity_ratio": ":.2f",
            "velocity_lift": ":,.1f",
        },
        labels={
            "title": "Mod",
            "value": "Downloads / Hour",
            "variable": "Rate",
            "baseline_velocity": "Normal Rate",
            "current_velocity": "Current Rate",
            "trend_rank": "Trend Rank",
            "trend_score": "Trend Score",
            "current_downloads_gained": (
                "Downloads Gained"
            ),
            "velocity_ratio": "Times Normal",
            "velocity_lift": "Velocity Lift",
        },
        title="Current vs Normal Download Rate",
    )

    figure.for_each_trace(
        lambda trace: trace.update(
            name=(
                "Normal"
                if trace.name == "baseline_velocity"
                else "Current"
            )
        )
    )

    figure.update_layout(
        xaxis_title="Downloads / Hour",
        yaxis_title=None,
        legend_title_text=None,
    )

    return style_modrinth_figure(
        figure
    )
    
def build_top_trending_figure(
    trending_signals_df,
    limit: int = 20,
):
    chart_df = (
        trending_signals_df
        .sort_values(
            "trend_rank",
            ascending=True,
        )
        .head(limit)
        .sort_values(
            "trend_score",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="trend_score",
        y="title",
        orientation="h",
        hover_data={
            "trend_rank": True,
            "current_downloads": ":,",
            "current_downloads_gained": ":,",
            "current_velocity": ":,.1f",
            "baseline_velocity": ":,.1f",
            "velocity_ratio": ":.2f",
            "velocity_lift": ":,.1f",
        },
        labels={
            "title": "Mod",
            "trend_score": (
                "Trend Score"
            ),
            "trend_rank": (
                "Trend Rank"
            ),
            "current_downloads": (
                "Total Downloads"
            ),
            "current_downloads_gained": (
                "Downloads Gained"
            ),
            "current_velocity": (
                "Current Downloads / Hour"
            ),
            "baseline_velocity": (
                "Baseline Downloads / Hour"
            ),
            "velocity_ratio": (
                "Times Normal"
            ),
            "velocity_lift": (
                "Velocity Lift"
            ),
        },
        title="Top Trending Mods",
    )

    figure.update_layout(
        xaxis_title="Trend Score",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )
    
def build_hottest_mods_figure(
    hottest_signals_df,
):
    chart_df = hottest_signals_df.sort_values(
        "current_velocity",
        ascending=True,
    )

    figure = px.bar(
        chart_df,
        x="current_velocity",
        y="title",
        orientation="h",
        hover_data={
            "current_downloads": ":,",
            "current_downloads_gained": ":,",
            "baseline_velocity": ":,.1f",
            "velocity_ratio": ":.2f",
            "velocity_lift": ":,.1f",
            "trend_score": ":.1f",
            "trend_rank": True,
        },
        labels={
            "title": "Mod",
            "current_velocity": (
                "Downloads / Hour"
            ),
            "current_downloads": (
                "Total Downloads"
            ),
            "current_downloads_gained": (
                "Downloads Gained"
            ),
            "baseline_velocity": (
                "Baseline Downloads / Hour"
            ),
            "velocity_ratio": (
                "Times Normal"
            ),
            "velocity_lift": (
                "Velocity Lift"
            ),
            "trend_score": (
                "Trend Score"
            ),
            "trend_rank": (
                "Trend Rank"
            ),
        },
        title="Hottest Mods Right Now",
    )

    figure.update_layout(
        xaxis_title=(
            "Current Downloads / Hour"
        ),
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )
    

with st.form(
    "signal_filters"
):
    
    filter_momentum_col1, filter_momentum_col2, filter_momentum_col3 = st.columns(3)
    filter_momentum_col4, filter_momentum_col5, filter_momentum_col6 = st.columns(3)
    
    with filter_momentum_col1:
        selected_momentum_gameplay_categories = st.multiselect(
            "Gameplay Categories",
            options=gameplay_category_options,
            key="momentum_gameplay_categories_multiselect"
        )

    with filter_momentum_col2:
        selected_momentum_versions = st.multiselect(
            "Minecraft Versions",
            options=version_options,
            key="momentum_versions_multiselect"
        )

    with filter_momentum_col3:
        selected_momentum_platform_loaders = st.multiselect(
            "Platform Loaders",
            options=platform_loader_options,
            key="momentum_platform_loader_multiselect"
        )

    with filter_momentum_col6:
        selected_momentum_search = st.toggle(
            "Match All Filters (ON) or Any Filter (OFF)",
            value=False
        )
        
    apply_col1, apply_col2 = st.columns([4,1])

    with apply_col2:
        submitted_momentum = st.form_submit_button(
            "Apply Filters",
            type='primary',
            use_container_width=True
        )
        
st.subheader(
    "Discovery"
)

if submitted_momentum:
    st.session_state["trending_signals_df"] = load_trending_signals(
        project_type="mod",
        selected_gameplay_categories=selected_momentum_gameplay_categories,
        selected_platform_loaders=selected_momentum_platform_loaders,
        selected_versions=selected_momentum_versions,
        selected_search=selected_momentum_search
    )
    
    st.session_state['hottest_signals_df'] = load_hottest_signals(
        project_type="mod",
        selected_gameplay_categories=selected_momentum_gameplay_categories,
        selected_platform_loaders=selected_momentum_platform_loaders,
        selected_versions=selected_momentum_versions,
        selected_search=selected_momentum_search
    )
    
    trending_signals_df = st.session_state["trending_signals_df"]
    hottest_signals_df = st.session_state['hottest_signals_df']
    
    
    mod_momentum_figure = (
        build_trend_velocity_comparison_figure(
            trending_signals_df
        )
    )

    st.plotly_chart(
        mod_momentum_figure,
        use_container_width=True,
    )


    left_column, right_column = st.columns(
        2
    )


    with left_column:
        top_trending_figure = (
            build_top_trending_figure(
                trending_signals_df,
                limit=15,
            )
        )

        st.plotly_chart(
            top_trending_figure,
            use_container_width=True,
        )


    with right_column:
        hottest_mods_figure = (
            build_hottest_mods_figure(
                hottest_signals_df
            )
        )

        st.plotly_chart(
            hottest_mods_figure,
            use_container_width=True,
        )
        
st.divider()

st.subheader("Audience")

def build_fan_affinity_score_figure(
    fan_signals_df,
    limit: int = 15,
):
    chart_df = (
        fan_signals_df
        .sort_values(
            "fan_affinity_rank",
            ascending=True,
        )
        .head(limit)
        .sort_values(
            "fan_affinity_score",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="fan_affinity_score",
        y="title",
        orientation="h",
        hover_data={
            "follows": ":,",
            "current_downloads": ":,",
            "follows_per_1000_downloads": ":.2f",
            "follow_rate_percentile": ":.3f",
            "follower_count_percentile": ":.3f",
        },
        labels={
            "title": "Mod",
            "fan_affinity_score": "Fan Affinity Score",
            "follows": "Followers",
            "current_downloads": "Downloads",
            "follows_per_1000_downloads": (
                "Follows / 1K Downloads"
            ),
            "follow_rate_percentile": (
                "Affinity Percentile"
            ),
            "follower_count_percentile": (
                "Follower Count Percentile"
            ),
        },
        title="Most Dedicated Fan Bases",
    )

    figure.update_layout(
        xaxis_title="Fan Affinity Score",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

def build_highest_fan_affinity_figure(
    fan_signals_df,
    limit: int = 15,
):
    chart_df = (
        fan_signals_df
        .sort_values(
            "follows_per_1000_downloads",
            ascending=False,
        )
        .head(limit)
        .sort_values(
            "follows_per_1000_downloads",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="follows_per_1000_downloads",
        y="title",
        orientation="h",
        hover_data={
            "follows": ":,",
            "current_downloads": ":,",
            "fan_affinity_score": ":.1f",
            "fan_affinity_rank": True,
        },
        labels={
            "title": "Mod",
            "follows_per_1000_downloads": (
                "Follows / 1K Downloads"
            ),
            "follows": "Followers",
            "current_downloads": "Downloads",
            "fan_affinity_score": (
                "Fan Affinity Score"
            ),
            "fan_affinity_rank": (
                "Fan Affinity Rank"
            ),
        },
        title="Highest Fan Affinity",
    )

    figure.update_layout(
        xaxis_title="Follows / 1K Downloads",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

def build_largest_fan_bases_figure(
    fan_signals_df,
    limit: int = 15,
):
    chart_df = (
        fan_signals_df
        .sort_values(
            "follows",
            ascending=False,
        )
        .head(limit)
        .sort_values(
            "follows",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="follows",
        y="title",
        orientation="h",
        hover_data={
            "current_downloads": ":,",
            "follows_per_1000_downloads": ":.2f",
            "fan_affinity_score": ":.1f",
            "fan_affinity_rank": True,
        },
        labels={
            "title": "Mod",
            "follows": "Followers",
            "current_downloads": "Downloads",
            "follows_per_1000_downloads": (
                "Follows / 1K Downloads"
            ),
            "fan_affinity_score": (
                "Fan Affinity Score"
            ),
            "fan_affinity_rank": (
                "Fan Affinity Rank"
            ),
        },
        title="Largest Fan Bases",
    )

    figure.update_layout(
        xaxis_title="Followers",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

if submitted_momentum:
    st.session_state["fan_signals_df"] = load_fan_signals(
        project_type="mod",
        selected_gameplay_categories=selected_momentum_gameplay_categories,
        selected_platform_loaders=selected_momentum_platform_loaders,
        selected_versions=selected_momentum_versions,
        selected_search=selected_momentum_search)
    
    fan_signals_df = st.session_state["fan_signals_df"]
    
    fan_affinity_figure = (
        build_fan_affinity_score_figure(
            fan_signals_df,
            limit=15,
        )
    )

    st.plotly_chart(
        fan_affinity_figure,
        use_container_width=True,
    )


    left_column, right_column = st.columns(
        2
    )


    with left_column:
        highest_fan_affinity_figure = (
            build_highest_fan_affinity_figure(
                fan_signals_df,
                limit=15,
            )
        )

        st.plotly_chart(
            highest_fan_affinity_figure,
            use_container_width=True,
        )


    with right_column:
        largest_fan_bases_figure = (
            build_largest_fan_bases_figure(
                fan_signals_df,
                limit=15,
            )
        )

        st.plotly_chart(
            largest_fan_bases_figure,
            use_container_width=True,
        )
    
st.divider()

st.subheader("Activity")

def build_activity_score_figure(
    activity_signals_df,
    limit: int = 15,
):
    chart_df = (
        activity_signals_df
        .sort_values(
            "activity_rank",
            ascending=True,
        )
        .head(limit)
        .sort_values(
            "activity_score",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="activity_score",
        y="title",
        orientation="h",
        hover_data={
            "activity_rank": True,
            "latest_version_number": True,
            "latest_version_type": True,
            "days_since_latest_release": ":.1f",
            "current_downloads_gained": ":,",
            "current_velocity": ":,.1f",
            "active_release_days_last_30_days": True,
            "active_release_days_last_90_days": True,
            "trend_rank": True,
        },
        labels={
            "title": "Mod",
            "activity_score": "Activity Score",
            "activity_rank": "Activity Rank",
            "latest_version_number": "Latest Version",
            "latest_version_type": "Version Type",
            "days_since_latest_release": "Days Since Release",
            "current_downloads_gained": "Downloads Gained",
            "current_velocity": "Downloads / Hour",
            "active_release_days_last_30_days": (
                "Active Release Days — 30 Days"
            ),
            "active_release_days_last_90_days": (
                "Active Release Days — 90 Days"
            ),
            "trend_rank": "Trend Rank",
        },
        title="Recently Updated + Getting Attention",
    )

    figure.update_layout(
        xaxis_title="Activity Score",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

def build_most_recently_updated_figure(
    activity_signals_df,
    limit: int = 15,
):
    chart_df = (
        activity_signals_df
        .sort_values(
            "days_since_latest_release",
            ascending=True,
        )
        .head(limit)
        .copy()
    )

    chart_df["release_recency_score"] = (
        chart_df["release_recency_percentile"]
        * 100
    )

    chart_df = chart_df.sort_values(
        "release_recency_score",
        ascending=True,
    )

    figure = px.bar(
        chart_df,
        x="release_recency_score",
        y="title",
        orientation="h",
        hover_data={
            "latest_version_number": True,
            "latest_version_type": True,
            "latest_release_at": True,
            "days_since_latest_release": ":.1f",
            "current_downloads_gained": ":,",
            "current_velocity": ":,.1f",
            "activity_score": ":.1f",
        },
        labels={
            "title": "Mod",
            "release_recency_score": "Release Recency Score",
            "latest_version_number": "Latest Version",
            "latest_version_type": "Version Type",
            "latest_release_at": "Latest Release",
            "days_since_latest_release": "Days Since Release",
            "current_downloads_gained": "Downloads Gained",
            "current_velocity": "Downloads / Hour",
            "activity_score": "Activity Score",
        },
        title="Most Recently Updated",
    )

    figure.update_layout(
        xaxis_title="Release Recency Score",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

def build_most_active_development_figure(
    activity_signals_df,
    limit: int = 15,
):
    chart_df = (
        activity_signals_df
        .sort_values(
            [
                "active_release_days_last_30_days",
                "active_release_days_last_90_days",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .head(limit)
        .sort_values(
            "active_release_days_last_30_days",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="active_release_days_last_30_days",
        y="title",
        orientation="h",
        hover_data={
            "active_release_days_last_90_days": True,
            "latest_version_number": True,
            "latest_version_type": True,
            "days_since_latest_release": ":.1f",
            "current_downloads_gained": ":,",
            "current_velocity": ":,.1f",
            "activity_score": ":.1f",
        },
        labels={
            "title": "Mod",
            "active_release_days_last_30_days": (
                "Active Release Days — 30 Days"
            ),
            "active_release_days_last_90_days": (
                "Active Release Days — 90 Days"
            ),
            "latest_version_number": "Latest Version",
            "latest_version_type": "Version Type",
            "days_since_latest_release": "Days Since Release",
            "current_downloads_gained": "Downloads Gained",
            "current_velocity": "Downloads / Hour",
            "activity_score": "Activity Score",
        },
        title="Most Active Development",
    )

    figure.update_layout(
        xaxis_title="Active Release Days — Last 30 Days",
        yaxis_title=None,
    )

    return style_modrinth_figure(
        figure
    )

if submitted_momentum:
    st.session_state["activity_signals_df"] = load_activity_signals(
        project_type="mod",
        selected_gameplay_categories=selected_momentum_gameplay_categories,
        selected_platform_loaders=selected_momentum_platform_loaders,
        selected_versions=selected_momentum_versions,
        selected_search=selected_momentum_search,
    )

    activity_signals_df = st.session_state["activity_signals_df"]

    if not activity_signals_df.empty:
        activity_score_figure = (
            build_activity_score_figure(
                activity_signals_df,
                limit=15,
            )
        )

        st.plotly_chart(
            activity_score_figure,
            use_container_width=True,
        )

        left_column, right_column = st.columns(2)

        with left_column:
            most_recently_updated_figure = (
                build_most_recently_updated_figure(
                    activity_signals_df,
                    limit=15,
                )
            )

            st.plotly_chart(
                most_recently_updated_figure,
                use_container_width=True,
            )

        with right_column:
            most_active_development_figure = (
                build_most_active_development_figure(
                    activity_signals_df,
                    limit=15,
                )
            )

            st.plotly_chart(
                most_active_development_figure,
                use_container_width=True,
            )

    else:
        st.info(
            "No activity signals match the selected filters."
        )


st.divider()

st.subheader("Content")

st.caption(
    "Content opportunity scores and ranks are recalculated "
    "within the selected filter universe."
)

def build_content_opportunity_figure(
    content_signals_df,
    limit: int = 15,
):
    chart_df = (
        content_signals_df
        .sort_values(
            "content_opportunity_rank",
            ascending=True,
        )
        .head(limit)
        .sort_values(
            "content_opportunity_score",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="content_opportunity_score",
        y="title",
        orientation="h",
        hover_data={
            "content_opportunity_rank": True,
            "cross_signal_count": True,
            "discovery_score": ":.1f",
            "audience_score": ":.1f",
            "development_activity_score": ":.1f",
            "trend_rank": True,
            "breakout_rank": True,
            "activity_rank": True,
            "current_downloads": ":,",
            "current_downloads_gained": ":,",
        },
        labels={
            "title": "Mod",
            "content_opportunity_score": (
                "Content Opportunity Score"
            ),
            "content_opportunity_rank": (
                "Content Opportunity Rank"
            ),
            "cross_signal_count": "Strong Signals",
            "discovery_score": "Discovery Score",
            "audience_score": "Audience Score",
            "development_activity_score": "Activity Score",
            "trend_rank": "Trend Rank",
            "breakout_rank": "Breakout Rank",
            "activity_rank": "Activity Rank",
            "current_downloads": "Total Downloads",
            "current_downloads_gained": "Downloads Gained",
        },
        title="Top Content Opportunities",
    )

    figure.update_layout(
        xaxis_title="Content Opportunity Score",
        yaxis_title=None,
    )

    figure.update_xaxes(
        range=[0, 100],
    )

    return style_modrinth_figure(
        figure
    ) 

def build_content_signal_breakdown_figure(
    content_signals_df,
    limit: int = 10,
):
    top_content_df = (
        content_signals_df
        .sort_values(
            "content_opportunity_rank",
            ascending=True,
        )
        .head(limit)
        .copy()
    )

    title_order = (
        top_content_df["title"]
        .tolist()
    )

    chart_df = top_content_df.melt(
        id_vars=[
            "title",
            "content_opportunity_rank",
            "content_opportunity_score",
        ],
        value_vars=[
            "discovery_score",
            "audience_score",
            "development_activity_score",
        ],
        var_name="signal_family",
        value_name="signal_score",
    )

    signal_labels = {
        "discovery_score": "Discovery",
        "audience_score": "Audience",
        "development_activity_score": "Activity",
    }

    chart_df["signal_family"] = (
        chart_df["signal_family"]
        .map(signal_labels)
    )

    chart_df = chart_df.dropna(
        subset=[
            "signal_score",
        ]
    )

    figure = px.bar(
        chart_df,
        x="signal_score",
        y="title",
        color="signal_family",
        orientation="h",
        barmode="group",
        hover_data={
            "content_opportunity_rank": True,
            "content_opportunity_score": ":.1f",
            "signal_score": ":.1f",
        },
        labels={
            "title": "Mod",
            "signal_score": "Signal Score",
            "signal_family": "Signal",
            "content_opportunity_rank": "Content Rank",
            "content_opportunity_score": "Content Score",
        },
        title="Why These Are Content Opportunities",
    )

    figure.update_layout(
        xaxis_title="Signal Score",
        yaxis_title=None,
        legend_title_text=None,
    )

    figure.update_xaxes(
        range=[0, 100],
    )

    figure.update_yaxes(
        categoryorder="array",
        categoryarray=title_order[::-1],
    )

    return style_modrinth_figure(
        figure
    )

def build_content_corroboration_figure(
    content_signals_df,
    limit: int = 15,
):
    chart_df = (
        content_signals_df[
            content_signals_df["cross_signal_count"] >= 2
        ]
        .copy()
    )

    chart_df["support_strength_percent"] = (
        chart_df["support_strength"]
        * 100
    )

    chart_df = (
        chart_df
        .sort_values(
            [
                "support_strength",
                "content_opportunity_score",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .head(limit)
        .sort_values(
            "support_strength_percent",
            ascending=True,
        )
    )

    figure = px.bar(
        chart_df,
        x="support_strength_percent",
        y="title",
        orientation="h",
        hover_data={
            "content_opportunity_rank": True,
            "content_opportunity_score": ":.1f",
            "cross_signal_count": True,
            "discovery_score": ":.1f",
            "audience_score": ":.1f",
            "development_activity_score": ":.1f",
        },
        labels={
            "title": "Mod",
            "support_strength_percent": (
                "Corroboration Strength"
            ),
            "content_opportunity_rank": "Content Rank",
            "content_opportunity_score": "Content Score",
            "cross_signal_count": "Strong Signals",
            "discovery_score": "Discovery Score",
            "audience_score": "Audience Score",
            "development_activity_score": "Activity Score",
        },
        title="Most Corroborated Opportunities",
    )

    figure.update_layout(
        xaxis_title="Supporting Signal Strength (%)",
        yaxis_title=None,
    )

    figure.update_xaxes(
        range=[0, 100],
    )

    return style_modrinth_figure(
        figure
    )

if submitted_momentum:
    st.session_state["story_queue_df"] = load_story_queue(
        project_type="mod",
        selected_gameplay_categories=selected_momentum_gameplay_categories,
        selected_platform_loaders=selected_momentum_platform_loaders,
        selected_versions=selected_momentum_versions,
        selected_search=selected_momentum_search,
    )

    story_queue_df = st.session_state["story_queue_df"]

    # Content shows actual opportunities, while Story Queue keeps
    # every project in the filtered universe.
    content_signals_df = (
        story_queue_df
        .copy()
        .rename(
            columns={
                "story_priority_rank": "content_opportunity_rank",
                "story_priority_score": "content_opportunity_score",
            }
        )
    )

    if not content_signals_df.empty:
        content_opportunity_figure = (
            build_content_opportunity_figure(
                content_signals_df,
                limit=15,
            )
        )

        st.plotly_chart(
            content_opportunity_figure,
            use_container_width=True,
        )

        content_left_column, content_right_column = st.columns(2)

        with content_left_column:
            signal_breakdown_figure = (
                build_content_signal_breakdown_figure(
                    content_signals_df,
                    limit=10,
                )
            )

            st.plotly_chart(
                signal_breakdown_figure,
                use_container_width=True,
            )

        with content_right_column:
            corroborated_df = (
                content_signals_df[
                    content_signals_df["cross_signal_count"] >= 2
                ]
                .copy()
            )

            if not corroborated_df.empty:
                corroboration_figure = (
                    build_content_corroboration_figure(
                        content_signals_df,
                        limit=15,
                    )
                )

                st.plotly_chart(
                    corroboration_figure,
                    use_container_width=True,
                )

            else:
                st.info(
                    "No multi-signal opportunities match "
                    "the selected filters."
                )

    else:
        st.info(
            "No content opportunities match the selected filters."
        )


st.divider()

def build_story_queue_display_df(
    story_queue_df,
    limit: int = 50,
):
    display_df = (
        story_queue_df
        .sort_values(
            "story_priority_rank",
            ascending=True,
        )
        .head(limit)
        .copy()
    )

    display_df = display_df[
        [
            "story_priority_rank",
            "global_story_priority_rank",
            "title",
            "primary_story_type",
            "story_priority_score",
            "global_story_priority_score",
            "story_reason",
            "current_downloads_gained",
            "discovery_score",
            "audience_score",
            "development_activity_score",
            "cross_signal_count",
            "strongest_momentum_category",
            "strongest_category_momentum_score",
        ]
    ]

    display_df = display_df.rename(
        columns={
            "story_priority_rank": (
                "Rank"
            ),
            "global_story_priority_rank": (
                "Global Rank"
            ),
            "title": (
                "Mod"
            ),
            "primary_story_type": (
                "Story Type"
            ),
            "story_priority_score": (
                "Story Score"
            ),
            "global_story_priority_score": (
                "Global Score"
            ),
            "story_reason": (
                "Why Now"
            ),
            "current_downloads_gained": (
                "Downloads Gained"
            ),
            "discovery_score": (
                "Discovery"
            ),
            "audience_score": (
                "Audience"
            ),
            "development_activity_score": (
                "Activity"
            ),
            "cross_signal_count": (
                "Strong Signals"
            ),
            "strongest_momentum_category": (
                "Ecosystem"
            ),
            "strongest_category_momentum_score": (
                "Ecosystem Score"
            ),
        }
    )

    return display_df


st.subheader(
    "Story Queue"
)

st.caption(
    "Highest-priority mod stories based on "
    "Discovery, Audience, Activity, and "
    "Ecosystem Momentum."
)


if submitted_momentum:

    if not story_queue_df.empty:

        story_queue_display_df = (
            build_story_queue_display_df(
                story_queue_df,
                limit=50,
            )
        )

        st.dataframe(
            story_queue_display_df,
            hide_index=True,
            use_container_width=True,
            height=650,
            column_config={
                "Rank": (
                    st.column_config.NumberColumn(
                        "Rank",
                        format="%d",
                    )
                ),
                "Global Rank": (
                    st.column_config.NumberColumn(
                        "Global Rank",
                        format="%d",
                    )
                ),
                "Story Score": (
                    st.column_config.NumberColumn(
                        "Story Score",
                        format="%.1f",
                    )
                ),
                "Global Score": (
                    st.column_config.NumberColumn(
                        "Global Score",
                        format="%.1f",
                    )
                ),
                "Downloads Gained": (
                    st.column_config.NumberColumn(
                        "Downloads Gained",
                        format="%d",
                    )
                ),
                "Discovery": (
                    st.column_config.NumberColumn(
                        "Discovery",
                        format="%.1f",
                    )
                ),
                "Audience": (
                    st.column_config.NumberColumn(
                        "Audience",
                        format="%.1f",
                    )
                ),
                "Activity": (
                    st.column_config.NumberColumn(
                        "Activity",
                        format="%.1f",
                    )
                ),
                "Strong Signals": (
                    st.column_config.NumberColumn(
                        "Strong Signals",
                        format="%d",
                    )
                ),
                "Ecosystem Score": (
                    st.column_config.NumberColumn(
                        "Ecosystem Score",
                        format="%.1f",
                    )
                ),
            },
        )

    else:

        st.info(
            "No story opportunities match "
            "the selected filters."
        )