from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets as py_secrets
from dataclasses import dataclass
from typing import Any, Mapping

import streamlit as st


TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "n", "off", "disabled"}
AUTH_PROVIDERS = {"local", "ldap"}
LOCAL_USER_SESSION_KEY = "anz_bi_local_user"
CURRENT_USER_SESSION_KEY = "anz_bi_current_user"
EXPORT_PERMISSIONS = {"*", "admin", "user", "export", "download", "can_export"}
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000

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
    provider: str
    ldap: dict[str, Any] | None
    local_users: dict[str, dict[str, Any]]
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

    if settings.provider == "local":
        return _require_local_login(settings)
    if settings.provider != "ldap":
        st.error(f"不支持的登录方式：{settings.provider}")
        st.stop()

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
    st.session_state[CURRENT_USER_SESSION_KEY] = user

    with st.sidebar:
        authenticator.createLogoutForm(_logout_form_config(user, settings.signout_form), callback=_clear_current_user)
    return user


def current_user() -> dict[str, Any] | None:
    user = st.session_state.get(CURRENT_USER_SESSION_KEY)
    if isinstance(user, dict):
        return user
    user = st.session_state.get(LOCAL_USER_SESSION_KEY)
    return user if isinstance(user, dict) else None


def can_export_data(user: Mapping[str, Any] | None = None) -> bool:
    if user is None:
        user = current_user()
    if user is None:
        return True
    permissions = _permission_set(user)
    if not permissions:
        return True
    return bool(permissions.intersection(EXPORT_PERMISSIONS))


def render_export_restricted_notice() -> None:
    st.info("当前账号为 viewer 权限，可查看页面数据，但不能导出清单。")


def resolve_auth_settings(
    secrets: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> AuthSettings:
    raw_secrets = _secrets_mapping(secrets)
    env = os.environ if environ is None else environ
    auth = _section(raw_secrets, "auth")
    ldap = _section(raw_secrets, "ldap")
    local_users = _local_users(_section(raw_secrets, "local_users"))
    secret_enabled = _secret_value(raw_secrets, "AUTH_ENABLED")
    if secret_enabled is None:
        secret_enabled = auth.get("enabled")
    secret_provider = _secret_value(raw_secrets, "AUTH_PROVIDER")
    if secret_provider is None:
        secret_provider = auth.get("provider")

    provider = _resolve_auth_provider(
        secret_provider,
        env.get("AUTH_PROVIDER"),
        ldap_present=bool(ldap),
        local_present=bool(local_users),
    )
    enabled = _resolve_auth_enabled(
        secret_enabled,
        env.get("AUTH_ENABLED"),
        provider=provider,
        ldap_present=bool(ldap),
        local_present=bool(local_users),
    )
    signin_form = _deep_merge(DEFAULT_SIGNIN_FORM, _section(raw_secrets, "signin_form"))
    signout_form = _deep_merge(DEFAULT_SIGNOUT_FORM, _section(raw_secrets, "signout_form"))
    settings = AuthSettings(
        enabled=enabled,
        provider=provider,
        ldap=ldap or None,
        local_users=local_users,
        session_state_names=_section(raw_secrets, "session_state_names") or None,
        auth_cookie=_section(raw_secrets, "auth_cookie") or None,
        encryptor=_section(raw_secrets, "encryptor") or None,
        signin_form=signin_form,
        signout_form=signout_form,
        allowed_users=_normalized_values(auth.get("allowed_users"), env.get("AUTH_ALLOWED_USERS")),
        allowed_domains=_normalized_domains(auth.get("allowed_domains"), env.get("AUTH_ALLOWED_DOMAINS")),
    )
    if settings.enabled and settings.provider == "ldap" and not settings.ldap:
        raise AuthConfigError("启用 LDAP 登录时必须配置 `[ldap]` secrets。")
    if settings.enabled and settings.provider == "local" and not settings.local_users:
        raise AuthConfigError("启用本地账号登录时必须配置 `[local_users]` secrets。")
    return settings


def make_password_hash(password: str, *, salt: bytes | None = None, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    if salt is None:
        salt = py_secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = str(encoded_hash).split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _require_local_login(settings: AuthSettings) -> dict[str, Any]:
    current_user = st.session_state.get(LOCAL_USER_SESSION_KEY)
    if isinstance(current_user, dict):
        st.session_state[CURRENT_USER_SESSION_KEY] = current_user
        _render_local_logout(current_user, settings)
        return current_user

    title = _form_text(settings.signin_form, ("title", "text"), "ANZ BI 登录")
    username_label = _form_text(settings.signin_form, ("username", "label"), "账号")
    username_placeholder = _form_text(settings.signin_form, ("username", "placeholder"), "邮箱")
    password_label = _form_text(settings.signin_form, ("password", "label"), "密码")
    password_placeholder = _form_text(settings.signin_form, ("password", "placeholder"), "请输入密码")
    submit_label = _form_text(settings.signin_form, ("submit", "label"), "登录")

    st.subheader(title)
    with st.form("anz_bi_local_login_form"):
        username = st.text_input(username_label, placeholder=username_placeholder)
        password = st.text_input(password_label, placeholder=password_placeholder, type="password")
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    if submitted:
        user = _authenticate_local_user(settings, username, password)
        if user is None:
            st.error("账号或密码不正确。")
        else:
            st.session_state[LOCAL_USER_SESSION_KEY] = user
            st.session_state[CURRENT_USER_SESSION_KEY] = user
            st.rerun()
    st.stop()


def _authenticate_local_user(settings: AuthSettings, username: str, password: str) -> dict[str, Any] | None:
    normalized_username = str(username or "").strip().casefold()
    if not normalized_username or not password:
        return None
    user_config = settings.local_users.get(normalized_username)
    if not user_config:
        return None
    password_hash = str(user_config.get("password_hash") or "")
    if not verify_password(password, password_hash):
        return None
    user = _local_user_info(normalized_username, user_config)
    result = _authorization_check(settings)(None, user)
    return user if result is True else None


def _local_user_info(username: str, user_config: Mapping[str, Any]) -> dict[str, Any]:
    name = str(user_config.get("name") or username).strip()
    role = str(user_config.get("role") or "viewer").strip().lower()
    permissions = user_config.get("permissions") or []
    if isinstance(permissions, str):
        permissions = [permissions]
    return {
        "auth_provider": "local",
        "userPrincipalName": username,
        "mail": username,
        "displayName": name,
        "role": role,
        "permissions": [str(permission) for permission in permissions],
    }


def _render_local_logout(user: Mapping[str, Any], settings: AuthSettings) -> None:
    label = _form_text(settings.signout_form, ("submit", "label"), "退出登录")
    display_name = _display_name(user)
    role = str(user.get("role") or "").strip()
    role_suffix = f" / {role}" if role else ""
    with st.sidebar:
        st.caption(f"已登录：{display_name}{role_suffix}")
        if st.button(label, key="anz_bi_local_logout", use_container_width=True):
            st.session_state.pop(LOCAL_USER_SESSION_KEY, None)
            st.session_state.pop(CURRENT_USER_SESSION_KEY, None)
            st.rerun()


def _clear_current_user(_event: Any) -> None:
    st.session_state.pop(CURRENT_USER_SESSION_KEY, None)


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


def _permission_set(user: Mapping[str, Any]) -> set[str]:
    raw = user.get("permissions") or []
    if isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = [raw]
    return {str(value).strip().casefold() for value in values if str(value).strip()}


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


def _resolve_auth_provider(
    secret_value: Any,
    env_value: str | None,
    *,
    ldap_present: bool,
    local_present: bool,
) -> str:
    for value in (env_value, secret_value):
        if value is None or str(value).strip() == "":
            continue
        normalized = str(value).strip().casefold()
        if normalized == "auto":
            break
        if normalized in AUTH_PROVIDERS:
            return normalized
        raise AuthConfigError(f"AUTH_PROVIDER/`[auth].provider` 值无效：{value!r}")
    if local_present:
        return "local"
    if ldap_present:
        return "ldap"
    return "local"


def _resolve_auth_enabled(
    secret_value: Any,
    env_value: str | None,
    *,
    provider: str,
    ldap_present: bool,
    local_present: bool,
) -> bool:
    for value in (env_value, secret_value):
        if value is None or str(value).strip() == "":
            continue
        normalized = str(value).strip().casefold()
        if normalized == "auto":
            return local_present if provider == "local" else ldap_present
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        raise AuthConfigError(f"AUTH_ENABLED/`[auth].enabled` 值无效：{value!r}")
    return local_present if provider == "local" else ldap_present


def _local_users(section: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for username, raw_config in section.items():
        normalized_username = str(username or "").strip().casefold()
        if not normalized_username:
            continue
        if hasattr(raw_config, "to_dict"):
            config = dict(raw_config.to_dict())
        elif isinstance(raw_config, Mapping):
            config = dict(raw_config)
        else:
            raise AuthConfigError(f"本地账号 {username!r} 配置必须是 TOML table。")
        if not str(config.get("password_hash") or "").strip():
            raise AuthConfigError(f"本地账号 {username!r} 缺少 password_hash。")
        users[normalized_username] = config
    return users


def _form_text(config: Mapping[str, Any], path: tuple[str, ...], default: str) -> str:
    value: Any = config
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return default
        value = value[key]
    return str(value or default)


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
