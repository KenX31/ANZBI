from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st


PROJECT_ID = "anz-bi-platform"
DEFAULT_LOCAL_PROJECT_ROOT = Path(r"D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform")
EXPECTED_SCHEMA = {
    "new_intake": "1.0",
    "activation_low_activity": "1.0",
}


class DataLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataSource:
    backend: str
    local_root: Path | None = None
    github_repo: str = "KenX31/anzdata"
    github_ref: str = "main"
    github_project: str = PROJECT_ID
    github_token: str = ""


def _secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        value = None
    return str(value or os.getenv(name, default))


def resolve_data_source() -> DataSource:
    backend = _secret_or_env("DATA_BACKEND", "local")
    local_root = _secret_or_env("LOCAL_DATA_ROOT", "")
    resolved_local_root = Path(local_root).expanduser() if local_root else None
    if backend == "local" and resolved_local_root is None and DEFAULT_LOCAL_PROJECT_ROOT.exists():
        resolved_local_root = DEFAULT_LOCAL_PROJECT_ROOT
    return DataSource(
        backend=backend,
        local_root=resolved_local_root,
        github_repo=_secret_or_env("DATA_GITHUB_REPO", "KenX31/anzdata"),
        github_ref=_secret_or_env("DATA_GITHUB_REF", "main"),
        github_project=_secret_or_env("DATA_PROJECT", PROJECT_ID),
        github_token=_secret_or_env("DATA_GITHUB_TOKEN", ""),
    )


@st.cache_data(show_spinner=False)
def load_project_data() -> dict[str, Any]:
    source = resolve_data_source()
    manifest = _load_json(source, "manifest.json")
    return {
        "manifest": manifest,
        "new_intake": {
            "rows": _load_frame(source, "processed/new_intake/new_intake_rows.csv"),
            "summary": _load_json(source, "processed/new_intake/new_intake_summary.json"),
            "institution_rollup": _load_frame(source, "processed/new_intake/new_intake_institution_rollup.csv"),
            "export_rows": _load_frame(source, "processed/new_intake/new_intake_export.csv"),
            "provider_export_rows": _load_frame_optional(source, "processed/new_intake/new_intake_provider_export.csv"),
            "internal_export_rows": _load_frame_optional(source, "processed/new_intake/new_intake_internal_record_export.csv"),
        },
        "activation_low_activity": {
            "rows": _load_frame(source, "processed/activation_low_activity/activation_candidates.csv"),
            "summary": _load_json(source, "processed/activation_low_activity/low_activity_bi_summary.json"),
            "area_rollup": _load_frame(source, "processed/activation_low_activity/area_low_activity_rollup.csv"),
            "export_rows": _load_frame(source, "processed/activation_low_activity/activation_export.csv"),
            "provider_export_rows": _load_frame_optional(source, "processed/activation_low_activity/activation_provider_export.csv"),
            "internal_export_rows": _load_frame_optional(source, "processed/activation_low_activity/activation_internal_record_export.csv"),
        },
    }


def validate_project(project: dict[str, Any]) -> None:
    manifest = project.get("manifest") or {}
    if manifest.get("project_id") != PROJECT_ID:
        raise DataLoadError(
            f"Loaded data project is {manifest.get('project_id')!r}; expected {PROJECT_ID!r}."
        )

    page_datasets = manifest.get("page_datasets") or {}
    for page, expected in EXPECTED_SCHEMA.items():
        actual = str((page_datasets.get(page) or {}).get("schema_version") or "")
        if actual != expected:
            raise DataLoadError(
                f"{page} schema version is {actual or 'missing'}; expected {expected}. "
                "Please refresh the private data package before rendering this app."
            )


def _load_json(source: DataSource, relative_path: str) -> dict[str, Any]:
    text = _read_text(source, relative_path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"Invalid JSON in {relative_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataLoadError(f"{relative_path} must contain a JSON object.")
    return payload


def _load_frame(source: DataSource, relative_path: str) -> pd.DataFrame:
    if source.backend == "local":
        path = _local_path(source, relative_path)
        if not path.exists():
            raise DataLoadError(f"Missing local data file: {path}")
        return pd.read_csv(path)
    text = _read_text(source, relative_path)
    from io import StringIO

    return pd.read_csv(StringIO(text))


def _load_frame_optional(source: DataSource, relative_path: str) -> pd.DataFrame:
    try:
        return _load_frame(source, relative_path)
    except DataLoadError:
        return pd.DataFrame()


def _read_text(source: DataSource, relative_path: str) -> str:
    if source.backend == "local":
        path = _local_path(source, relative_path)
        if not path.exists():
            raise DataLoadError(f"Missing local data file: {path}")
        return path.read_text(encoding="utf-8-sig")
    if source.backend == "github_private":
        return _read_github_text(source, relative_path)
    raise DataLoadError(f"Unsupported DATA_BACKEND: {source.backend}")


def _local_path(source: DataSource, relative_path: str) -> Path:
    root = source.local_root
    if root is None:
        raise DataLoadError(
            "LOCAL_DATA_ROOT is required when DATA_BACKEND=local. "
            f"Expected local project root like {DEFAULT_LOCAL_PROJECT_ROOT}."
        )
    return root / relative_path


def _read_github_text(source: DataSource, relative_path: str) -> str:
    url = (
        f"https://raw.githubusercontent.com/{source.github_repo}/"
        f"{source.github_ref}/projects/{source.github_project}/{relative_path}"
    )
    headers = {"Accept": "application/vnd.github.raw"}
    if source.github_token:
        headers["Authorization"] = f"Bearer {source.github_token}"
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 404:
        raise DataLoadError(f"Private data file not found on GitHub: {relative_path}")
    if response.status_code >= 400:
        raise DataLoadError(f"GitHub data request failed for {relative_path}: HTTP {response.status_code}")
    return response.text
