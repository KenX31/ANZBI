from __future__ import annotations

import streamlit as st

from data_loader import DataLoadError, load_project_data, validate_project
from pages_or_modules.activation_low_activity import render_activation_page
from pages_or_modules.new_intake import render_new_intake_page


st.set_page_config(
    page_title="ANZ BI Portal",
    page_icon="ANZ",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    st.title("ANZ BI Portal")
    st.caption("New Intake and Activation Low-Activity BI")

    try:
        project = load_project_data()
        validate_project(project)
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()

    manifest = project["manifest"]
    st.sidebar.header("BI Navigation")
    page = st.sidebar.radio(
        "Page",
        ("New Intake", "Activation Low-Activity"),
        label_visibility="collapsed",
    )
    st.sidebar.caption(
        f"Data version {manifest.get('version', '-')}; generated {manifest.get('generated_at', '-')}"
    )

    if page == "New Intake":
        render_new_intake_page(project["new_intake"])
    else:
        render_activation_page(project["activation_low_activity"])


if __name__ == "__main__":
    main()

