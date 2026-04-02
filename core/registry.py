"""平台插件注册表 - 仅加载 Kiro 平台。"""

import importlib
from typing import Dict, Type

from .base_platform import BasePlatform

_registry: Dict[str, Type[BasePlatform]] = {}


def register(cls: Type[BasePlatform]):
    """装饰器：注册平台插件"""
    _registry[cls.name] = cls
    return cls


def load_all():
    """仅加载 Kiro 插件，项目已收缩为 Kiro-only。"""
    importlib.import_module("platforms.kiro.plugin")


def get(name: str) -> Type[BasePlatform]:
    if name not in _registry:
        raise KeyError(f"平台 '{name}' 未注册，已注册: {list(_registry.keys())}")
    return _registry[name]


def list_platforms() -> list:
    return [
        {"name": cls.name, "display_name": cls.display_name, "version": cls.version}
        for cls in _registry.values()
    ]
