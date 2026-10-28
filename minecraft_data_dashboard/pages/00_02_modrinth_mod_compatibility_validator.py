import asyncio
from datetime import datetime
import httpx
import json
import zipfile
import pandas as pd
import streamlit as st

from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from utils.theme import (
    apply_modrinth_theme,
    brand_subheader,
)

from utils.db import (
    get_first_activity,
    get_project_versions,
    get_project_version_by_id,
    get_project_listings,
    get_distinct_gameplay_categories,
    get_distinct_mod_loaders,
    get_distinct_mod_release_versions,
    get_modrinth_kpis,
)

from shared_code.api.modrinth_rate_limiter import ModrinthRateLimiter


st.set_page_config(
    page_icon="assets/modrinth_icon_light.png",
    layout="wide",
)

st.markdown(
    """
    <style>
    .st-key-clear_mod_list_button button {
        background-color: #7f1d1d;
        color: white;
        border-color: #ef4444;
    }

    .st-key-clear_mod_list_button button:hover {
        background-color: #991b1b;
        color: white;
        border-color: #f87171;
    }

    .st-key-confirm_clear_mod_list_button button {
        background-color: #7f1d1d;
        color: white;
        border-color: #ef4444;
    }

    .st-key-confirm_clear_mod_list_button button:hover {
        background-color: #991b1b;
        color: white;
        border-color: #f87171;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# DATA LOADERS
# ---------------------------------------------------------

@st.cache_data(ttl=30)
def load_project_versions(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False,
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
def load_project_listings(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False,
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
def load_gameplay_categories():
    return get_distinct_gameplay_categories(project_type="mod")


@st.cache_data(ttl=30)
def load_platform_loaders():
    return get_distinct_mod_loaders()


@st.cache_data(ttl=30)
def load_versions():
    return get_distinct_mod_release_versions()


@st.cache_data(ttl=30)
def load_kpis():
    return get_modrinth_kpis(project_type="mod")


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def build_search_results_df(
    project_versions_df: pd.DataFrame,
    project_listings_df: pd.DataFrame,
) -> pd.DataFrame:

    if project_versions_df.empty:
        return pd.DataFrame()

    listing_context_df = project_listings_df[
        [
            "project_id",
            "slug",
            "description",
            "server_side",
            "client_side",
            "environment",
        ]
    ].rename(
        columns={
            "description": "project_description",
            "environment": "project_environment",
        }
    )

    results_df = project_versions_df.merge(
        listing_context_df,
        on="project_id",
        how="left",
    )

    results_df["manual_download_url"] = (
        "https://modrinth.com/"
        + results_df["project_type"].astype(str)
        + "/"
        + results_df["slug"].astype(str).str.lstrip("-")
        + "/version/"
        + results_df["version_number"].astype(str).str.strip('"')
    )
    
    results_df["api_download_url"] = (
        results_df["files"]
        .apply(get_api_download_url)
    )

    search_result_columns = [
        "project_id",
        "version_id",
        "project_title",
        "project_author",
        "project_description",
        "game_versions",
        "name",
        "version_number",
        "loaders",
        "server_side",
        "client_side",
        "project_environment",
        "date_published",
        "manual_download_url",
        "api_download_url",
        "dependencies"
    ]

    return (
        results_df[search_result_columns]
        .rename(
            columns={
                "project_title": "title",
                "project_author": "author",
                "project_description": "description",
                "project_environment": "environment",
                "name": "mod_file_name",
            }
        )
        .sort_values(
            ["title", "date_published"],
            ascending=[True, False],
        )
        .reset_index(drop=True)
    )


def parse_dependencies(value) -> list[dict]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    if isinstance(value, str):
        if not value.strip():
            return []

        try:
            parsed_value = json.loads(value)

            if isinstance(parsed_value, list):
                return parsed_value

            if isinstance(parsed_value, dict):
                return [parsed_value]

        except json.JSONDecodeError:
            return []

    return []


def normalize_multi_value(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        stripped_value = value.strip()

        if not stripped_value:
            return []

        try:
            parsed_value = json.loads(stripped_value)
        except json.JSONDecodeError:
            return [stripped_value]

        if isinstance(parsed_value, str):
            return [parsed_value]

        value = parsed_value

    if hasattr(value, "tolist"):
        value = value.tolist()

    if isinstance(value, (list, tuple, set)):
        return [
            str(item)
            for item in value
            if item is not None
            and str(item).strip()
        ]

    return []


def assess_mod_compatibility(
    mod_list_df: pd.DataFrame,
    selected_platform_loaders: list[str],
    selected_versions: list[str],
) -> pd.DataFrame:
    report_rows = []

    selected_project_ids = set(
        mod_list_df["project_id"].dropna()
    )
    selected_version_ids = set(
        mod_list_df["version_id"].dropna()
    )

    target_loaders = normalize_multi_value(
        selected_platform_loaders
    )
    target_versions = normalize_multi_value(
        selected_versions
    )

    target_loader = (
        target_loaders[0]
        if len(target_loaders) == 1
        else None
    )
    target_version = (
        target_versions[0]
        if len(target_versions) == 1
        else None
    )

    duplicate_projects_df = (
        mod_list_df
        .groupby(
            ["project_id", "title"],
            dropna=False,
        )
        .size()
        .reset_index(
            name="selected_version_count"
        )
    )

    duplicate_projects_df = duplicate_projects_df[
        duplicate_projects_df[
            "selected_version_count"
        ] > 1
    ]

    for _, row in duplicate_projects_df.iterrows():
        report_rows.append({
            "level": "ERROR",
            "mod": row["title"],
            "issue": "Multiple versions selected",
            "details": (
                f"{int(row['selected_version_count'])} versions of this mod are in the list. "
                "A modpack should normally contain only one version of a mod."
            ),
        })

    # ---------------------------------------------------------
    # VALIDATE SELECTED PLATFORM LOADER
    # ---------------------------------------------------------

    if target_loader is None:
        report_rows.append({
            "level": "ERROR",
            "mod": "Mod List",
            "issue": "Platform loader not selected",
            "details": (
                "Choose one platform loader for the compatibility list "
                "before assessing compatibility."
            ),
        })

    else:
        incompatible_loader_df = mod_list_df[
            ~mod_list_df["loaders"].apply(
                lambda loaders: (
                    target_loader
                    in normalize_multi_value(loaders)
                )
            )
        ]

        if incompatible_loader_df.empty:
            report_rows.append({
                "level": "INFO",
                "mod": "Mod List",
                "issue": "Selected mod loader",
                "details": target_loader,
            })

        else:
            incompatible_titles = (
                incompatible_loader_df["title"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            report_rows.append({
                "level": "ERROR",
                "mod": "Mod List",
                "issue": "Selected mod loader conflict",
                "details": (
                    f"The following file(s) do not support {target_loader}: "
                    + ", ".join(incompatible_titles)
                ),
            })

    # ---------------------------------------------------------
    # VALIDATE SELECTED MINECRAFT VERSION
    # ---------------------------------------------------------

    if target_version is None:
        report_rows.append({
            "level": "ERROR",
            "mod": "Mod List",
            "issue": "Minecraft version not selected",
            "details": (
                "Choose one Minecraft version for the compatibility list "
                "before assessing compatibility."
            ),
        })

    else:
        incompatible_version_df = mod_list_df[
            ~mod_list_df["game_versions"].apply(
                lambda game_versions: (
                    target_version
                    in normalize_multi_value(
                        game_versions
                    )
                )
            )
        ]

        if incompatible_version_df.empty:
            report_rows.append({
                "level": "INFO",
                "mod": "Mod List",
                "issue": "Selected Minecraft version",
                "details": target_version,
            })

        else:
            incompatible_titles = (
                incompatible_version_df["title"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            report_rows.append({
                "level": "ERROR",
                "mod": "Mod List",
                "issue": "Selected Minecraft version conflict",
                "details": (
                    f"The following file(s) do not support Minecraft {target_version}: "
                    + ", ".join(incompatible_titles)
                ),
            })

    compatibility_loaders = (
        [target_loader]
        if target_loader
        else []
    )
    compatibility_versions = (
        [target_version]
        if target_version
        else []
    )

    latest_mod_versions_df = (
        mod_list_df
        .sort_values(
            "date_published",
            ascending=False,
        )
        .drop_duplicates(
            subset=["project_id"],
            keep="first",
        )
    )

    missing_dependencies_by_mod = {}
    reported_incompatible_dependencies = set()

    if "dependencies" in latest_mod_versions_df.columns:
        for _, row in latest_mod_versions_df.iterrows():
            mod_title = row["title"]
            mod_project_id = row["project_id"]
            dependencies = parse_dependencies(
                row["dependencies"]
            )

            for dependency in dependencies:
                dependency_type = dependency.get(
                    "dependency_type"
                )
                dependency_project_id = dependency.get(
                    "project_id"
                )
                dependency_version_id = dependency.get(
                    "version_id"
                )

                resolved_dependency_project_id = (
                    resolve_dependency_project_id(
                        dependency_project_id=(
                            dependency_project_id
                        ),
                        dependency_version_id=(
                            dependency_version_id
                        ),
                    )
                )

                if resolved_dependency_project_id:
                    dependency_project_id = (
                        resolved_dependency_project_id
                    )

                if dependency_project_id:
                    dependency_present = (
                        dependency_project_id
                        in selected_project_ids
                    )

                elif dependency_version_id:
                    dependency_present = (
                        dependency_version_id
                        in selected_version_ids
                    )

                else:
                    dependency_present = False

                if (
                    dependency_type == "required"
                    and not dependency_present
                ):
                    dependency_resolution = (
                        resolve_dependency(
                            dependency_project_id=(
                                dependency_project_id
                            ),
                            dependency_version_id=(
                                dependency_version_id
                            ),
                            selected_platform_loaders=(
                                compatibility_loaders
                            ),
                            selected_versions=(
                                compatibility_versions
                            ),
                        )
                    )

                    mod_key = (
                        mod_project_id,
                        mod_title,
                    )

                    dependency_key = (
                        dependency_project_id,
                        dependency_version_id,
                    )

                    if (
                        mod_key
                        not in missing_dependencies_by_mod
                    ):
                        missing_dependencies_by_mod[
                            mod_key
                        ] = {}

                    if (
                        dependency_resolution["status"]
                        == "READY_TO_ADD"
                    ):
                        dependency_details = (
                            f"{dependency_resolution['project_title']} | "
                            f"File: {dependency_resolution['file_name']} | "
                            f"Project ID: {dependency_resolution['project_id']} | "
                            f"Version ID: {dependency_resolution['version_id']} | "
                            "Status: Ready to add"
                        )

                    else:
                        dependency_details = (
                            f"{dependency_resolution['project_title']} | "
                            f"Project ID: {dependency_resolution['project_id']} | "
                            f"Status: {dependency_resolution['reason']}"
                        )

                    missing_dependencies_by_mod[
                        mod_key
                    ][dependency_key] = (
                        dependency_details
                    )

                if (
                    dependency_type == "incompatible"
                    and dependency_present
                ):
                    dependency_key = (
                        mod_project_id,
                        dependency_project_id,
                        dependency_version_id,
                    )

                    if (
                        dependency_key
                        not in reported_incompatible_dependencies
                    ):
                        if dependency_version_id:
                            conflicting_mod_df = (
                                mod_list_df[
                                    mod_list_df[
                                        "version_id"
                                    ] == dependency_version_id
                                ]
                            )
                        else:
                            conflicting_mod_df = (
                                mod_list_df[
                                    mod_list_df[
                                        "project_id"
                                    ] == dependency_project_id
                                ]
                            )

                        if not conflicting_mod_df.empty:
                            conflicting_row = (
                                conflicting_mod_df.iloc[0]
                            )

                            conflict_details = (
                                f"{conflicting_row['title']} | "
                                f"File: {conflicting_row['mod_file_name']} | "
                                f"Project ID: {conflicting_row['project_id']} | "
                                f"Version ID: {conflicting_row['version_id']}"
                            )
                        else:
                            conflict_details = (
                                f"Project ID: {dependency_project_id} | "
                                f"Version ID: {dependency_version_id}"
                            )

                        report_rows.append({
                            "level": "ERROR",
                            "mod": mod_title,
                            "issue": (
                                "Declared incompatible mod detected"
                            ),
                            "details": conflict_details,
                        })

                        reported_incompatible_dependencies.add(
                            dependency_key
                        )

    for (
        _,
        mod_title,
    ), dependencies in missing_dependencies_by_mod.items():
        dependency_count = len(dependencies)

        dependency_details = (
            "Required dependency:\n"
            if dependency_count == 1
            else "Required dependencies:\n"
        )

        for dependency_number, dependency in enumerate(
            dependencies.values(),
            start=1,
        ):
            dependency_details += (
                f"\n{dependency_number}. {dependency}"
            )

        report_rows.append({
            "level": "ERROR",
            "mod": mod_title,
            "issue": (
                "Missing required dependency"
                if dependency_count == 1
                else "Missing required dependencies"
            ),
            "details": dependency_details,
        })

    has_errors = any(
        row["level"] == "ERROR"
        for row in report_rows
    )

    if not has_errors:
        report_rows.append({
            "level": "INFO",
            "mod": "Mod List",
            "issue": "No metadata conflicts detected",
            "details": (
                f"All selected files support {target_loader} + Minecraft {target_version}, "
                "and no required dependency issues were detected. "
                "Runtime compatibility is not guaranteed."
            ),
        })

    return pd.DataFrame(report_rows)

def prepare_excel_df(dataframe: pd.DataFrame) -> pd.DataFrame:
    excel_df = dataframe.copy()

    def prepare_excel_value(value):
        if isinstance(value, pd.Timestamp):
            if value.tzinfo is not None:
                return value.tz_convert("America/New_York").tz_localize(None)
            return value

        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return (
                    pd.Timestamp(value)
                    .tz_convert("America/New_York")
                    .tz_localize(None)
                    .to_pydatetime()
                )
            return value

        if isinstance(value, (list, dict)):
            return json.dumps(value)

        if isinstance(value, tuple):
            return json.dumps(list(value))

        return value

    for column in excel_df.columns:
        if isinstance(excel_df[column].dtype, pd.DatetimeTZDtype):
            excel_df[column] = (
                excel_df[column]
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )
        else:
            excel_df[column] = excel_df[column].map(prepare_excel_value)

    return excel_df

def add_to_loaded_session(state_key: str, new_df: pd.DataFrame, unique_column: str):
    if new_df.empty:
        return

    existing_df = st.session_state.get(state_key, pd.DataFrame())

    st.session_state[state_key] = (
        pd.concat(
            [existing_df, new_df],
            ignore_index=True,
        )
        .drop_duplicates(subset=[unique_column])
        .reset_index(drop=True)
    )

def value_matches_filter(value, selected_values):
    if not selected_values:
        return True

    values = normalize_multi_value(value)

    if not values:
        return False

    return any(
        selected_value in values
        for selected_value in selected_values
    )


def resolve_dependency_project_id(
    dependency_project_id: str | None,
    dependency_version_id: str | None,
) -> str | None:

    if dependency_project_id:
        return dependency_project_id

    if not dependency_version_id:
        return None

    loaded_versions_df = st.session_state.get(
        "loaded_project_versions_df",
        pd.DataFrame(),
    )

    if not loaded_versions_df.empty:
        version_match_df = loaded_versions_df[
            loaded_versions_df["version_id"]
            == dependency_version_id
        ]

        if not version_match_df.empty:
            return version_match_df.iloc[0]["project_id"]

    version_match_df = get_project_version_by_id(
        version_id=dependency_version_id,
        project_type="mod",
    )

    if version_match_df.empty:
        return None

    add_to_loaded_session(
        "loaded_project_versions_df",
        version_match_df,
        "version_id",
    )

    return version_match_df.iloc[0]["project_id"]


def resolve_dependency(
    dependency_project_id: str | None,
    dependency_version_id: str | None,
    selected_platform_loaders: list[str],
    selected_versions: list[str],
):

    loaded_versions_df = st.session_state.get(
        "loaded_project_versions_df",
        pd.DataFrame(),
    )

    loaded_listings_df = st.session_state.get(
        "loaded_project_listings_df",
        pd.DataFrame(),
    )

    # ---------------------------------------------------------
    # RESOLVE PROJECT ID
    # ---------------------------------------------------------

    resolved_project_id = resolve_dependency_project_id(
        dependency_project_id=dependency_project_id,
        dependency_version_id=dependency_version_id,
    )

    if resolved_project_id is None:
        return {
            "status": "NO_COMPATIBLE_VERSION",
            "project_title": (
                f"Dependency version {dependency_version_id}"
                if dependency_version_id
                else "Unresolved dependency"
            ),
            "file_name": None,
            "project_id": None,
            "version_id": dependency_version_id,
            "candidate_row": None,
            "reason": (
                "Dependency project could not be resolved "
                "from the available Modrinth version data."
            ),
        }

    # ---------------------------------------------------------
    # RESOLVE PROJECT METADATA BEFORE VALIDATING SCOPE
    # ---------------------------------------------------------

    project_title = None

    matching_listings_df = (
        loaded_listings_df[
            loaded_listings_df["project_id"]
            == resolved_project_id
        ].copy()
        if not loaded_listings_df.empty
        else pd.DataFrame()
    )

    if matching_listings_df.empty:
        dependency_listings_df = load_project_listings(
            project_type="mod",
            selected_gameplay_categories=None,
            selected_platform_loaders=None,
            selected_versions=None,
            selected_project_id=resolved_project_id,
            selected_author_id=None,
            selected_search=True,
        )

        if not dependency_listings_df.empty:
            add_to_loaded_session(
                "loaded_project_listings_df",
                dependency_listings_df,
                "project_id",
            )

            matching_listings_df = dependency_listings_df

    if not matching_listings_df.empty:
        project_title = matching_listings_df.iloc[0]["title"]

    # The version lookup may already know the project title even if
    # listing metadata is unavailable. Use it as a secondary source.
    if project_title is None:
        loaded_versions_df = st.session_state.get(
            "loaded_project_versions_df",
            loaded_versions_df,
        )

        if not loaded_versions_df.empty:
            project_versions_df = loaded_versions_df[
                loaded_versions_df["project_id"]
                == resolved_project_id
            ]

            if (
                not project_versions_df.empty
                and "project_title" in project_versions_df.columns
            ):
                project_titles = (
                    project_versions_df["project_title"]
                    .dropna()
                    .astype(str)
                )

                if not project_titles.empty:
                    project_title = project_titles.iloc[0]

    if project_title is None:
        project_title = f"Project {resolved_project_id}"

    # ---------------------------------------------------------
    # VALIDATE COMPATIBILITY SCOPE
    # ---------------------------------------------------------

    if not selected_platform_loaders or not selected_versions:
        return {
            "status": "NO_COMPATIBLE_VERSION",
            "project_title": project_title,
            "file_name": None,
            "project_id": resolved_project_id,
            "version_id": dependency_version_id,
            "candidate_row": None,
            "reason": (
                "Dependency compatibility scope is incomplete. "
                "A common platform loader and Minecraft version "
                "are required."
            ),
        }

    # ---------------------------------------------------------
    # QUERY ALL COMPATIBLE VERSIONS FOR DEPENDENCY PROJECT
    # ---------------------------------------------------------

    dependency_versions_df = load_project_versions(
        project_type="mod",
        selected_gameplay_categories=None,
        selected_platform_loaders=selected_platform_loaders,
        selected_versions=selected_versions,
        selected_project_id=resolved_project_id,
        selected_author_id=None,
        selected_search=True,
    )

    dependency_versions_df = filter_versions_to_scope(
        dependency_versions_df,
        selected_platform_loaders,
        selected_versions,
    )

    # ---------------------------------------------------------
    # NO COMPATIBLE VERSION
    # ---------------------------------------------------------

    if dependency_versions_df.empty:
        filter_parts = []

        if selected_versions:
            filter_parts.append(
                f"Minecraft {', '.join(selected_versions)}"
            )

        if selected_platform_loaders:
            filter_parts.append(
                f"loader {', '.join(selected_platform_loaders)}"
            )

        filter_description = " + ".join(filter_parts)

        return {
            "status": "NO_COMPATIBLE_VERSION",
            "project_title": project_title,
            "file_name": None,
            "project_id": resolved_project_id,
            "version_id": dependency_version_id,
            "candidate_row": None,
            "reason": (
                f"No version matches {filter_description}."
            ),
        }

    # ---------------------------------------------------------
    # STORE COMPATIBLE VERSIONS IN SESSION
    # ---------------------------------------------------------

    add_to_loaded_session(
        "loaded_project_versions_df",
        dependency_versions_df,
        "version_id",
    )

    # ---------------------------------------------------------
    # SELECT NEWEST COMPATIBLE VERSION
    # ---------------------------------------------------------

    dependency_row = (
        dependency_versions_df
        .sort_values(
            "date_published",
            ascending=False,
        )
        .iloc[0]
    )

    if (
        project_title.startswith("Project ")
        and "project_title" in dependency_row.index
        and pd.notna(dependency_row["project_title"])
    ):
        project_title = dependency_row["project_title"]

    return {
        "status": "READY_TO_ADD",
        "project_title": project_title,
        "file_name": dependency_row["name"],
        "project_id": dependency_row["project_id"],
        "version_id": dependency_row["version_id"],
        "candidate_row": dependency_row,
        "reason": (
            "Newest compatible dependency version found."
        ),
    }

def get_duplicate_projects(mod_list_df: pd.DataFrame) -> list[str]:
    project_counts = (
        mod_list_df
        .groupby("project_id")
        .size()
    )

    return project_counts[
        project_counts > 1
    ].index.tolist()


def apply_duplicate_version_choices(
    mod_list_df: pd.DataFrame,
    version_choices: dict,
) -> pd.DataFrame:
    rows_to_keep = []

    for project_id, project_df in mod_list_df.groupby("project_id"):
        if project_id in version_choices:
            project_df = project_df[
                project_df["version_id"] == version_choices[project_id]
            ]

        rows_to_keep.append(
            project_df
        )

    return (
        pd.concat(
            rows_to_keep,
            ignore_index=True,
        )
        .reset_index(drop=True)
    )

def add_required_dependencies(
    mod_list_df: pd.DataFrame,
    selected_platform_loaders: list[str],
    selected_versions: list[str],
):

    updated_mod_list_df = mod_list_df.copy()

    # ---------------------------------------------------------
    # DETERMINE COMPATIBILITY SCOPE
    # ---------------------------------------------------------

    selected_platform_loaders, selected_versions = (
        get_mod_list_compatibility_scope(
            mod_list_df,
            selected_platform_loaders,
            selected_versions,
        )
    )
    
    if not selected_platform_loaders or not selected_versions:
        return (
            updated_mod_list_df,
            [],
            [
                {
                    "required_by": "Mod List",
                    "project_title": "Compatibility Scope",
                    "project_id": None,
                    "version_id": None,
                    "reason": (
                        "Dependencies cannot be resolved because "
                        "the current mod list does not share a "
                        "platform loader and Minecraft version "
                        "within the selected compatibility scope."
                    ),
                }
            ],
        )

    # ---------------------------------------------------------
    # START WITH ONE VERSION PER PROJECT
    # ---------------------------------------------------------

    starting_versions_df = (
        updated_mod_list_df
        .sort_values(
            "date_published",
            ascending=False,
        )
        .drop_duplicates(
            subset=["project_id"],
            keep="first",
        )
    )

    dependency_queue = [
        row
        for _, row in starting_versions_df.iterrows()
    ]

    processed_version_ids = set()
    added_dependencies = []
    unresolved_dependencies = []

    # ---------------------------------------------------------
    # PROCESS DEPENDENCIES RECURSIVELY
    # ---------------------------------------------------------

    while dependency_queue:

        current_mod = dependency_queue.pop(0)
        current_version_id = current_mod["version_id"]

        if current_version_id in processed_version_ids:
            continue

        processed_version_ids.add(
            current_version_id
        )

        dependencies = parse_dependencies(
            current_mod["dependencies"]
        )

        for dependency in dependencies:

            if dependency.get("dependency_type") != "required":
                continue

            dependency_project_id = dependency.get(
                "project_id"
            )

            dependency_version_id = dependency.get(
                "version_id"
            )

            resolved_dependency_project_id = (
                resolve_dependency_project_id(
                    dependency_project_id=dependency_project_id,
                    dependency_version_id=dependency_version_id,
                )
            )

            if resolved_dependency_project_id:
                dependency_project_id = (
                    resolved_dependency_project_id
                )

            current_project_ids = set(
                updated_mod_list_df[
                    "project_id"
                ].dropna()
            )

            current_version_ids = set(
                updated_mod_list_df[
                    "version_id"
                ].dropna()
            )

            # -------------------------------------------------
            # CHECK WHETHER DEPENDENCY PROJECT IS ALREADY THERE
            # -------------------------------------------------

            if dependency_project_id:

                dependency_present = (
                    dependency_project_id
                    in current_project_ids
                )

            elif dependency_version_id:

                dependency_present = (
                    dependency_version_id
                    in current_version_ids
                )

            else:

                dependency_present = False

            if dependency_present:
                continue

            # -------------------------------------------------
            # RESOLVE NEWEST VERSION MATCHING CURRENT SCOPE
            # -------------------------------------------------

            dependency_resolution = resolve_dependency(
                dependency_project_id=dependency_project_id,
                dependency_version_id=dependency_version_id,
                selected_platform_loaders=selected_platform_loaders,
                selected_versions=selected_versions,
            )

            if (
                dependency_resolution["status"]
                != "READY_TO_ADD"
            ):

                unresolved_dependencies.append({
                    "required_by": current_mod["title"],
                    "project_title": dependency_resolution[
                        "project_title"
                    ],
                    "project_id": dependency_resolution[
                        "project_id"
                    ],
                    "version_id": dependency_resolution[
                        "version_id"
                    ],
                    "reason": dependency_resolution[
                        "reason"
                    ],
                })

                continue

            dependency_row = (
                dependency_resolution[
                    "candidate_row"
                ]
            )

            # -------------------------------------------------
            # GET PROJECT LISTING METADATA
            # -------------------------------------------------

            loaded_listings_df = (
                st.session_state.get(
                    "loaded_project_listings_df",
                    pd.DataFrame(),
                )
            )

            dependency_listing_df = (
                loaded_listings_df[
                    loaded_listings_df["project_id"]
                    == dependency_row["project_id"]
                ]
                .copy()
            )

            if dependency_listing_df.empty:

                dependency_listing_df = (
                    load_project_listings(
                        project_type="mod",
                        selected_gameplay_categories=None,
                        selected_platform_loaders=None,
                        selected_versions=None,
                        selected_project_id=dependency_row[
                            "project_id"
                        ],
                        selected_author_id=None,
                        selected_search=True,
                    )
                )

                if not dependency_listing_df.empty:

                    add_to_loaded_session(
                        "loaded_project_listings_df",
                        dependency_listing_df,
                        "project_id",
                    )

            if dependency_listing_df.empty:

                unresolved_dependencies.append({
                    "required_by": current_mod["title"],
                    "project_title": dependency_resolution[
                        "project_title"
                    ],
                    "project_id": dependency_resolution[
                        "project_id"
                    ],
                    "version_id": dependency_resolution[
                        "version_id"
                    ],
                    "reason": (
                        "Project listing metadata "
                        "could not be resolved."
                    ),
                })

                continue

            # -------------------------------------------------
            # BUILD NORMAL MOD-LIST ROW
            # -------------------------------------------------

            dependency_results_df = (
                build_search_results_df(
                    pd.DataFrame(
                        [dependency_row]
                    ),
                    dependency_listing_df,
                )
            )

            if dependency_results_df.empty:

                unresolved_dependencies.append({
                    "required_by": current_mod["title"],
                    "project_title": dependency_resolution[
                        "project_title"
                    ],
                    "project_id": dependency_resolution[
                        "project_id"
                    ],
                    "version_id": dependency_resolution[
                        "version_id"
                    ],
                    "reason": (
                        "Dependency row could not "
                        "be constructed."
                    ),
                })

                continue

            dependency_df = (
                dependency_results_df
                .head(1)
                .reindex(
                    columns=mod_list_columns
                )
                .copy()
            )

            # -------------------------------------------------
            # ADD DEPENDENCY
            # -------------------------------------------------

            updated_mod_list_df = (
                pd.concat(
                    [
                        updated_mod_list_df,
                        dependency_df,
                    ],
                    ignore_index=True,
                )
                .drop_duplicates(
                    subset=["version_id"]
                )
                .reset_index(drop=True)
            )

            added_dependencies.append({
                "title": dependency_df.iloc[0][
                    "title"
                ],
                "file_name": dependency_df.iloc[0][
                    "mod_file_name"
                ],
                "project_id": dependency_df.iloc[0][
                    "project_id"
                ],
                "version_id": dependency_df.iloc[0][
                    "version_id"
                ],
            })

            # Dependency may itself have dependencies.
            dependency_queue.append(
                dependency_df.iloc[0]
            )

    return (
        updated_mod_list_df,
        added_dependencies,
        unresolved_dependencies,
    )

def get_download_filename(
    url: str,
) -> str:

    filename = Path(
        unquote(
            urlparse(url).path
        )
    ).name

    if not filename:
        raise ValueError(
            f"Unable to determine filename from URL: {url}"
        )

    return filename


def get_unique_filename(
    filename: str,
    used_filenames: set[str],
) -> str:

    if filename not in used_filenames:
        used_filenames.add(filename)
        return filename

    file_path = Path(filename)

    counter = 2

    while True:
        candidate = (
            f"{file_path.stem}_{counter}"
            f"{file_path.suffix}"
        )

        if candidate not in used_filenames:
            used_filenames.add(candidate)
            return candidate

        counter += 1


async def download_files_to_zip_async(
    download_urls: list[str],
) -> BytesIO:

    zip_buffer = BytesIO()
    used_filenames = set()

    headers = {
        "User-Agent": (
            "liamxaro/Minecraft-Data-Platform/"
            "(contact: stormcraftmods@gmail.com)"
        )
    }

    rate_limiter = ModrinthRateLimiter(
        max_concurrency=8,
        max_requests_per_minute=295,
    )

    timeout = httpx.Timeout(
        120.0
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:

        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:

            for url in download_urls:

                filename = get_unique_filename(
                    get_download_filename(url),
                    used_filenames,
                )

                file_bytes = (
                    await download_response(
                        client=client,
                        rate_limiter=rate_limiter,
                        url=url,
                    )
                )

                archive.writestr(
                    filename,
                    file_bytes,
                )

    zip_buffer.seek(0)

    return zip_buffer


def download_files_to_zip(
    download_urls: list[str],
) -> BytesIO:

    return asyncio.run(
        download_files_to_zip_async(
            download_urls
        )
    )


async def download_files_to_folder_async(
    download_urls: list[str],
    folder_path: str,
) -> list[str]:

    output_folder = Path(
        folder_path
    ).expanduser()

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    used_filenames = set()
    downloaded_files = []

    headers = {
        "User-Agent": (
            "liamxaro/Minecraft-Data-Platform/1.0 "
            "(contact: stormcraftmods@gmail.com)"
        )
    }

    rate_limiter = ModrinthRateLimiter(
        max_concurrency=3,
        max_requests_per_minute=280,
    )

    timeout = httpx.Timeout(
        120.0
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:

        for url in download_urls:

            filename = get_unique_filename(
                get_download_filename(url),
                used_filenames,
            )

            output_path = (
                output_folder
                / filename
            )

            file_bytes = (
                await download_response(
                    client=client,
                    rate_limiter=rate_limiter,
                    url=url,
                )
            )

            output_path.write_bytes(
                file_bytes
            )

            downloaded_files.append(
                str(output_path)
            )

    return downloaded_files


def download_files_to_folder(
    download_urls: list[str],
    folder_path: str,
) -> list[str]:

    return asyncio.run(
        download_files_to_folder_async(
            download_urls=download_urls,
            folder_path=folder_path,
        )
    )


def get_api_download_url(
    files,
) -> str | None:

    if files is None:
        return None

    if isinstance(files, str):
        try:
            files = json.loads(files)
        except json.JSONDecodeError:
            return None

    if not isinstance(files, list) or not files:
        return None

    primary_file = next(
        (
            file_info
            for file_info in files
            if file_info.get("primary") is True
        ),
        files[0],
    )

    return primary_file.get("url")


def prepare_download_urls(
    download_df: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame]:

    if (
        download_df.empty
        or "api_download_url" not in download_df.columns
    ):
        return [], pd.DataFrame()

    prepared_df = download_df.copy()

    prepared_df["api_download_url"] = (
        prepared_df["api_download_url"]
        .astype("string")
        .str.strip()
    )

    prepared_df = prepared_df[
        prepared_df["api_download_url"].notna()
        & prepared_df["api_download_url"].str.startswith(
            ("http://", "https://")
        )
    ].copy()

    duplicate_version_rows_df = pd.DataFrame()

    if "version_id" in prepared_df.columns:
        normalized_version_ids = (
            prepared_df["version_id"]
            .astype("string")
            .str.strip()
        )

        valid_version_id_mask = (
            normalized_version_ids.notna()
            & normalized_version_ids.ne("")
        )

        duplicate_version_mask = (
            valid_version_id_mask
            & normalized_version_ids.duplicated(
                keep=False
            )
        )

        duplicate_version_rows_df = (
            prepared_df[duplicate_version_mask]
            .copy()
        )

        rows_with_version_id_df = (
            prepared_df[valid_version_id_mask]
            .drop_duplicates(
                subset=["version_id"],
                keep="first",
            )
        )

        rows_without_version_id_df = (
            prepared_df[~valid_version_id_mask]
        )

        prepared_df = (
            pd.concat(
                [
                    rows_with_version_id_df,
                    rows_without_version_id_df,
                ],
                axis=0,
            )
            .sort_index()
        )

    prepared_df = prepared_df.drop_duplicates(
        subset=["api_download_url"],
        keep="first",
    )

    return (
        prepared_df["api_download_url"].tolist(),
        duplicate_version_rows_df,
    )

def get_compatibility_dimension_state(
    mod_list_df: pd.DataFrame,
    column_name: str,
    selected_value: str | None = None,
) -> dict:
    value_sets = []

    if column_name not in mod_list_df.columns:
        return {
            "target_value": None,
            "options": [],
            "requires_selection": False,
        }

    for value in mod_list_df[column_name]:
        normalized_values = normalize_multi_value(
            value
        )

        if normalized_values:
            value_sets.append(
                set(normalized_values)
            )

    if not value_sets:
        return {
            "target_value": None,
            "options": [],
            "requires_selection": False,
        }

    all_values = sorted(
        set.union(*value_sets)
    )

    # Preserve a previous explicit choice when every currently
    # selected file still supports it.
    if (
        selected_value
        and selected_value in all_values
        and all(
            selected_value in value_set
            for value_set in value_sets
        )
    ):
        return {
            "target_value": selected_value,
            "options": all_values,
            "requires_selection": False,
        }

    single_values = [
        next(iter(value_set))
        for value_set in value_sets
        if len(value_set) == 1
    ]

    unique_single_values = set(
        single_values
    )

    # Single-option files anchor the target when they all agree.
    # Multi-option files are compatible as long as they include
    # that anchored value.
    if len(unique_single_values) == 1:
        anchored_value = next(
            iter(unique_single_values)
        )

        if all(
            anchored_value in value_set
            for value_set in value_sets
        ):
            return {
                "target_value": anchored_value,
                "options": all_values,
                "requires_selection": False,
            }

    # If every file has only one possible value and they all agree,
    # there is no decision to make.
    if len(all_values) == 1:
        return {
            "target_value": all_values[0],
            "options": all_values,
            "requires_selection": False,
        }

    # Conflicting single-option files, or a list made entirely of
    # multi-option files, requires an explicit user choice. Choosing
    # a value will remove files that do not support it.
    return {
        "target_value": None,
        "options": all_values,
        "requires_selection": True,
    }


def filter_mod_list_to_compatibility_target(
    mod_list_df: pd.DataFrame,
    target_loader: str,
    target_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    compatible_mask = (
        mod_list_df["loaders"].apply(
            lambda loaders: (
                target_loader
                in normalize_multi_value(loaders)
            )
        )
        & mod_list_df["game_versions"].apply(
            lambda game_versions: (
                target_version
                in normalize_multi_value(
                    game_versions
                )
            )
        )
    )

    compatible_mod_list_df = (
        mod_list_df[compatible_mask]
        .copy()
        .reset_index(drop=True)
    )

    removed_mod_list_df = (
        mod_list_df[~compatible_mask]
        .copy()
        .reset_index(drop=True)
    )

    return (
        compatible_mod_list_df,
        removed_mod_list_df,
    )


def format_loader_name(loader: str | None) -> str:
    if not loader:
        return "Select"

    loader_names = {
        "fabric": "Fabric",
        "forge": "Forge",
        "neoforge": "NeoForge",
        "quilt": "Quilt",
    }

    return loader_names.get(
        loader.lower(),
        loader,
    )


def get_mod_list_compatibility_scope(
    mod_list_df: pd.DataFrame,
    selected_platform_loaders: list[str],
    selected_versions: list[str],
) -> tuple[list[str], list[str]]:

    loader_sets = []

    for loaders in mod_list_df["loaders"]:
        normalized_loaders = normalize_multi_value(loaders)

        if normalized_loaders:
            loader_sets.append(set(normalized_loaders))

    game_version_sets = []

    for game_versions in mod_list_df["game_versions"]:
        normalized_game_versions = normalize_multi_value(
            game_versions
        )

        if normalized_game_versions:
            game_version_sets.append(
                set(normalized_game_versions)
            )

    common_loaders = (
        set.intersection(*loader_sets)
        if loader_sets
        else set()
    )

    common_game_versions = (
        set.intersection(*game_version_sets)
        if game_version_sets
        else set()
    )

    selected_loader_values = normalize_multi_value(
        selected_platform_loaders
    )

    selected_version_values = normalize_multi_value(
        selected_versions
    )

    if selected_loader_values:
        common_loaders &= set(selected_loader_values)

    if selected_version_values:
        common_game_versions &= set(selected_version_values)

    return (
        sorted(common_loaders),
        sorted(common_game_versions),
    )


def filter_versions_to_scope(
    versions_df: pd.DataFrame,
    required_loaders: list[str],
    required_versions: list[str],
) -> pd.DataFrame:

    if versions_df.empty:
        return versions_df

    filtered_df = versions_df.copy()

    if required_loaders:
        filtered_df = filtered_df[
            filtered_df["loaders"].apply(
                lambda loaders: value_matches_filter(
                    loaders,
                    required_loaders,
                )
            )
        ]

    if required_versions:
        filtered_df = filtered_df[
            filtered_df["game_versions"].apply(
                lambda versions: value_matches_filter(
                    versions,
                    required_versions,
                )
            )
        ]

    return filtered_df


async def download_response(
    client: httpx.AsyncClient,
    rate_limiter: ModrinthRateLimiter,
    url: str,
    max_attempts: int = 5,
) -> bytes:

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        await rate_limiter.wait_for_request_slot()

        async with rate_limiter.semaphore:

            response = await client.get(
                url,
            )

        if response.status_code == 429:

            await rate_limiter.update_from_429(
                response
            )

            await rate_limiter.wait_if_paused()

            continue

        await rate_limiter.update_from_response(
            response
        )

        if response.status_code in {
            500,
            502,
            503,
            504,
        }:

            if attempt == max_attempts:
                response.raise_for_status()

            await asyncio.sleep(
                min(
                    2 ** attempt,
                    30,
                )
            )

            continue

        response.raise_for_status()

        return response.content

    raise RuntimeError(
        f"Unable to download after "
        f"{max_attempts} attempts: {url}"
    )
# ---------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------

first_activity = get_first_activity(project_type="mod").iloc[0]["first_activity_date"]
kpi_df = load_kpis()
current_kpis = kpi_df.loc[kpi_df["snapshot"] == "current"].iloc[0]

title_col, refresh_col = st.columns([6, 2], vertical_alignment="center")

with title_col:
    apply_modrinth_theme(
        "Minecraft Mod Compatibility Board",
        "Search Modrinth mods, build a mod list, and validate compatibility step by step.",
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


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

mod_list_columns = [
    "project_id",
    "version_id",
    "title",
    "author",
    "description",
    "game_versions",
    "mod_file_name",
    "version_number",
    "loaders",
    "server_side",
    "client_side",
    "environment",
    "date_published",
    "manual_download_url",
    "api_download_url",
    "dependencies"
]

mod_list_schema_version = 3

if "project_versions_df" not in st.session_state:
    st.session_state["project_versions_df"] = pd.DataFrame()

if "project_listings_df" not in st.session_state:
    st.session_state["project_listings_df"] = pd.DataFrame()

if (
    "mod_list_df" not in st.session_state
    or st.session_state.get("mod_list_schema_version") != mod_list_schema_version
    or list(st.session_state["mod_list_df"].columns) != mod_list_columns
):
    st.session_state["mod_list_df"] = pd.DataFrame(columns=mod_list_columns)
    st.session_state["mod_list_schema_version"] = mod_list_schema_version
    st.session_state.pop("compatibility_report_df", None)
    
if "loaded_project_versions_df" not in st.session_state:
    st.session_state["loaded_project_versions_df"] = pd.DataFrame()

if "loaded_project_listings_df" not in st.session_state:
    st.session_state["loaded_project_listings_df"] = pd.DataFrame()
    

if "confirm_clear_mod_list" not in st.session_state:
    st.session_state["confirm_clear_mod_list"] = False


# ---------------------------------------------------------
# FILTER OPTIONS
# ---------------------------------------------------------

versions_df = load_versions()
platform_loaders_df = load_platform_loaders()
gameplay_categories_df = load_gameplay_categories()

gameplay_category_options = ["All"] + gameplay_categories_df["name"].tolist()
platform_loader_options = ["All"] + platform_loaders_df["platform_loaders"].tolist()
version_options = ["All"] + versions_df["version"].tolist()


# ---------------------------------------------------------
# MOD SEARCH
# ---------------------------------------------------------

brand_subheader("Search for Mods")


with st.form("project_versions_filter_form"):
    filter_version_col1, filter_version_col2, filter_version_col3 = st.columns(3)
    filter_version_col4, filter_version_col5, filter_version_col6 = st.columns(3)

    with filter_version_col1:
        selected_versions_gameplay_categories = st.multiselect(
            "Filter Mods by Gameplay Category",
            options=gameplay_category_options,
            default=[],
            key="compatibility_gameplay_category_multiselect",
        )

    with filter_version_col2:
        selected_versions_platform_loaders = st.multiselect(
            "Filter Mods by Platform Loader",
            options=platform_loader_options,
            default=[],
            key="compatibility_platform_loader_multiselect",
        )

    with filter_version_col3:
        selected_versions_versions = st.multiselect(
            "Filter Mods by Minecraft Version",
            options=version_options,
            default=[],
            placeholder="All versions",
            key="compatibility_version_multiselect",
        )

    with filter_version_col4:
        selected_versions_project_id = st.text_input(
            "Filter Mods by Project ID",
            placeholder="Enter a specific project ID (CASE SENSITIVE)",
            key="compatibility_project_id_search_input",
        )

    with filter_version_col5:
        selected_versions_author_id = st.text_input(
            "Filter Mods by Author ID",
            placeholder="Enter a specific author ID (CASE SENSITIVE)",
            key="compatibility_author_id_search_input",
        )

    with filter_version_col6:
        selected_versions_search = st.toggle(
            "Match All Filters (ON) or Any Filter (OFF)",
            value=False,
            key="compatibility_search_toggle",
        )

    search_col1, search_col2 = st.columns([4, 1])

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

selected_versions_versions = [
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
        selected_search=selected_versions_search,
    )

    st.session_state["project_listings_df"] = load_project_listings(
        project_type="mod",
        selected_gameplay_categories=selected_versions_gameplay_categories,
        selected_platform_loaders=selected_versions_platform_loaders,
        selected_versions=selected_versions_versions,
        selected_project_id=selected_versions_project_id if selected_versions_project_id else None,
        selected_author_id=selected_versions_author_id if selected_versions_author_id else None,
        selected_search=selected_versions_search,
    )
    
    add_to_loaded_session(
    "loaded_project_versions_df",
    st.session_state["project_versions_df"],
    "version_id",
    )

    add_to_loaded_session(
        "loaded_project_listings_df",
        st.session_state["project_listings_df"],
        "project_id",
    )
    
project_versions_df = st.session_state["project_versions_df"]
project_listings_df = st.session_state["project_listings_df"]


# ---------------------------------------------------------
# SEARCH RESULTS
# ---------------------------------------------------------

if not project_versions_df.empty and not project_listings_df.empty:
    search_results_df = build_search_results_df(
        project_versions_df,
        project_listings_df,
    )

    search_results_df.insert(0, "selected", False)

    filter_col1, filter_col2 = st.columns([1, 3])

    with filter_col1:
        filter_column = st.selectbox(
            "Filter Column",
            options=[
                "title",
                "project_id",
                "version_id",
                "author",
                "mod_file_name",
                "version_number",
                "server_side",
                "client_side",
                "environment",
            ],
            key="search_results_filter_column",
        )

    with filter_col2:
        filter_value = st.text_input(
            "Filter Value",
            placeholder="Type to filter...",
            key="search_results_filter_value",
        )

    filtered_search_results_df = search_results_df

    if filter_value:
        filtered_search_results_df = filtered_search_results_df[
            filtered_search_results_df[filter_column]
            .astype(str)
            .str.contains(
                filter_value,
                case=False,
                na=False,
            )
        ]


    st.markdown("#### Search Results")
    
    st.caption(
            f"{filtered_search_results_df['project_id'].nunique():,} project(s) found | "
            f"{len(filtered_search_results_df):,} project version(s) loaded"
        )

    edited_search_results_df = st.data_editor(
        filtered_search_results_df,
        hide_index=True,
        use_container_width=True,
        key="compatibility_search_results_editor",
        column_config={
            "selected": st.column_config.CheckboxColumn(
                "Add",
                default=False,
            ),
            "project_id": st.column_config.TextColumn("Project ID"),
            "version_id": st.column_config.TextColumn("Version ID"),
            "title": st.column_config.TextColumn("Title"),
            "author": st.column_config.TextColumn("Author"),
            "description": st.column_config.TextColumn("Description"),
            "game_versions": st.column_config.ListColumn("Minecraft Versions"),
            "mod_file_name": st.column_config.TextColumn("Mod File Name"),
            "version_number": st.column_config.TextColumn("Mod Version"),
            "loaders": st.column_config.ListColumn("Platform Loaders"),
            "server_side": st.column_config.TextColumn("Server Side"),
            "client_side": st.column_config.TextColumn("Client Side"),
            "environment": st.column_config.TextColumn("Environment"),
            "date_published": st.column_config.DatetimeColumn("Date Published"),
            "manual_download_url": st.column_config.LinkColumn("Manual Download"),
            "api_download_url": st.column_config.LinkColumn("API Download"),
            "dependencies": None,
        },
        disabled=[
            column
            for column in filtered_search_results_df.columns
            if column != "selected"
        ],
    )

    add_selected_col1, add_selected_col2 = st.columns([4, 1])

    with add_selected_col2:
        add_selected_mods = st.button(
            "Add Selected Mods",
            type="primary",
            use_container_width=True,
            key="compatibility_add_selected_mods_button",
        )

    if add_selected_mods:
        selected_mods_df = (
            edited_search_results_df[
                edited_search_results_df["selected"]
            ]
            .drop(columns=["selected"])
            .reindex(columns=mod_list_columns)
            .copy()
        )

        if selected_mods_df.empty:
            st.warning("Select at least one mod first.")
        else:
            current_count = len(st.session_state["mod_list_df"])

            st.session_state["mod_list_df"] = (
                pd.concat(
                    [st.session_state["mod_list_df"], selected_mods_df],
                    ignore_index=True,
                )
                .reindex(columns=mod_list_columns)
                .drop_duplicates(subset=["version_id"])
                .reset_index(drop=True)
            )

            new_count = len(st.session_state["mod_list_df"])
            added_count = new_count - current_count
            st.session_state.pop("compatibility_report_df", None)
            st.success(f"Added {added_count:,} new mod version(s).")

elif selected_versions_submit:
    st.info("No matching mod versions were found.")
else:
    st.info("Use the filters above to search for mods.")


# ---------------------------------------------------------
# ADD DIRECTLY BY PROJECT ID
# ---------------------------------------------------------

st.markdown("#### Add Directly by Project ID")
st.caption("Adding by Project ID adds the newest version currently available in your data.")

manual_project_id_col, add_project_id_col = st.columns([4, 1])

with manual_project_id_col:
    manual_project_id = st.text_input(
        "Modrinth Project ID",
        placeholder="Example: AANobbMI",
        key="compatibility_manual_project_id",
    )

with add_project_id_col:
    st.write("")
    add_project_id = st.button(
        "Add Mod",
        type="primary",
        use_container_width=True,
        key="compatibility_add_project_id_button",
    )


if add_project_id:
    manual_project_id = manual_project_id.strip()

    if not manual_project_id:
        st.warning("Enter a Modrinth project ID.")

    else:
        compatibility_target_loader = (
            st.session_state.get(
                "compatibility_target_loader"
            )
        )
        compatibility_target_version = (
            st.session_state.get(
                "compatibility_target_version"
            )
        )

        direct_add_loaders = (
            [compatibility_target_loader]
            if compatibility_target_loader
            else selected_versions_platform_loaders
        )
        direct_add_versions = (
            [compatibility_target_version]
            if compatibility_target_version
            else selected_versions_versions
        )

        project_id_versions_df = load_project_versions(
            project_type="mod",
            selected_gameplay_categories=None,
            selected_platform_loaders=direct_add_loaders,
            selected_versions=direct_add_versions,
            selected_project_id=manual_project_id,
            selected_author_id=None,
            selected_search=True,
        )

        project_id_listings_df = load_project_listings(
            project_type="mod",
            selected_gameplay_categories=None,
            selected_platform_loaders=None,
            selected_versions=None,
            selected_project_id=manual_project_id,
            selected_author_id=None,
            selected_search=True,
        )
        
        add_to_loaded_session(
            "loaded_project_versions_df",
            project_id_versions_df,
            "version_id",
        )

        add_to_loaded_session(
            "loaded_project_listings_df",
            project_id_listings_df,
            "project_id",
        )

        if project_id_versions_df.empty:
            st.error(
                f"Project ID `{manual_project_id}` does not have a version matching "
                "the current compatibility target or search filters."
            )

        elif project_id_listings_df.empty:
            st.error(
                f"No Modrinth project listing was found for `{manual_project_id}`."
            )

        else:
            project_id_results_df = build_search_results_df(
                project_id_versions_df,
                project_id_listings_df,
            )

            mod_to_add_df = (
                project_id_results_df
                .sort_values("date_published", ascending=False)
                .head(1)
                .reindex(columns=mod_list_columns)
                .copy()
            )

            current_count = len(st.session_state["mod_list_df"])

            st.session_state["mod_list_df"] = (
                pd.concat(
                    [
                        st.session_state["mod_list_df"],
                        mod_to_add_df,
                    ],
                    ignore_index=True,
                )
                .drop_duplicates(subset=["version_id"])
                .reset_index(drop=True)
            )

            new_count = len(st.session_state["mod_list_df"])
            project_title = mod_to_add_df.iloc[0]["title"]

            if new_count == current_count:
                st.info(f"{project_title} is already in the mod list.")

            else:
                st.session_state.pop("compatibility_report_df", None)
                st.success(f"Added the latest matching version of {project_title}.")

# ---------------------------------------------------------
# MOD COMPATIBILITY LIST
# ---------------------------------------------------------

st.divider()

mod_list_title_col, clear_list_col = st.columns(
    [6, 1],
    vertical_alignment="center",
)

with mod_list_title_col:
    st.subheader("Mod Compatibility List")

with clear_list_col:
    clear_mod_list = st.button(
        "Clear List",
        use_container_width=True,
        disabled=(
            st.session_state["mod_list_df"].empty
        ),
        key="clear_mod_list_button",
    )

if clear_mod_list:
    st.session_state[
        "confirm_clear_mod_list"
    ] = True

if st.session_state["confirm_clear_mod_list"]:
    st.warning(
        "Clear the entire compatibility list? "
        "This cannot be undone."
    )

    confirm_clear_col1, confirm_clear_col2 = (
        st.columns([4, 1])
    )

    with confirm_clear_col2:
        cancel_clear_col, confirm_clear_col = (
            st.columns(2)
        )

        with cancel_clear_col:
            if st.button(
                "Cancel",
                use_container_width=True,
                key="cancel_clear_mod_list_button",
            ):
                st.session_state[
                    "confirm_clear_mod_list"
                ] = False
                st.rerun()

        with confirm_clear_col:
            if st.button(
                "Yes, Clear",
                use_container_width=True,
                key="confirm_clear_mod_list_button",
            ):
                st.session_state["mod_list_df"] = (
                    pd.DataFrame(
                        columns=mod_list_columns
                    )
                )

                for state_key in [
                    "compatibility_report_df",
                    "last_added_dependencies",
                    "last_unresolved_dependencies",
                    "compatibility_target_loader",
                    "compatibility_target_version",
                    "compatibility_selection_notice",
                    "compatibility_loader_choice_input",
                    "compatibility_version_choice_input",
                ]:
                    st.session_state.pop(
                        state_key,
                        None,
                    )

                st.session_state[
                    "confirm_clear_mod_list"
                ] = False

                st.rerun()

mod_list_df = (
    st.session_state["mod_list_df"]
    .reindex(columns=mod_list_columns)
    .copy()
)

if mod_list_df.empty:
    st.session_state.pop(
        "compatibility_target_loader",
        None,
    )
    st.session_state.pop(
        "compatibility_target_version",
        None,
    )

current_target_loader = st.session_state.get(
    "compatibility_target_loader"
)
current_target_version = st.session_state.get(
    "compatibility_target_version"
)

loader_state = get_compatibility_dimension_state(
    mod_list_df,
    "loaders",
    current_target_loader,
)

version_state = get_compatibility_dimension_state(
    mod_list_df,
    "game_versions",
    current_target_version,
)

target_loader = loader_state["target_value"]
target_version = version_state["target_value"]

# Persist automatically determined targets. Explicit user choices
# are also preserved here as long as every selected file supports them.
if target_loader:
    st.session_state[
        "compatibility_target_loader"
    ] = target_loader

if target_version:
    st.session_state[
        "compatibility_target_version"
    ] = target_version

st.caption(
    "Build your working mod list, then assess whether the selected mod versions "
    "share a loader, Minecraft version, and compatible dependency metadata."
)

st.caption(
    f"Selected files: {len(mod_list_df):,} | "
    f"Loader: {format_loader_name(target_loader)} | "
    f"Minecraft Version: {target_version or 'Select'}"
)

selection_notice = st.session_state.pop(
    "compatibility_selection_notice",
    None,
)

if selection_notice:
    st.success(selection_notice)

loader_requires_selection = loader_state[
    "requires_selection"
]
version_requires_selection = version_state[
    "requires_selection"
]

if (
    not mod_list_df.empty
    and (
        loader_requires_selection
        or version_requires_selection
    )
):
    st.warning(
        "The selected files do not determine one compatibility target. "
        "Choose the loader and/or Minecraft version you want to build for. "
        "Files that do not support your choice will be removed from the list."
    )

    selection_col1, selection_col2 = (
        st.columns(2)
    )

    loader_choice = target_loader
    version_choice = target_version

    with selection_col1:
        if loader_requires_selection:
            loader_options = loader_state[
                "options"
            ]

            existing_loader = (
                current_target_loader
                if current_target_loader
                in loader_options
                else None
            )

            loader_choice_key = (
                "compatibility_loader_choice_input"
            )

            if (
                st.session_state.get(
                    loader_choice_key
                )
                not in loader_options
            ):
                st.session_state.pop(
                    loader_choice_key,
                    None,
                )

            loader_choice = st.selectbox(
                "Choose Platform Loader",
                options=loader_options,
                index=(
                    loader_options.index(
                        existing_loader
                    )
                    if existing_loader
                    else None
                ),
                placeholder="Select a loader",
                format_func=format_loader_name,
                key=loader_choice_key,
            )
        else:
            st.info(
                "Platform Loader: "
                f"{format_loader_name(target_loader)}"
            )

    with selection_col2:
        if version_requires_selection:
            version_options = version_state[
                "options"
            ]

            existing_version = (
                current_target_version
                if current_target_version
                in version_options
                else None
            )

            version_choice_key = (
                "compatibility_version_choice_input"
            )

            if (
                st.session_state.get(
                    version_choice_key
                )
                not in version_options
            ):
                st.session_state.pop(
                    version_choice_key,
                    None,
                )

            version_choice = st.selectbox(
                "Choose Minecraft Version",
                options=version_options,
                index=(
                    version_options.index(
                        existing_version
                    )
                    if existing_version
                    else None
                ),
                placeholder=(
                    "Select a Minecraft version"
                ),
                key=version_choice_key,
            )
        else:
            st.info(
                "Minecraft Version: "
                f"{target_version}"
            )

    selection_complete = bool(
        loader_choice
        and version_choice
    )

    if st.button(
        "Apply Compatibility Choices",
        type="primary",
        use_container_width=True,
        disabled=not selection_complete,
        key="apply_compatibility_choices_button",
    ):
        (
            compatible_mod_list_df,
            removed_mod_list_df,
        ) = filter_mod_list_to_compatibility_target(
            mod_list_df,
            target_loader=loader_choice,
            target_version=version_choice,
        )

        st.session_state["mod_list_df"] = (
            compatible_mod_list_df
        )
        st.session_state[
            "compatibility_target_loader"
        ] = loader_choice
        st.session_state[
            "compatibility_target_version"
        ] = version_choice

        st.session_state.pop(
            "compatibility_report_df",
            None,
        )
        st.session_state.pop(
            "last_added_dependencies",
            None,
        )
        st.session_state.pop(
            "last_unresolved_dependencies",
            None,
        )

        removed_count = len(
            removed_mod_list_df
        )

        if removed_count:
            removed_titles = (
                removed_mod_list_df["title"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            st.session_state[
                "compatibility_selection_notice"
            ] = (
                f"Compatibility target set to "
                f"{format_loader_name(loader_choice)} + "
                f"Minecraft {version_choice}. "
                f"Removed {removed_count:,} incompatible file(s): "
                + ", ".join(removed_titles)
            )
        else:
            st.session_state[
                "compatibility_selection_notice"
            ] = (
                f"Compatibility target set to "
                f"{format_loader_name(loader_choice)} + "
                f"Minecraft {version_choice}. "
                "No files needed to be removed."
            )

        st.rerun()

compatibility_scope_ready = bool(
    target_loader
    and target_version
    and not loader_requires_selection
    and not version_requires_selection
)

if not mod_list_df.empty:
    editable_mod_list_df = mod_list_df.copy()
    editable_mod_list_df.insert(
        0,
        "remove",
        False,
    )

    edited_mod_list_df = st.data_editor(
        editable_mod_list_df,
        hide_index=True,
        use_container_width=True,
        key="compatibility_mod_list_editor",
        column_config={
            "remove": (
                st.column_config.CheckboxColumn(
                    "Remove",
                    default=False,
                )
            ),
            "project_id": (
                st.column_config.TextColumn(
                    "Project ID"
                )
            ),
            "version_id": (
                st.column_config.TextColumn(
                    "Version ID"
                )
            ),
            "title": (
                st.column_config.TextColumn(
                    "Mod"
                )
            ),
            "author": (
                st.column_config.TextColumn(
                    "Author"
                )
            ),
            "description": (
                st.column_config.TextColumn(
                    "Description"
                )
            ),
            "game_versions": (
                st.column_config.ListColumn(
                    "Minecraft Versions"
                )
            ),
            "mod_file_name": (
                st.column_config.TextColumn(
                    "Mod File Name"
                )
            ),
            "version_number": (
                st.column_config.TextColumn(
                    "Mod Version"
                )
            ),
            "loaders": (
                st.column_config.ListColumn(
                    "Platform Loaders"
                )
            ),
            "server_side": (
                st.column_config.TextColumn(
                    "Server Side"
                )
            ),
            "client_side": (
                st.column_config.TextColumn(
                    "Client Side"
                )
            ),
            "environment": (
                st.column_config.TextColumn(
                    "Environment"
                )
            ),
            "date_published": (
                st.column_config.DatetimeColumn(
                    "Date Published"
                )
            ),
            "manual_download_url": (
                st.column_config.LinkColumn(
                    "Manual Download"
                )
            ),
            "api_download_url": (
                st.column_config.LinkColumn(
                    "API Download"
                )
            ),
            "dependencies": None,
        },
        disabled=[
            column
            for column in editable_mod_list_df.columns
            if column != "remove"
        ],
    )

    action_col1, action_col2, action_col3 = (
        st.columns(3)
    )

    with action_col1:
        if st.button(
            "Remove Selected Mods",
            use_container_width=True,
            key=(
                "compatibility_remove_selected_mods_button"
            ),
        ):
            remove_indices = (
                edited_mod_list_df.index[
                    edited_mod_list_df["remove"]
                ]
            )

            st.session_state["mod_list_df"] = (
                mod_list_df
                .drop(index=remove_indices)
                .reset_index(drop=True)
            )

            st.session_state.pop(
                "compatibility_report_df",
                None,
            )
            st.session_state.pop(
                "last_added_dependencies",
                None,
            )
            st.session_state.pop(
                "last_unresolved_dependencies",
                None,
            )

            st.rerun()

    with action_col2:
        assess_compatibility = st.button(
            "Assess Compatibility",
            use_container_width=True,
            disabled=not compatibility_scope_ready,
            key="assess_mod_compatibility_button",
        )

    with action_col3:
        add_dependencies = st.button(
            "Add Dependencies & Reassess",
            type="primary",
            use_container_width=True,
            disabled=not compatibility_scope_ready,
            key=(
                "add_dependencies_and_reassess_button"
            ),
        )

    if not compatibility_scope_ready:
        st.caption(
            "Choose one platform loader and one Minecraft version "
            "before assessing compatibility or adding dependencies."
        )

    compatibility_loaders = (
        [target_loader]
        if target_loader
        else []
    )
    compatibility_versions = (
        [target_version]
        if target_version
        else []
    )

    if assess_compatibility:
        st.session_state[
            "compatibility_report_df"
        ] = assess_mod_compatibility(
            mod_list_df,
            selected_platform_loaders=(
                compatibility_loaders
            ),
            selected_versions=(
                compatibility_versions
            ),
        )

    if add_dependencies:
        (
            updated_mod_list_df,
            added_dependencies,
            unresolved_dependencies,
        ) = add_required_dependencies(
            mod_list_df=mod_list_df,
            selected_platform_loaders=(
                compatibility_loaders
            ),
            selected_versions=(
                compatibility_versions
            ),
        )

        st.session_state["mod_list_df"] = (
            updated_mod_list_df
        )
        st.session_state[
            "last_added_dependencies"
        ] = added_dependencies
        st.session_state[
            "last_unresolved_dependencies"
        ] = unresolved_dependencies

        duplicate_project_ids = (
            get_duplicate_projects(
                updated_mod_list_df
            )
        )

        if duplicate_project_ids:
            st.session_state.pop(
                "compatibility_report_df",
                None,
            )

        else:
            st.session_state[
                "compatibility_report_df"
            ] = assess_mod_compatibility(
                updated_mod_list_df,
                selected_platform_loaders=(
                    compatibility_loaders
                ),
                selected_versions=(
                    compatibility_versions
                ),
            )

        st.rerun()

    mod_list_df = st.session_state[
        "mod_list_df"
    ]

    last_added_dependencies = (
        st.session_state.get(
            "last_added_dependencies",
            [],
        )
    )

    last_unresolved_dependencies = (
        st.session_state.get(
            "last_unresolved_dependencies",
            [],
        )
    )

    if last_added_dependencies:
        st.success(
            f"Added {len(last_added_dependencies):,} required "
            "dependency mod(s)."
        )

    if last_unresolved_dependencies:
        st.warning(
            f"{len(last_unresolved_dependencies):,} required "
            "dependency item(s) could not be automatically resolved."
        )

        st.dataframe(
            pd.DataFrame(
                last_unresolved_dependencies
            ),
            hide_index=True,
            use_container_width=True,
        )

    duplicate_project_ids = (
        get_duplicate_projects(
            mod_list_df
        )
    )

    if duplicate_project_ids:
        st.warning(
            "Multiple versions of the same mod are in the list. "
            "Choose which version of each mod you want to keep."
        )

        version_choices = {}

        for project_id in duplicate_project_ids:
            duplicate_versions_df = (
                mod_list_df[
                    mod_list_df[
                        "project_id"
                    ] == project_id
                ]
                .sort_values(
                    "date_published",
                    ascending=False,
                )
                .reset_index(drop=True)
            )

            project_title = (
                duplicate_versions_df.iloc[0][
                    "title"
                ]
            )

            version_options = (
                duplicate_versions_df[
                    "version_id"
                ].tolist()
            )

            def format_version_option(
                version_id,
                versions_df=(
                    duplicate_versions_df
                ),
            ):
                version_row = versions_df[
                    versions_df[
                        "version_id"
                    ] == version_id
                ].iloc[0]

                return (
                    f"Project Listing Version: {version_row['version_number']} | "
                    f"Project Listing File Name: {version_row['mod_file_name']} | "
                    f"Project Listing Date Published: {version_row['date_published']}"
                )

            version_choices[project_id] = (
                st.selectbox(
                    f"{project_title} — Version to Keep",
                    options=version_options,
                    index=0,
                    format_func=(
                        format_version_option
                    ),
                    key=(
                        f"duplicate_version_{project_id}"
                    ),
                )
            )

        if st.button(
            "Keep Selected Versions & Reassess",
            type="primary",
            use_container_width=True,
            disabled=not compatibility_scope_ready,
            key=(
                "resolve_duplicate_versions_button"
            ),
        ):
            resolved_mod_list_df = (
                apply_duplicate_version_choices(
                    mod_list_df,
                    version_choices,
                )
            )

            st.session_state["mod_list_df"] = (
                resolved_mod_list_df
            )

            st.session_state[
                "compatibility_report_df"
            ] = assess_mod_compatibility(
                resolved_mod_list_df,
                selected_platform_loaders=(
                    compatibility_loaders
                ),
                selected_versions=(
                    compatibility_versions
                ),
            )

            st.rerun()

    compatibility_report_df = (
        st.session_state.get(
            "compatibility_report_df"
        )
    )

    if (
        compatibility_report_df is not None
        and not compatibility_report_df.empty
    ):
        st.subheader(
            "Compatibility Assessment"
        )

        error_count = (
            compatibility_report_df["level"]
            .eq("ERROR")
            .sum()
        )

        warning_count = (
            compatibility_report_df["level"]
            .eq("WARNING")
            .sum()
        )

        if error_count > 0:
            st.error(
                f"{error_count} compatibility error(s) detected. "
                "This exact combination should not currently be treated as compatible."
            )

        elif warning_count > 0:
            st.warning(
                f"{warning_count} compatibility warning(s) detected."
            )

        else:
            st.info(
                "No Modrinth metadata conflicts were detected. "
                "Runtime compatibility is still not guaranteed."
            )

        for _, row in (
            compatibility_report_df.iterrows()
        ):
            message = (
                f"**{row['mod']} — {row['issue']}**  \n"
                f"{row['details']}"
            )

            if row["level"] == "ERROR":
                st.error(message)

            elif row["level"] == "WARNING":
                st.warning(message)

            else:
                st.info(message)

        st.dataframe(
            compatibility_report_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "level": (
                    st.column_config.TextColumn(
                        "Level"
                    )
                ),
                "mod": (
                    st.column_config.TextColumn(
                        "Mod"
                    )
                ),
                "issue": (
                    st.column_config.TextColumn(
                        "Assessment"
                    )
                ),
                "details": (
                    st.column_config.TextColumn(
                        "Details",
                        width="large",
                    )
                ),
            },
        )

    xlsx_mod_list_df = prepare_excel_df(
        mod_list_df
    )

    if (
        compatibility_report_df is not None
        and not compatibility_report_df.empty
    ):
        xlsx_compatibility_df = prepare_excel_df(
            compatibility_report_df
        )

    else:
        xlsx_compatibility_df = pd.DataFrame([
            {
                "level": "INFO",
                "mod": "Mod List",
                "issue": "Compatibility not assessed",
                "details": (
                    "Run Assess Compatibility before downloading "
                    "for a full compatibility report."
                ),
            }
        ])

    xlsx_buffer = BytesIO()

    with pd.ExcelWriter(
        xlsx_buffer,
        engine="xlsxwriter",
    ) as writer:
        xlsx_mod_list_df.to_excel(
            writer,
            index=False,
            sheet_name=(
                "Mod Compatibility List"
            ),
        )

        xlsx_compatibility_df.to_excel(
            writer,
            index=False,
            sheet_name=(
                "Compatibility Assessment"
            ),
        )

    st.download_button(
        "Download Mod List (.xlsx)",
        data=xlsx_buffer.getvalue(),
        file_name=(
            "minecraft_mod_compatibility_list_"
            f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

st.divider()

st.subheader("Modrinth Download Tool")

st.caption(
    "Download Modrinth files from an uploaded Excel file "
    "or from the current compatibility session."
)


download_source = st.radio(
    "Where should the download links come from?",
    options=[
        "Current App Session",
        "Upload Excel File",
    ],
    horizontal=True,
    key="modrinth_download_source",
)


download_urls = []
duplicate_download_versions_df = pd.DataFrame()


if download_source == "Upload Excel File":

    uploaded_download_file = st.file_uploader(
        "Upload Excel File",
        type=["xlsx"],
        key="modrinth_download_excel",
        help=(
            "The Excel file must contain a column named "
            "`api_download_url`."
        ),
    )

    if uploaded_download_file is not None:

        uploaded_download_df = pd.read_excel(
            uploaded_download_file
        )

        if "api_download_url" not in uploaded_download_df.columns:

            st.error(
                "The uploaded Excel file must contain "
                "a column named exactly `api_download_url`."
            )

        else:

            (
                download_urls,
                duplicate_download_versions_df,
            ) = prepare_download_urls(
                uploaded_download_df
            )

            if len(download_urls) < 1:
                st.warning(
                    "No valid download URLs found in the uploaded Excel file."
                )
            else:
                st.success(
                    f"{len(download_urls):,} unique mod file(s) loaded."
                )


else:

    session_download_df = st.session_state.get(
        "mod_list_df",
        pd.DataFrame(),
    )

    if session_download_df.empty:

        st.info(
            "Add mods to the compatibility list first."
        )

    elif "api_download_url" not in session_download_df.columns:

        st.warning(
            "The current mod list does not contain "
            "`api_download_url` yet."
        )

    else:

        (
            download_urls,
            duplicate_download_versions_df,
        ) = prepare_download_urls(
            session_download_df
        )

        st.success(
            f"{len(download_urls):,} unique mod file(s) "
            "loaded from the current session."
        )


if not duplicate_download_versions_df.empty:
    duplicate_version_count = (
        duplicate_download_versions_df["version_id"]
        .nunique()
    )

    removed_duplicate_count = (
        len(duplicate_download_versions_df)
        - duplicate_version_count
    )

    st.warning(
        f"Removed {removed_duplicate_count:,} duplicate download row(s) "
        f"across {duplicate_version_count:,} duplicated version ID(s). "
        "Only one file per version ID will be downloaded."
    )

    duplicate_display_columns = [
        column
        for column in [
            "title",
            "version_id",
            "mod_file_name",
            "api_download_url",
        ]
        if column in duplicate_download_versions_df.columns
    ]

    st.dataframe(
        duplicate_download_versions_df[
            duplicate_display_columns
        ],
        hide_index=True,
        use_container_width=True,
    )


if download_urls:

    st.markdown("#### Download Destination")

    download_destination = st.radio(
        "How would you like to save the files?",
        options=[
            "Download ZIP",
            "Save Directly to Folder",
        ],
        horizontal=True,
        key="modrinth_download_destination",
    )


    if download_destination == "Save Directly to Folder":

        download_folder_path = st.text_input(
            "Folder Path",
            placeholder=(
                "/Users/admin/Downloads/minecraft_mods"
            ),
            key="modrinth_download_folder_path",
            help=(
                "Because Streamlit is running locally, "
                "this path points to a folder on your Mac."
            ),
        )

        if st.button(
            "Download Files to Folder",
            type="primary",
            use_container_width=True,
            key="download_modrinth_files_to_folder",
        ):

            if not download_folder_path.strip():

                st.warning(
                    "Enter a folder path first."
                )

            else:

                try:

                    with st.spinner(
                        "Downloading Modrinth files..."
                    ):

                        downloaded_files = (
                            download_files_to_folder(
                                download_urls,
                                download_folder_path,
                            )
                        )

                    st.success(
                        f"Downloaded "
                        f"{len(downloaded_files):,} file(s) to:"
                    )

                    st.code(
                        str(
                            Path(
                                download_folder_path
                            ).expanduser()
                        )
                    )

                except Exception as exc:

                    st.error(
                        f"Download failed: {exc}"
                    )


    else:

        if st.button(
            "Prepare Download",
            type="primary",
            use_container_width=True,
            key="prepare_modrinth_zip_download",
        ):

            try:

                with st.spinner(
                    "Downloading and packaging files..."
                ):

                    st.session_state[
                        "modrinth_download_zip"
                    ] = download_files_to_zip(
                        download_urls
                    ).getvalue()

            except Exception as exc:

                st.error(
                    f"Download failed: {exc}"
                )


        if st.session_state.get(
            "modrinth_download_zip"
        ):

            zip_loader = target_loader or ""
            zip_version = target_version or ""

            st.download_button(
                "Download Mod Files (.zip)",
                data=st.session_state[
                    "modrinth_download_zip"
                ],
                file_name=(
                    f"modrinth_mods_"
                    f"{zip_loader}_"
                    f"{zip_version.replace('.', '_')}_"
                    f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.zip"
                ),
                mime="application/zip",
                use_container_width=True,
                key="download_modrinth_zip_button",
            )
