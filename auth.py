from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

import streamlit as st


TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "n", "off", "disabled"}

DEFAULT_SIGNIN_FORM = {
    "maxWidth": 460,
    "align": "center",
    "title": {"text": "ANZ BI 登录", "size": "large", "align": "center"},
    "username": {
        "label": "账号",
        "placeholder": "邮箱或域账号",
        "required": {"required": True, "message": "请输入账号"},
    },
    "password": {
        "label": "密码",
        "placeholder": "请输入密码",
        "required": {"required": True, "message": "请输入密码"},
    },
    "remember": {"label": "保持登录"},
    "submit": {"label": "登录"},
    "busy_message": "正在验证账号...",
}

DEFAULT_SIGNOUT_FORM = {
    "formType": "inline",
    "align": "right",
    "submit": {"label": "退出登录"},
    "busy_message": "正在退出...",
    "sleep_sec": 0.2,
}


class AuthConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    ldap: dict[str, Any] | None
    session_state_names: dict[str, Any] | None
    auth_cookie: dict[str, Any] | None
    encryptor: dict[str, Any] | None
    signin_form: dict[str, Any]
    signout_form: dict[str, Any]
    allowed_users: tuple[str, ...]
    allowed_domains: tuple[str, ...]


def require_login() -> dict[str, Any] | None:
    settings = resolve_auth_settings()
    if not settings.enabled:
        return None

    try:
        from streamlit_ldap_authenticator import Authenticate
    except ImportError as exc:
        st.error(
            "已启用 LDAP 登录，但当前环境缺少 `streamlit-ldap-authenticator`。"
            "请先安装 requirements.txt 中的依赖。"
        )
        st.stop()
        raise exc

    try:
        authenticator = Authenticate(
            settings.ldap,
            settings.session_state_names,
            settings.auth_cookie,
            settings.encryptor,
        )
    except Exception as exc:
        st.error(f"LDAP 登录配置无效：{exc}")
        st.stop()
        raise exc

    user = authenticator.login(
        additionalCheck=_authorization_check(settings),
        config=settings.signin_form,
    )
    if user is None:
        st.stop()

    with st.sidebar:
        authenticator.createLogoutForm(_logout_form_config(user, settings.signout_form))
    return user


def resolve_auth_settings(
    secrets: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> AuthSettings:
    raw_secrets = _secrets_mapping(secrets)
    env = os.environ if environ is None else environ
    auth = _section(raw_secrets, "auth")
    ldap = _section(raw_secrets, "ldap")
    secret_enabled = _secret_value(raw_secrets, "AUTH_ENABLED")
    if secret_enabled is None:
        secret_enabled = auth.get("enabled")

    enabled = _resolve_auth_enabled(secret_enabled, env.get("AUTH_ENABLED"), ldap_present=bool(ldap))
    signin_form = _deep_merge(DEFAULT_SIGNIN_FORM, _section(raw_secrets, "signin_form"))
    signout_form = _deep_merge(DEFAULT_SIGNOUT_FORM, _section(raw_secrets, "signout_form"))
    settings = AuthSettings(
        enabled=enabled,
        ldap=ldap or None,
        session_state_names=_section(raw_secrets, "session_state_names") or None,
        auth_cookie=_section(raw_secrets, "auth_cookie") or None,
        encryptor=_section(raw_secrets, "encryptor") or None,
        signin_form=signin_form,
        signout_form=signout_form,
        allowed_users=_normalized_values(auth.get("allowed_users"), env.get("AUTH_ALLOWED_USERS")),
        allowed_domains=_normalized_domains(auth.get("allowed_domains"), env.get("AUTH_ALLOWED_DOMAINS")),
    )
    if settings.enabled and not settings.ldap:
        raise AuthConfigError("启用 LDAP 登录时必须配置 `[ldap]` secrets。")
    return settings


def _authorization_check(settings: AuthSettings):
    def check_user(_conn: Any, user: dict[str, Any]) -> bool | str:
        allowed_users = {value.casefold() for value in settings.allowed_users}
        allowed_domains = {value.casefold() for value in settings.allowed_domains}
        if not allowed_users and not allowed_domains:
            return True

        identifiers = _user_identifiers(user)
        if allowed_users and any(value.casefold() in allowed_users for value in identifiers):
            return True

        domains = {_domain_from_identifier(value).casefold() for value in identifiers}
        domains.discard("")
        if allowed_domains and domains.intersection(allowed_domains):
            return True

        return "当前账号未被授权访问 ANZ BI 门户。"

    return check_user


def _logout_form_config(user: Mapping[str, Any], base_config: Mapping[str, Any]) -> dict[str, Any]:
    display_name = _display_name(user)
    title = {"title": {"text": f"已登录：{display_name}", "size": "small"}}
    return _deep_merge(title, base_config)


def _display_name(user: Mapping[str, Any]) -> str:
    for key in ("displayName", "cn", "mail", "userPrincipalName", "sAMAccountName"):
        value = str(user.get(key) or "").strip()
        if value:
            return value
    return "已认证用户"


def _user_identifiers(user: Mapping[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for key in ("userPrincipalName", "mail", "sAMAccountName", "displayName"):
        value = str(user.get(key) or "").strip()
        if value:
            identifiers.add(value)
    return identifiers


def _domain_from_identifier(value: str) -> str:
    text = str(value or "").strip()
    if "@" in text:
        return text.rsplit("@", 1)[1]
    if "\\" in text:
        return text.split("\\", 1)[0]
    return ""


def _resolve_auth_enabled(secret_value: Any, env_value: str | None, *, ldap_present: bool) -> bool:
    for value in (env_value, secret_value):
        if value is None or str(value).strip() == "":
            continue
        normalized = str(value).strip().casefold()
        if normalized == "auto":
            return ldap_present
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        raise AuthConfigError(f"AUTH_ENABLED/`[auth].enabled` 值无效：{value!r}")
    return ldap_present


def _normalized_values(secret_value: Any, env_value: str | None = None) -> tuple[str, ...]:
    values: list[str] = []
    for raw in (secret_value, env_value):
        if raw is None:
            continue
        if isinstance(raw, str):
            candidates = raw.split(",")
        elif isinstance(raw, (list, tuple, set)):
            candidates = list(raw)
        else:
            candidates = [raw]
        values.extend(str(value).strip() for value in candidates)
    return tuple(value for value in values if value)


def _normalized_domains(secret_value: Any, env_value: str | None = None) -> tuple[str, ...]:
    values = []
    for value in _normalized_values(secret_value, env_value):
        value = value.casefold()
        if value.startswith("@"):
            value = value[1:]
        if value:
            values.append(value)
    return tuple(values)


def _secrets_mapping(secrets: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    if secrets is not None:
        return secrets
    try:
        return st.secrets
    except Exception:
        return {}


def _section(secrets: Mapping[str, Any], name: str) -> dict[str, Any]:
    try:
        section = secrets.get(name)  # type: ignore[union-attr]
    except Exception:
        return {}
    if section is None:
        return {}
    if hasattr(section, "to_dict"):
        return dict(section.to_dict())
    if isinstance(section, Mapping):
        return dict(section)
    return {}


def _secret_value(secrets: Mapping[str, Any], name: str) -> Any:
    try:
        return secrets.get(name)  # type: ignore[union-attr]
    except Exception:
        return None


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged
