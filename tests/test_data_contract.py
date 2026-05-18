from __future__ import annotations

from datetime import date
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import (
    AuthConfigError,
    AuthSettings,
    _authenticate_local_user,
    _authorization_check,
    can_export_data,
    make_password_hash,
    resolve_auth_settings,
    verify_password,
)
from charts import combo_line_bar_option, donut_option, horizontal_bar_option
from charts import combo_bar_count_line_option
from data_loader import DataLoadError, _append_ka_segment, _normalize_amount_units, _read_csv_text, validate_project
from exports import (
    activation_internal_export,
    activation_provider_export,
    new_intake_internal_export,
    new_intake_provider_export,
    silent_merchants_internal_export,
    silent_merchants_provider_export,
)
from geo_matching import StreamlitGeoMatcher, append_staging_geo_columns
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
from filters import KA_SCOPE_EXCLUDE, KA_SCOPE_ONLY, apply_ka_scope
from pages_or_modules.new_intake import (
    ONLINE_SCOPE_EXCLUDE,
    _apply_online_scope,
    _apply_zhenxing_scope,
    _default_month_range,
    _filter_month_range,
    _latest_month,
    _month_options,
)
from pages_or_modules.activation_low_activity import (
    _activity_windows,
    _classify_frequency_decline,
    _with_frequency_decline_band,
)
from pages_or_modules.silent_merchants import (
    SILENCE_TIER_ORDER,
    _filter_access_date_range,
    _geo_filter_specs,
)
from scripts.build_private_data_project import _new_intake_source_period, _silent_rows


def test_auth_settings_auto_disabled_without_ldap_config() -> None:
    settings = resolve_auth_settings(secrets={}, environ={})
    assert settings.enabled is False
    assert settings.provider == "local"


def test_auth_settings_auto_enables_with_ldap_and_merges_form_config() -> None:
    settings = resolve_auth_settings(
        secrets={
            "ldap": {
                "server_path": "ldap://ldap.example.com",
                "domain": "example",
                "search_base": "dc=example,dc=com",
                "attributes": ["userPrincipalName", "displayName"],
            },
            "auth": {"allowed_domains": ["@example.com"]},
            "signin_form": {
                "title": {"text": "企业账号登录"},
                "submit": {"label": "进入 BI"},
            },
        },
        environ={},
    )

    assert settings.enabled is True
    assert settings.provider == "ldap"
    assert settings.ldap is not None
    assert settings.signin_form["title"]["text"] == "企业账号登录"
    assert settings.signin_form["username"]["label"] == "账号"
    assert settings.signin_form["submit"]["label"] == "进入 BI"
    assert settings.allowed_domains == ("example.com",)


def test_auth_settings_forced_enabled_requires_ldap_config() -> None:
    try:
        resolve_auth_settings(secrets={"auth": {"enabled": True, "provider": "ldap"}}, environ={})
    except AuthConfigError as exc:
        assert "[ldap]" in str(exc)
    else:
        raise AssertionError("LDAP auth should require the [ldap] secrets section when enabled")


def test_auth_settings_reads_top_level_auth_enabled_secret() -> None:
    settings = resolve_auth_settings(secrets={"AUTH_ENABLED": "false", "ldap": {"server_path": "ldap://x"}}, environ={})
    assert settings.enabled is False
    assert settings.provider == "ldap"


def test_auth_settings_top_level_auth_enabled_overrides_auth_section() -> None:
    settings = resolve_auth_settings(
        secrets={"AUTH_ENABLED": "false", "auth": {"enabled": True}, "ldap": {"server_path": "ldap://x"}},
        environ={},
    )
    assert settings.enabled is False


def test_auth_settings_auto_enables_local_users() -> None:
    password_hash = make_password_hash("secret", salt=b"1234567890abcdef")
    settings = resolve_auth_settings(
        secrets={
            "local_users": {
                "v_kenhzxia@global.tencent.com": {
                    "name": "Ken",
                    "role": "admin",
                    "permissions": ["*"],
                    "password_hash": password_hash,
                }
            }
        },
        environ={},
    )

    assert settings.enabled is True
    assert settings.provider == "local"
    assert settings.local_users["v_kenhzxia@global.tencent.com"]["role"] == "admin"


def test_password_hash_verification() -> None:
    password_hash = make_password_hash("xhz1998", salt=b"1234567890abcdef")
    assert verify_password("xhz1998", password_hash) is True
    assert verify_password("wrong", password_hash) is False
    assert verify_password("xhz1998", "not-a-valid-hash") is False


def test_local_user_authentication_returns_admin_identity() -> None:
    password_hash = make_password_hash("xhz1998", salt=b"1234567890abcdef")
    settings = AuthSettings(
        enabled=True,
        provider="local",
        ldap=None,
        local_users={
            "v_kenhzxia@global.tencent.com": {
                "name": "Ken",
                "role": "admin",
                "permissions": ["*"],
                "password_hash": password_hash,
            }
        },
        session_state_names=None,
        auth_cookie=None,
        encryptor=None,
        signin_form={},
        signout_form={},
        allowed_users=(),
        allowed_domains=(),
    )

    user = _authenticate_local_user(settings, "V_KenHzXia@Global.Tencent.Com", "xhz1998")

    assert user is not None
    assert user["displayName"] == "Ken"
    assert user["role"] == "admin"
    assert user["permissions"] == ["*"]
    assert _authenticate_local_user(settings, "v_kenhzxia@global.tencent.com", "wrong") is None


def test_export_permission_blocks_viewer_and_allows_user() -> None:
    assert can_export_data({"permissions": ["viewer"]}) is False
    assert can_export_data({"permissions": ["user"]}) is True
    assert can_export_data({"permissions": ["*"]}) is True
    assert can_export_data({"permissions": ["viewer", "export"]}) is True


def test_auth_authorization_accepts_allowed_users_and_domains() -> None:
    settings = AuthSettings(
        enabled=True,
        provider="ldap",
        ldap={},
        local_users={},
        session_state_names=None,
        auth_cookie=None,
        encryptor=None,
        signin_form={},
        signout_form={},
        allowed_users=("allowed@example.com",),
        allowed_domains=("partner.example",),
    )
    check_user = _authorization_check(settings)

    assert check_user(None, {"userPrincipalName": "allowed@example.com"}) is True
    assert check_user(None, {"mail": "analyst@partner.example"}) is True
    assert isinstance(check_user(None, {"mail": "blocked@example.com"}), str)


def test_ka_dimension_marks_matching_merchants_and_defaults_smb() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "100", "merchant_short_name": "KA Shop"},
            {"merchant_id": "200", "merchant_short_name": "SMB Shop"},
        ]
    )
    ka_dimension = pd.DataFrame(
        [
            {
                "ka_mid": "100",
                "is_ka": "1",
                "merchant_segment": "KA",
                "country_group": "NZ",
                "ka_group": "Demo Group",
                "ka_brand": "Demo Brand",
                "ka_institution": "Demo PSP",
            }
        ]
    )

    annotated = _append_ka_segment(rows, ka_dimension)

    assert annotated["merchant_segment"].tolist() == ["KA", "SMB"]
    assert annotated["is_ka"].tolist() == [1, 0]
    assert annotated.loc[0, "ka_group"] == "Demo Group"
    assert annotated.loc[1, "ka_group"] == ""


def test_ka_scope_filter_can_keep_or_exclude_ka() -> None:
    rows = pd.DataFrame(
        {
            "merchant_id": ["ka", "smb"],
            "merchant_segment": ["KA", "SMB"],
        }
    )

    only_ka = apply_ka_scope(rows, KA_SCOPE_ONLY)
    excluded = apply_ka_scope(rows, KA_SCOPE_EXCLUDE)

    assert only_ka["merchant_id"].tolist() == ["ka"]
    assert excluded["merchant_id"].tolist() == ["smb"]


def test_manifest_schema_guard_accepts_expected_versions() -> None:
    validate_project(
        {
            "manifest": {
                "project_id": "anz-bi-platform",
                "page_datasets": {
                    "new_intake": {"schema_version": "1.0"},
                    "activation_low_activity": {"schema_version": "1.0"},
                    "silent_merchants": {"schema_version": "1.0"},
                },
            }
        }
    )


def test_manifest_schema_guard_rejects_stale_versions() -> None:
    try:
        validate_project(
            {
                "manifest": {
                    "project_id": "anz-bi-platform",
                    "page_datasets": {
                        "new_intake": {"schema_version": "0.9"},
                        "activation_low_activity": {"schema_version": "1.0"},
                        "silent_merchants": {"schema_version": "1.0"},
                    },
                }
            }
        )
    except DataLoadError as exc:
        assert "new_intake schema version" in str(exc)
    else:
        raise AssertionError("validate_project should reject stale schema versions")


def test_new_intake_source_period_uses_month_distribution() -> None:
    assert _new_intake_source_period({"month_distribution": {"2026.03": 1, "2022.01": 1}}) == "2022.01 to 2026.03"


def test_new_intake_provider_export_excludes_internal_ids() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "456",
                "institution_id": "psp1",
                "intake_month": "2026.03",
                "merchant_short_name": "Demo Shop",
                "institution_standard": "Demo PSP",
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "business_suburb": "CBD",
                "postcode": "1010",
                "geo_area": "Auckland Central",
                "business_cluster": "CBD",
                "active_30d_flag": 1,
                "store_address": "Demo address",
                "mcc_major_industry": "餐饮类",
            }
        ]
    )
    provider = new_intake_provider_export(rows)
    internal = new_intake_internal_export(rows)
    assert "merchant_id" not in provider.columns
    assert "institution_id" not in provider.columns
    assert "机构" not in provider.columns
    assert "国家" not in provider.columns
    assert "地理展示层级" not in provider.columns
    assert "NZ Cluster" not in provider.columns
    assert "州/省" not in provider.columns
    assert provider.columns.tolist() == [
        "商家名",
        "所在城市",
        "Suburb",
        "Postcode",
        "NZ地理片区",
        "接入后30天激活状态",
        "intake_month",
        "详细地址",
        "行业展示",
    ]
    assert "merchant_id" in internal.columns
    assert internal.loc[0, "merchant_id"] == "456"
    assert provider.loc[0, "接入后30天激活状态"] == "已激活"
    assert provider.loc[0, "NZ地理片区"] == "Auckland Central"


def test_activation_provider_export_excludes_internal_ids() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "123",
                "institution_id": "psp2",
                "candidate_rank": 8,
                "merchant_name": "Demo Merchant",
                "scope_country": "NZ",
                "business_city": "Auckland",
                "business_suburb": "CBD",
                "geo_area": "Auckland Central",
                "priority_label": "严重下滑",
                "address": "Demo address",
                "mcc_major_industry": "餐饮类",
            }
        ]
    )
    provider = activation_provider_export(rows)
    internal = activation_internal_export(rows)
    assert "merchant_id" not in provider.columns
    assert "institution_id" not in provider.columns
    assert "candidate_rank" not in provider.columns
    assert "地理展示层级" not in provider.columns
    assert "州/省" not in provider.columns
    assert "服务商跟进级别" in provider.columns
    assert "geo_reporting_level" not in internal.columns
    assert "geo_reporting_level_label" not in internal.columns
    assert "merchant_id" in internal.columns
    assert "candidate_rank" in internal.columns


def test_new_intake_provider_export_uses_au_columns_without_nz_area() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "789",
                "intake_month": "2026.03",
                "merchant_short_name": "Sydney Shop",
                "analysis_country": "AU",
                "state": "NSW",
                "business_city": "Sydney",
                "business_suburb": "Haymarket",
                "postcode": "2000",
                "active_30d_flag": 0,
                "store_address": "Demo address",
                "mcc_major_industry": "餐饮类",
            }
        ]
    )

    provider = new_intake_provider_export(rows)

    assert "州/省" in provider.columns
    assert "NZ地理片区" not in provider.columns
    assert "NZ Cluster" not in provider.columns
    assert provider.loc[0, "州/省"] == "NSW"
    assert provider.loc[0, "接入后30天激活状态"] == "未激活"


def test_activation_provider_export_keeps_mixed_country_specific_columns() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "nz",
                "merchant_name": "NZ Merchant",
                "scope_country": "NZ",
                "business_city": "Auckland",
                "business_suburb": "CBD",
                "geo_area": "Auckland Central",
                "priority_label": "严重下滑",
            },
            {
                "merchant_id": "au",
                "merchant_name": "AU Merchant",
                "scope_country": "AU",
                "state": "NSW",
                "business_city": "Sydney",
                "business_suburb": "Haymarket",
                "priority_label": "明显下滑",
            },
        ]
    )

    provider = activation_provider_export(rows)

    assert "地理展示层级" not in provider.columns
    assert "州/省" in provider.columns
    assert "NZ地理片区" in provider.columns
    assert provider.loc[0, "NZ地理片区"] == "Auckland Central"
    assert provider.loc[1, "州/省"] == "NSW"


def test_silent_provider_export_excludes_internal_ids_and_uses_english_headers() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "823448011",
                "institution_id": "739553423",
                "merchant_display_name": "Demo Merchant",
                "institution_name": "Demo PSP",
                "country_group": "AU",
                "merchant_country_code": "036",
                "state": "VIC",
                "business_city": "Melbourne",
                "business_suburb": "Syndal",
                "postcode": "3149",
                "silence_tier": "new_unactivated_180d",
                "access_age_band": "access_180_359d",
                "merchant_access_time": "2025-10-31 18:19:08",
                "business_type": "OFFLINE",
                "address": "Unit 902/108 Queens Rd",
                "mcc_code": "0744",
            }
        ]
    )

    provider = silent_merchants_provider_export(rows)
    internal = silent_merchants_internal_export(rows)

    assert "merchant_id" not in provider.columns
    assert "institution_id" not in provider.columns
    assert provider.columns.tolist() == [
        "Merchant Name",
        "Country",
        "State",
        "City",
        "Suburb",
        "Postcode",
        "Geo Reporting Name",
        "Silence Tier",
        "Access Age Band",
        "Access Time",
        "Business Type",
        "Address",
        "MCC Code",
    ]
    assert provider.loc[0, "Silence Tier"] == "New unactivated after 180 days"
    assert "merchant_id" in internal.columns
    assert "institution_id" in internal.columns
    assert internal.loc[0, "merchant_id"] == "823448011"


def test_silent_rows_preserve_ids_and_copy_stores_address_for_geo_matching() -> None:
    raw = pd.DataFrame(
        [
            {
                "snapshot_ds": 20260501,
                "country_group": "NZ",
                "merchant_country_code": 554,
                "merchant_id": 456789123,
                "merchant_display_name": "Demo Store",
                "institution_id": 123456,
                "mcc_code": 5812,
                "stores_address": "1 Queen Street\u00a0Auckland 1010",
                "silence_tier": "deep_silent",
            }
        ]
    )

    rows = _silent_rows(raw)
    matcher = StreamlitGeoMatcher.from_frames(
        nz=pd.DataFrame(
            [
                {
                    "Country": "NZ",
                    "City": "Auckland",
                    "geo_area": "Central Auckland",
                    "Suburb": "Auckland Central",
                    "Postcode": "1010",
                    "business_cluster": "CBD",
                }
            ]
        ),
        au=pd.DataFrame([{"Country": "AU", "State": "NSW", "City": "Sydney", "Suburb": "Haymarket", "Postcode": "2000"}]),
    )
    staged = append_staging_geo_columns(rows, matcher)

    assert rows.loc[0, "merchant_id"] == "456789123"
    assert rows.loc[0, "institution_id"] == "123456"
    assert rows.loc[0, "mcc_code"] == "5812"
    assert "\u00a0" not in rows.loc[0, "address"]
    assert rows.loc[0, "address"] == "1 Queen Street Auckland 1010"
    assert staged.loc[0, "staging_city"] == "Auckland"
    assert staged.loc[0, "staging_geo_area"] == "Central Auckland"


def test_silent_page_helpers_sort_filter_and_keep_country_aware_geo_specs() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "old", "merchant_access_time": "2025-05-01 10:00:00", "silence_tier": "deep_silent"},
            {"merchant_id": "mid", "merchant_access_time": "2025-10-01 10:00:00", "silence_tier": "initial_silent"},
            {"merchant_id": "new", "merchant_access_time": "2025-10-31 10:00:00", "silence_tier": "new_unactivated_180d"},
        ]
    )

    filtered = _filter_access_date_range(rows, date(2025, 10, 1), date(2025, 10, 31))

    assert SILENCE_TIER_ORDER == ["new_unactivated_180d", "initial_silent", "deep_silent"]
    assert filtered["merchant_id"].tolist() == ["mid", "new"]
    assert [spec.column for spec in _geo_filter_specs("AU")] == ["geo_state", "geo_city", "geo_suburb", "geo_postcode"]
    assert [spec.column for spec in _geo_filter_specs("NZ")] == [
        "geo_city",
        "nz_geo_area",
        "nz_business_cluster",
        "geo_suburb",
    ]


def test_amount_columns_are_scaled_from_minor_units() -> None:
    rows = pd.DataFrame(
        [
            {
                "txn_amount_30d": 12345,
                "trade_amt_prev_1m": 250,
                "txn_count_30d": 7,
                "merchant_id": "m1",
            }
        ]
    )

    normalized = _normalize_amount_units(rows, "minor")

    assert normalized.loc[0, "txn_amount_30d"] == 123.45
    assert normalized.loc[0, "trade_amt_prev_1m"] == 2.5
    assert normalized.loc[0, "txn_count_30d"] == 7
    assert normalized.loc[0, "merchant_id"] == "m1"


def test_csv_reader_preserves_intake_month_labels() -> None:
    rows = _read_csv_text("intake_month,txn_amount_30d\n2025.10,100\n")
    assert rows.loc[0, "intake_month"] == "2025.10"


def test_new_intake_default_month_range_uses_latest_six_calendar_months() -> None:
    rows = pd.DataFrame(
        {
            "intake_month": [
                "2025.08",
                "2025.09",
                "2025.10",
                "2025.11",
                "2025.12",
                "2026.01",
                "2026.02",
                "2026.03",
            ],
            "merchant_id": list(range(8)),
        }
    )

    months = _month_options(rows)
    assert _default_month_range(months) == ("2025.10", "2026.03")
    assert _latest_month(rows) == "2026.03"

    filtered = _filter_month_range(rows, "2025.10", "2026.03")
    assert filtered["intake_month"].tolist() == ["2025.10", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"]


def test_new_intake_month_options_recover_legacy_october_label() -> None:
    rows = pd.DataFrame(
        {
            "intake_month": ["2025.09", "2025.1", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"],
            "merchant_id": list(range(7)),
        }
    )

    months = _month_options(rows)
    assert "2025.10" in months
    assert "2025.1" not in months
    assert _default_month_range(months) == ("2025.10", "2026.03")

    filtered = _filter_month_range(rows, "2025.10", "2026.03")
    assert filtered["intake_month"].tolist() == ["2025.1", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"]


def test_new_intake_default_scope_excludes_online_and_zhenxing() -> None:
    rows = pd.DataFrame(
        {
            "merchant_id": ["offline", "online", "zhenxing"],
            "channel_type": ["OFFLINE", "ONLINE", "BOTH"],
            "is_zhenxing": ["0", "0", "1"],
        }
    )

    scoped = _apply_zhenxing_scope(_apply_online_scope(rows, ONLINE_SCOPE_EXCLUDE), "排除圳兴")

    assert scoped["merchant_id"].tolist() == ["offline"]


def test_activation_monitoring_uses_q1_frequency_decline_bands() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "stable", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 80},
            {"merchant_id": "medium", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 60},
            {"merchant_id": "high", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 20},
            {"merchant_id": "severe", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 0},
        ]
    )

    monitored = _with_frequency_decline_band(rows)

    assert monitored["decay_band"].tolist() == ["stable", "medium", "high", "severe"]
    assert monitored["eligible_low_activity_flag"].tolist() == [True, True, True, True]
    assert _classify_frequency_decline(jan=0, feb=100, mar=0) == ("stable", 0.0)


def test_activation_activity_windows_are_q1_frequency_in_calendar_order() -> None:
    rows = pd.DataFrame(
        [
            {"trade_cnt_prev_1m": 10, "trade_cnt_prev_2m": 20, "trade_cnt_prev_3m": 30},
            {"trade_cnt_prev_1m": 1, "trade_cnt_prev_2m": 2, "trade_cnt_prev_3m": 3},
        ]
    )

    windows = _activity_windows(rows)

    assert windows["window"].tolist() == ["2026.1", "2026.2", "2026.3"]
    assert windows["txn_count"].tolist() == [33, 22, 11]
    assert windows["active_merchant_count"].tolist() == [2, 2, 2]


def test_activation_combo_chart_uses_bar_and_line_axes() -> None:
    rows = pd.DataFrame(
        [
            {"window": "2026.1", "txn_count": 230008, "active_merchant_count": 5000},
            {"window": "2026.2", "txn_count": 275000, "active_merchant_count": 4259},
        ]
    )

    option = combo_bar_count_line_option(
        rows,
        x="window",
        bar_y="txn_count",
        line_y="active_merchant_count",
        title="2026 Q1",
        bar_name="交易频次",
        line_name="活跃商户数",
    )

    assert option["series"][0]["type"] == "bar"
    assert option["series"][1]["type"] == "line"
    assert option["series"][1]["yAxisIndex"] == 1


def test_reporting_geography_keeps_country_specific_levels() -> None:
    rows = pd.DataFrame(
        [
            {
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "business_suburb": "Albany",
                "geo_area": "North Shore",
                "business_cluster": "Albany Cluster",
                "staging_city": "Auckland",
                "staging_geo_area": "Central Auckland",
                "staging_business_cluster": "Reviewed Cluster",
            },
            {
                "analysis_country": "AU",
                "state": "NSW",
                "business_city": "Sydney",
                "business_suburb": "Haymarket",
                "staging_city": "Sydney",
                "geo_area": "Should not be AU geo area",
                "business_cluster": "Should not be AU cluster",
            },
            {
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "geo_area": "Legacy Auckland Area",
                "staging_city": "",
                "staging_geo_area": "",
            },
        ]
    )

    bridged = with_reporting_geography(rows, country_columns="analysis_country")

    assert bridged.loc[0, "geo_reporting_level"] == "nz_geo_area"
    assert bridged.loc[0, "geo_reporting_name"] == "Central Auckland"
    assert bridged.loc[0, "nz_business_cluster"] == "Reviewed Cluster"
    assert bridged.loc[1, "geo_reporting_level"] == "au_city"
    assert bridged.loc[1, "geo_reporting_name"] == "Sydney"
    assert bridged.loc[1, "nz_geo_area"] == ""
    assert bridged.loc[1, "nz_business_cluster"] == ""
    assert bridged.loc[2, "nz_geo_area"] == ""
    assert bridged.loc[2, "geo_city"] == ""
    assert country_scope(bridged.iloc[[0]]) == "NZ"
    assert [spec.column for spec in sidebar_geo_filter_specs("AU")] == [
        "geo_state",
        "geo_city",
        "geo_suburb",
        "geo_postcode",
    ]


def test_geo_matcher_can_use_private_repo_frames() -> None:
    rows = pd.DataFrame(
        [
            {
                "analysis_country": "NZ",
                "merchant_short_name": "Demo",
                "store_address": "1 Queen Street, Auckland 1010",
            }
        ]
    )
    matcher = StreamlitGeoMatcher.from_frames(
        nz=pd.DataFrame(
            [
                {
                    "Country": "NZ",
                    "City": "Auckland",
                    "geo_area": "Central Auckland",
                    "Suburb": "Auckland Central",
                    "Postcode": "1010",
                    "business_cluster": "CBD",
                }
            ]
        ),
        au=pd.DataFrame([{"Country": "AU", "State": "NSW", "City": "Sydney", "Suburb": "Haymarket", "Postcode": "2000"}]),
    )
    staged = append_staging_geo_columns(rows, matcher)
    assert staged.loc[0, "staging_geo_area"] == "Central Auckland"
    assert staged.loc[0, "staging_business_cluster"] == "CBD"


def test_echarts_option_builders_return_core_shapes() -> None:
    trend = pd.DataFrame([{"month": "2026.03", "count": 10, "rate": 0.4}])
    combo = combo_line_bar_option(
        trend,
        x="month",
        bar_y="count",
        line_y="rate",
        title="Trend",
        bar_name="Count",
        line_name="Rate",
    )
    assert combo["series"][0]["type"] == "bar"
    assert combo["series"][1]["type"] == "line"

    dist = pd.DataFrame([{"label": "NZ", "count": 3}])
    donut = donut_option(dist, label="label", value="count", title="Country")
    assert donut["series"][0]["type"] == "pie"

    rank = horizontal_bar_option(dist, label="label", value="count", title="Rank")
    assert rank["series"][0]["type"] == "bar"
