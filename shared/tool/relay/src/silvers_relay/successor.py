from __future__ import annotations

from typing import Any


def successor_template() -> dict[str, Any]:
    """兼容旧内部调用名；字段本身只由 protocol spec 生成。"""

    from .protocol import successor_template_from_spec

    return successor_template_from_spec()
