"""Kiro 外部系统同步。"""

from __future__ import annotations

from typing import Any


def sync_account(account) -> list[dict[str, Any]]:
    """同步 Kiro 外部集成，未配置的目标会自动跳过。"""
    from core.config_store import config_store
    from platforms.kiro.kiro_rs_upload import (
        is_kiro_rs_configured,
        upload_to_kiro_rs,
    )

    if getattr(account, "platform", "") != "kiro":
        return []

    from platforms.kiro.account_manager_upload import (
        resolve_manager_path,
        upload_to_kiro_manager,
    )

    results: list[dict[str, Any]] = []
    configured_path = str(config_store.get("kiro_manager_path", "") or "").strip()
    target_path = resolve_manager_path(configured_path or None)
    if configured_path or target_path.parent.exists() or target_path.exists():
        try:
            ok, msg = upload_to_kiro_manager(account, path=configured_path or None)
        except Exception as exc:
            ok, msg = False, f"导入异常: {exc}"
        results.append({"name": "Kiro Manager", "ok": ok, "msg": msg})

    if is_kiro_rs_configured():
        try:
            ok, msg = upload_to_kiro_rs(account)
        except Exception as exc:
            ok, msg = False, f"导入异常: {exc}"
        results.append({"name": "kiro.rs", "ok": ok, "msg": msg})
    return results
