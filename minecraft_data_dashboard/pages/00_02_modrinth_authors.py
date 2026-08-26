import streamlit as st
import plotly.express as px
from utils.db import run_query, get_modrinth_author_relevance

st.set_page_config(
    page_title="Modrinth",
    layout="wide"
)

st.title("Modrinth Dashboard")
st.write("This page is for Modrinth-specific metrics, tables, and charts.")

@st.cache_data(ttl=30)
def get_modrinth_metrics():
    return run_query("""
                     SELECT COUNT(*) AS mod_count, MAX(date_retrieved_at) AS last_refresh_date 
                     FROM base_api_project_listings
                     WHERE project_type = 'mod' 
                     """)
@st.cache_data(ttl=30)
def get_modrinth_project_listings():
    return run_query("""
                     SELECT * FROM base_api_project_listings
                     """)
@st.cache_data(ttl=30)
def get_modrinth_top_auth_x_download_count():
    return run_query("""
                     SELECT author,
                     SUM(download_count) AS total_downloads
                FROM base_api_project_listings
                WHERE project_type = 'mod'
                GROUP BY author
                ORDER BY total_downloads DESC
                LIMIT 10
                     """)
@st.cache_data(ttl=30)
def load_author_relevance():
    return get_modrinth_author_relevance()

modrinth_metrics = get_modrinth_metrics()
modrinth_project_listings = get_modrinth_project_listings() 
top_authors_x_download_count = get_modrinth_top_auth_x_download_count()
author_relevance = load_author_relevance()

if author_relevance.empty:
    st.warning("No Modrinth author data found.")

col1, col2 = st.columns(2)

col1.metric("Total Mod Count: ", f"{modrinth_metrics.loc[0, 'mod_count']:,}")
col2.metric("Modrinth Pipeline Last Refreshed At: ", f"{modrinth_metrics.loc[0, 'last_refresh_date']}")

st.subheader('Top Authors')
top_10_authors_df = author_relevance.head(10).copy()

col1, col2, col3 = st.columns(3)

col1.metric("authors", f"{len(author_relevance):,}")
col2.metric("top author", top_10_authors_df.iloc[0]["author"])
col3.metric("top relevance score", f"{top_10_authors_df.iloc[0]['relevance_score']:.4f}")

st.subheader("Top 10 Authors by Relevance Score")

bar_fig = px.bar(
    top_10_authors_df.sort_values("relevance_score", ascending=True),
    x="relevance_score",
    y="author",
    orientation="h",
    hover_data=[
        "mod_count",
        "total_downloads",
        "avg_downloads_per_mod",
        "total_follows"
    ]
)

bar_fig.update_layout(
    xaxis_title="Relevance Score",
    yaxis_title="Author"
)

st.plotly_chart(bar_fig, use_container_width=True)

st.subheader("Scale vs Quality")

scatter_fig = px.scatter(
    author_relevance,
    x="mod_count",
    y="avg_downloads_per_mod",
    size="total_downloads",
    hover_name="author",
    hover_data=["relevance_score", "total_follows"],
    log_y=True
)

scatter_fig.update_layout(
    xaxis_title="Mod Count",
    yaxis_title="Average Downloads per Mod"
)

st.plotly_chart(scatter_fig, use_container_width=True)

st.subheader("Author Relevance Table")

st.dataframe(
    author_relevance,
    use_container_width=True,
    hide_index=True,
    column_config={
        "mod_count": st.column_config.NumberColumn("Mod Count", format="%,d"),
        "total_downloads": st.column_config.NumberColumn("Total Downloads", format="%,d"),
        "avg_downloads_per_mod": st.column_config.NumberColumn("Avg Downloads / Mod", format="%,.0f"),
        "total_follows": st.column_config.NumberColumn("Total Follows", format="%,d"),
        "relevance_score": st.column_config.NumberColumn("Relevance Score", format="%.4f"),
    }
)

fig = px.bar(
    top_authors_x_download_count.sort_values("total_downloads", ascending=True),
    x="total_downloads",
    y="author",
    orientation="h",
    title="Top 10 Modrinth Authors by Download Count"
)

fig.update_xaxes(tickformat=",")
fig.update_layout(
    xaxis_title="Total Downloads",
    yaxis_title="Author"
)

st.plotly_chart(fig, width='stretch')

st.subheader("Project Listings")
st.dataframe(
    modrinth_project_listings[['display_title', 'author', 'description', 'download_count', 'client_side', 'server_side', 'date_created', 'date_modified', 'date_retrieved_at']],
    column_config={
        'download_count': st.column_config.NumberColumn(format="%,d")
    },
    width='stretch'
)