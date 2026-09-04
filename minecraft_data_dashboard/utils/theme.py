import os
import base64
import streamlit as st
import plotly.graph_objects as go

def format_compact_number(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,}"

def _get_base64_image(image_path: str) -> str:
    with open(os.path.abspath(image_path), "rb") as image_file:
        return base64.b64encode(image_file.read()).decode()


def apply_modrinth_theme(
    title: str,
    logo_path: str = "minecraft_data_dashboard/assets/modrinth_icon_light.png",
) -> None:
    logo_base64 = _get_base64_image(logo_path)

    st.markdown(
        f"""
        <style>
        :root {{
            --modrinth-green-1: #19e56f;
            --modrinth-green-2: #37ef8d;
            --modrinth-green-3: #7bf5c1;
            --modrinth-bg-1: #060913;
            --modrinth-bg-2: #0a1020;
            --modrinth-bg-3: #10182b;
            --modrinth-text: #f5f7fb;
            --modrinth-muted: #b8c0d4;
        }}

        .stApp {{
            background:
                radial-gradient(circle at 15% 20%, rgba(25, 229, 111, 0.09), transparent 0 22%),
                radial-gradient(circle at 85% 15%, rgba(55, 239, 141, 0.07), transparent 0 18%),
                radial-gradient(circle at 50% 100%, rgba(123, 245, 193, 0.05), transparent 0 25%),
                linear-gradient(135deg, var(--modrinth-bg-1) 0%, var(--modrinth-bg-2) 45%, var(--modrinth-bg-3) 100%);
            color: var(--modrinth-text);
        }}

        [data-testid="stHeader"] {{
            background: transparent;
        }}

        [data-testid="stSidebar"] {{
            background: rgba(8, 12, 24, 0.88);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(8px);
        }}

        .block-container {{
            padding-top: 1.75rem;
            padding-bottom: 2rem;
        }}

        .modrinth-brand-row {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 1.2rem;
        }}

        .modrinth-brand-logo {{
            width: 42px;
            height: 42px;
            object-fit: contain;
            display: block;
        }}

        .modrinth-brand-title {{
            margin: 0;
            color: var(--modrinth-text);
            font-size: 1.95rem;
            font-weight: 800;
            line-height: 1.05;
            letter-spacing: -0.02em;
        }}

        .modrinth-page-title {{
            margin: 0 0 0.2rem 0;
            font-size: 2.2rem;
            font-weight: 850;
            line-height: 1.05;
            letter-spacing: -0.03em;
            background: linear-gradient(
                90deg,
                var(--modrinth-green-1) 0%,
                var(--modrinth-green-2) 50%,
                var(--modrinth-green-3) 100%
            );
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            color: transparent;
        }}

        .modrinth-subtitle {{
            color: var(--modrinth-muted);
            margin-top: 0;
            margin-bottom: 1rem;
            font-size: 1rem;
        }}

        .modrinth-section-header {{
            margin: 1.15rem 0 0.55rem 0;
            font-size: 1.25rem;
            font-weight: 780;
            line-height: 1.15;
            letter-spacing: -0.02em;
            color: #f5f7fb;
        }}

        div[data-testid="stMetric"] {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 0.85rem 1rem;
            backdrop-filter: blur(6px);
        }}

        div[data-testid="stMetricLabel"] p {{
            color: var(--modrinth-muted) !important;
            font-weight: 600;
        }}

        div[data-testid="stMetricValue"] {{
            color: #7bf5c1 !important;
            font-weight: 800;
        }}

        div[data-testid="stDataFrame"] {{
            border-radius: 14px;
            overflow: hidden;
        }}
        </style>

        <div class="modrinth-brand-row">
            <img class="modrinth-brand-logo" src="data:image/png;base64,{logo_base64}">
            <h1 class="modrinth-brand-title">{title}</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )


def brand_page_title(text: str, subtitle: str | None = None) -> None:
    subtitle_html = f'<div class="modrinth-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="modrinth-page-title">{text}</div>
        {subtitle_html}
        """,
        unsafe_allow_html=True,
    )


def brand_subheader(text: str) -> None:
    st.markdown(
        f'<div class="modrinth-section-header">{text}</div>',
        unsafe_allow_html=True,
    )


def style_modrinth_figure(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f5f7fb"),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f5f7fb"),
        ),
        margin=dict(l=20, r=20, t=25, b=20),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            color="#dbe3f0",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.10)",
            zeroline=False,
            color="#dbe3f0",
        ),
    )
    return fig