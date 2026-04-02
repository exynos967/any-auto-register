"""通过 kiro.rs Admin API 自动导入 Kiro 凭据。"""

from __future__ import annotations

import json
import logging
from typing import Any, Tuple
from urllib import error, request

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-east-1"


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store

        return str(config_store.get(key, "") or "").strip()
    except Exception:
        return ""


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _canonical_auth_method(
    value: str | None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    method = str(value or "").strip().lower()
    if method in {"builder-id", "builderid", "iam", "idc"}:
        return "idc"
    if method == "social":
        return "social"
    if _clean_optional(client_id) or _clean_optional(client_secret):
        return "idc"
    return "social"


def resolve_kiro_rs_admin_url(url: str | None = None) -> str:
    raw = str(url or _get_config_value("kiro_rs_admin_url") or "").strip()
    if not raw:
        return ""

    normalized = raw.rstrip("/")
    if normalized.endswith("/api/admin/credentials"):
        return normalized
    if normalized.endswith("/api/admin"):
        return f"{normalized}/credentials"
    return f"{normalized}/api/admin/credentials"


def resolve_kiro_rs_admin_key(api_key: str | None = None) -> str:
    return str(api_key or _get_config_value("kiro_rs_admin_key") or "").strip()


def is_kiro_rs_configured(
    admin_url: str | None = None,
    admin_key: str | None = None,
) -> bool:
    return bool(
        resolve_kiro_rs_admin_url(admin_url)
        and resolve_kiro_rs_admin_key(admin_key)
    )


def build_kiro_rs_credential_document(account) -> dict[str, Any]:
    extra = getattr(account, "extra", {}) or {}

    refresh_token = _clean_optional(
        extra.get("refreshToken") or extra.get("refresh_token")
    )
    if not refresh_token:
        raise ValueError("账号缺少 refreshToken")

    client_id = _clean_optional(extra.get("clientId") or extra.get("client_id"))
    client_secret = _clean_optional(
        extra.get("clientSecret") or extra.get("client_secret")
    )
    access_token = _clean_optional(
        extra.get("accessToken")
        or extra.get("access_token")
        or getattr(account, "token", "")
    )
    expires_at = _clean_optional(extra.get("expiresAt") or extra.get("expires_at"))
    auth_method = _canonical_auth_method(
        extra.get("authMethod") or extra.get("auth_method"),
        client_id=client_id,
        client_secret=client_secret,
    )
    region = _clean_optional(extra.get("region")) or DEFAULT_REGION
    email = _clean_optional(getattr(account, "email", "") or extra.get("email"))

    document = {
        "refreshToken": refresh_token,
        "authMethod": auth_method,
        "region": region,
    }
    optional_fields = {
        "accessToken": access_token,
        "expiresAt": expires_at,
        "clientId": client_id,
        "clientSecret": client_secret,
        "authRegion": _clean_optional(
            extra.get("authRegion") or extra.get("auth_region")
        ),
        "apiRegion": _clean_optional(extra.get("apiRegion") or extra.get("api_region")),
        "machineId": _clean_optional(
            extra.get("machineId") or extra.get("machine_id")
        ),
        "email": email,
        "proxyUrl": _clean_optional(extra.get("proxyUrl") or extra.get("proxy_url")),
        "proxyUsername": _clean_optional(
            extra.get("proxyUsername") or extra.get("proxy_username")
        ),
        "proxyPassword": _clean_optional(
            extra.get("proxyPassword") or extra.get("proxy_password")
        ),
    }
    for key, value in optional_fields.items():
        if value:
            document[key] = value
    return document


def build_kiro_rs_admin_payload(account) -> dict[str, Any]:
    document = build_kiro_rs_credential_document(account)
    payload = {
        "refreshToken": document["refreshToken"],
        "authMethod": document["authMethod"],
        "priority": 0,
    }
    for key in (
        "clientId",
        "clientSecret",
        "region",
        "authRegion",
        "apiRegion",
        "machineId",
        "email",
        "proxyUrl",
        "proxyUsername",
        "proxyPassword",
    ):
        value = document.get(key)
        if value:
            payload[key] = value
    return payload


def _response_message(body: str, status_code: int) -> str:
    try:
        data = json.loads(body)
    except ValueError:
        return body[:200].strip() or f"HTTP {status_code}"

    if isinstance(data, dict):
        error_data = data.get("error")
        if isinstance(error_data, dict):
            message = _clean_optional(
                error_data.get("message")
                or error_data.get("msg")
                or error_data.get("detail")
            )
            if message:
                return message
        for key in ("message", "msg", "detail", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return body[:200].strip() or f"HTTP {status_code}"


def _is_duplicate_message(message: str) -> bool:
    text = str(message or "").lower()
    return "凭据已存在" in text or "refreshtoken 重复" in text or "duplicate" in text


def upload_to_kiro_rs(
    account,
    admin_url: str | None = None,
    admin_key: str | None = None,
) -> Tuple[bool, str]:
    endpoint = resolve_kiro_rs_admin_url(admin_url)
    api_key = resolve_kiro_rs_admin_key(admin_key)

    if not endpoint:
        return False, "kiro.rs Admin URL 未配置"
    if not api_key:
        return False, "kiro.rs Admin API Key 未配置"

    payload = build_kiro_rs_admin_payload(account)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "x-api-key": api_key,
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status_code = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except error.URLError as exc:
        logger.error("kiro.rs Admin API 请求异常: %s", exc)
        return False, f"请求异常: {exc.reason or exc}"
    except Exception as exc:
        logger.error("kiro.rs Admin API 请求异常: %s", exc)
        return False, f"请求异常: {exc}"

    if status_code in (200, 201):
        return True, "上传成功"

    message = _response_message(body, status_code)
    if _is_duplicate_message(message):
        return True, f"已存在: {message}"
    return False, f"上传失败: HTTP {status_code} - {message}"
