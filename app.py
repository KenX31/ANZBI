from __future__ import annotations

import streamlit as st

from auth import AuthConfigError, require_login
from data_loader import DataLoadError, load_project_data, validate_project
from pages_or_modules.activation_low_activity import render_activation_page
from pages_or_modules.new_intake import render_new_intake_page
from pages_or_modules.rate_coupon_activity import render_rate_coupon_activity_page
from pages_or_modules.silent_merchants import render_silent_merchants_page
from ui_labels import PAGE_LABELS


st.set_page_config(
    page_title="ANZ BI 门户",
    page_icon="ANZ",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    _apply_brand_theme()
    st.title("ANZ BI 门户")
    st.caption("新进件与活跃监测 BI")

    try:
        require_login()
    except AuthConfigError as exc:
        st.error(str(exc))
        st.stop()

    try:
        project = load_project_data()
        validate_project(project)
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()

    manifest = project["manifest"]
    st.sidebar.header("BI 导航")
    page_key = st.sidebar.radio(
        "页面",
        tuple(PAGE_LABELS.keys()),
        format_func=lambda value: PAGE_LABELS.get(str(value), str(value)),
        label_visibility="collapsed",
    )
    st.sidebar.caption(
        f"数据版本 {manifest.get('version', '-')}；生成时间 {manifest.get('generated_at', '-')}"
    )

    if page_key == "new_intake":
        render_new_intake_page(project["new_intake"])
    elif page_key == "activation_low_activity":
        render_activation_page(project["activation_low_activity"])
    elif page_key == "rate_coupon_activity":
        render_rate_coupon_activity_page(project["rate_coupon_activity"])
    elif page_key == "silent_merchants":
        render_silent_merchants_page(project["silent_merchants"])
    else:
        st.error(f"Unsupported page key: {page_key}")


def _apply_brand_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
          --forest: #001e2b;
          --green: #00ed64;
          --dark-green: #00684a;
          --blue: #006cfa;
          --teal-active: #1eaedb;
          --deep-teal: #1c2d38;
          --teal-gray: #3d4f58;
          --cool-gray: #5c6c75;
          --silver: #b8c4c2;
          --input: #e8edeb;
          --white: #ffffff;
        }

        html, body, [data-testid="stAppViewContainer"] {
          background: var(--white);
          color: var(--forest);
          font-family: "Euclid Circular A", "Noto Sans SC", Arial, system-ui, sans-serif;
        }

        [data-testid="stAppViewContainer"] > .main {
          background: linear-gradient(180deg, rgba(232, 237, 235, 0.38) 0, #ffffff 220px);
        }

        .block-container {
          max-width: 1440px;
          padding-top: 2.2rem;
          padding-bottom: 3rem;
        }

        h1 {
          color: var(--forest) !important;
          font-weight: 700 !important;
          letter-spacing: 0 !important;
        }

        h2, h3 {
          color: var(--forest) !important;
          letter-spacing: 0 !important;
        }

        [data-testid="stCaptionContainer"] {
          color: var(--cool-gray);
        }

        [data-testid="stSidebar"] {
          background: var(--forest);
          border-right: 1px solid var(--teal-gray);
        }

        [data-testid="stSidebar"] * {
          color: var(--input);
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] .stMarkdown {
          color: var(--white) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] [data-baseweb="textarea"] > div {
          background: var(--deep-teal);
          border-color: var(--teal-gray);
          border-radius: 8px;
        }

        [data-testid="stSidebar"] [role="radiogroup"] label {
          background: rgba(232, 237, 235, 0.06);
          border: 1px solid var(--teal-gray);
          border-radius: 999px;
          margin-bottom: 8px;
          padding: 6px 10px;
        }

        [data-testid="stMetric"] {
          background: var(--white);
          border: 1px solid var(--silver);
          border-radius: 16px;
          padding: 16px 18px;
          box-shadow: rgba(0, 30, 43, 0.08) 0px 16px 28px;
        }

        [data-testid="stMetricLabel"] {
          color: var(--cool-gray);
          font-size: 0.82rem;
          font-weight: 600;
        }

        [data-testid="stMetricValue"] {
          color: var(--forest);
          font-weight: 700;
        }

        div[data-testid="stDownloadButton"] button,
        div[data-testid="stButton"] button {
          border-radius: 999px;
          border: 1px solid var(--dark-green);
          background: var(--dark-green);
          color: var(--white);
          font-weight: 700;
          box-shadow: rgba(0, 0, 0, 0.06) 0px 1px 6px;
        }

        div[data-testid="stDownloadButton"] button:hover,
        div[data-testid="stButton"] button:hover {
          border-color: var(--green);
          background: var(--forest);
          color: var(--green);
        }

        .stTabs [data-baseweb="tab-list"] {
          gap: 8px;
          border-bottom: 1px solid var(--silver);
        }

        .stTabs [data-baseweb="tab"] {
          border-radius: 999px 999px 0 0;
          color: var(--cool-gray);
          font-weight: 600;
        }

        .stTabs [aria-selected="true"] {
          color: var(--forest) !important;
          border-bottom: 3px solid var(--green);
        }

        [data-testid="stDataFrame"] {
          border: 1px solid var(--silver);
          border-radius: 16px;
          overflow: hidden;
          box-shadow: rgba(0, 30, 43, 0.06) 0px 10px 24px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
