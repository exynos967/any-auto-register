"""Kiro Manager 插件拉取 / 启停管理。"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parents[2]
_EXT_ROOT = _ROOT / "_ext_targets"
_LOG_ROOT = Path(__file__).resolve().parent / "external_logs"
_LOG_ROOT.mkdir(parents=True, exist_ok=True)

_REMOTE_URLS = {
    "kiro-manager": "https://github.com/hj01857655/kiro-account-manager.git",
}

_KIRO_MANAGER_MSI_URL = (
    "https://github.com/hj01857655/kiro-account-manager/releases/download/"
    "v1.8.3/KiroAccountManager_1.8.3_x64_zh-CN.msi"
)
_KIRO_MANAGER_MSI = _EXT_ROOT / "KiroAccountManager_1.8.3_x64_zh-CN.msi"
_KIRO_MANAGER_EXTRACT_DIR = _EXT_ROOT / "kiro-manager-msi-extract"
_KIRO_MANAGER_EXTRACT_EXE = (
    _KIRO_MANAGER_EXTRACT_DIR / "PFiles" / "KiroAccountManager" / "kiro-account-manager.exe"
)

_SERVICE_META = {
    "kiro-manager": {
        "label": "Kiro Account Manager",
        "repo_name": "kiro-account-manager",
        "url": "",
        "health": "",
        "kind": "desktop",
    },
}

_PROCS: dict[str, subprocess.Popen] = {}
_LOG_FILES: dict[str, Any] = {}
_LAST_ERROR: dict[str, str] = {}
_LOCK = threading.Lock()


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _repo_path(name: str) -> Path:
    return _EXT_ROOT / _SERVICE_META[name]["repo_name"]


def _log_path(name: str) -> Path:
    return _LOG_ROOT / f"{name}.log"


def _close_log(name: str):
    file_obj = _LOG_FILES.pop(name, None)
    if not file_obj:
        return
    try:
        file_obj.close()
    except Exception:
        pass


def _open_log(name: str):
    _close_log(name)
    file_obj = open(_log_path(name), "a", encoding="utf-8")
    _LOG_FILES[name] = file_obj
    return file_obj


def _clone_repo_if_missing(name: str):
    repo = _repo_path(name)
    if repo.exists():
        return
    repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", _REMOTE_URLS[name], str(repo)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creationflags(),
    )


def _get_setting(key: str, default: str = "") -> str:
    try:
        from core.config_store import config_store

        value = str(config_store.get(key, "") or "").strip()
        return value or default
    except Exception:
        return default


def _kiro_known_exe_paths() -> list[str]:
    candidates: list[str] = []

    configured = _get_setting("kiro_manager_exe")
    if configured and Path(configured).exists():
        candidates.append(str(Path(configured).resolve()).lower())

    for item in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiroAccountManager" / "KiroAccountManager.exe",
        Path(os.environ.get("ProgramFiles", "")) / "KiroAccountManager" / "KiroAccountManager.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "kiro-account-manager" / "kiro-account-manager.exe",
        Path(os.environ.get("ProgramFiles", "")) / "kiro-account-manager" / "kiro-account-manager.exe",
        _KIRO_MANAGER_EXTRACT_EXE,
    ]:
        if item.exists():
            candidates.append(str(item.resolve()).lower())
    return candidates


def _find_desktop_pid(name: str) -> int | None:
    if name != "kiro-manager":
        return None

    target_paths = set(_kiro_known_exe_paths())

    try:
        processes = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -in @('KiroAccountManager.exe','kiro-account-manager.exe') } | "
                "Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress",
            ],
            text=True,
            creationflags=_creationflags(),
        ).strip()
    except Exception:
        return None

    if not processes:
        return None

    try:
        import json

        data = json.loads(processes)
        items = data if isinstance(data, list) else [data]
        for item in items:
            pid = item.get("ProcessId")
            exe = str(item.get("ExecutablePath") or "").strip()
            if not pid:
                continue
            if not target_paths:
                return int(pid)
            if exe:
                try:
                    if str(Path(exe).resolve()).lower() in target_paths:
                        return int(pid)
                except Exception:
                    if exe.lower() in target_paths:
                        return int(pid)
    except Exception:
        return None

    return None


def _proc_running(name: str) -> bool:
    proc = _PROCS.get(name)
    return bool(proc and proc.poll() is None)


def _status_one(name: str) -> dict[str, Any]:
    meta = _SERVICE_META[name]
    repo = _repo_path(name)
    proc = _PROCS.get(name)
    desktop_pid = _find_desktop_pid(name)
    running = bool(desktop_pid or _proc_running(name))
    pid = proc.pid if proc and proc.poll() is None else desktop_pid
    return {
        "name": name,
        "label": meta["label"],
        "repo_path": str(repo),
        "repo_exists": repo.exists(),
        "url": "",
        "management_url": "",
        "management_key": "",
        "running": running,
        "pid": pid,
        "log_path": str(_log_path(name)),
        "last_error": _LAST_ERROR.get(name, ""),
        "kind": meta["kind"],
    }


def list_status() -> list[dict[str, Any]]:
    return [_status_one("kiro-manager")]


def install(name: str) -> dict[str, Any]:
    if name != "kiro-manager":
        raise KeyError(name)
    with _LOCK:
        _clone_repo_if_missing(name)
    return _status_one(name)


def _download_file(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(dest, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)


def _ensure_kiro_extracted_exe() -> str | None:
    if _KIRO_MANAGER_EXTRACT_EXE.exists():
        return str(_KIRO_MANAGER_EXTRACT_EXE)
    if not _KIRO_MANAGER_MSI.exists():
        _download_file(_KIRO_MANAGER_MSI_URL, _KIRO_MANAGER_MSI)
    _KIRO_MANAGER_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "msiexec.exe",
            "/a",
            str(_KIRO_MANAGER_MSI),
            f"TARGETDIR={_KIRO_MANAGER_EXTRACT_DIR}",
            "/qn",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creationflags(),
    )
    if _KIRO_MANAGER_EXTRACT_EXE.exists():
        return str(_KIRO_MANAGER_EXTRACT_EXE)
    return None


def _resolve_kiro_exe() -> str | None:
    configured = _get_setting("kiro_manager_exe")
    if configured and Path(configured).exists():
        return configured

    for item in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiroAccountManager" / "KiroAccountManager.exe",
        Path(os.environ.get("ProgramFiles", "")) / "KiroAccountManager" / "KiroAccountManager.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "kiro-account-manager" / "kiro-account-manager.exe",
        Path(os.environ.get("ProgramFiles", "")) / "kiro-account-manager" / "kiro-account-manager.exe",
        _KIRO_MANAGER_EXTRACT_EXE,
    ]:
        if item.exists():
            return str(item)

    return _ensure_kiro_extracted_exe()


def _build_command(name: str) -> tuple[list[str], Path]:
    repo = _repo_path(name)
    exe = _resolve_kiro_exe()
    if exe:
        return [exe], repo
    cargo = shutil.which("cargo")
    if not cargo:
        raise RuntimeError("未找到 Kiro Account Manager 可执行文件，且系统未安装 Rust/Cargo，无法从源码启动")
    return ["npm", "run", "tauri", "dev"], repo


def start(name: str) -> dict[str, Any]:
    if name != "kiro-manager":
        raise KeyError(name)

    with _LOCK:
        repo = _repo_path(name)
        if not repo.exists():
            raise RuntimeError("Kiro Account Manager 未安装，请先在插件页点击“安装”")
        if _status_one(name)["running"]:
            return _status_one(name)

        log_file = _open_log(name)
        try:
            command, cwd = _build_command(name)
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=_creationflags(),
            )
            _PROCS[name] = proc
            _LAST_ERROR[name] = ""
        except Exception as exc:
            _LAST_ERROR[name] = str(exc)
            _close_log(name)
            raise

    time.sleep(2)
    return _status_one(name)


def stop(name: str) -> dict[str, Any]:
    if name != "kiro-manager":
        raise KeyError(name)

    with _LOCK:
        proc = _PROCS.get(name)
        desktop_pid = _find_desktop_pid(name)

        if proc and proc.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_creationflags(),
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except Exception:
                    proc.kill()

        if desktop_pid and (not proc or desktop_pid != proc.pid):
            subprocess.run(
                ["taskkill", "/PID", str(desktop_pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creationflags(),
            )

        _PROCS.pop(name, None)
        _close_log(name)

    return _status_one(name)


def start_all() -> list[dict[str, Any]]:
    try:
        if not _repo_path("kiro-manager").exists():
            item = _status_one("kiro-manager")
            item["last_error"] = "未安装；如需使用请先手动安装"
            return [item]
        return [start("kiro-manager")]
    except Exception:
        return [_status_one("kiro-manager")]


def stop_all() -> list[dict[str, Any]]:
    return [stop("kiro-manager")]
