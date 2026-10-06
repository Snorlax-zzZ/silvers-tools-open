from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import sys


def default_relay_home(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    user_home: Path | None = None,
) -> Path:
    """Resolve Relay's platform-specific runtime home without creating it."""

    environment = os.environ if environ is None else environ
    override = environment.get("SILVERS_RELAY_HOME", "").strip()
    if override:
        return Path(override).expanduser()

    current_platform = sys.platform if platform is None else platform
    home = Path.home() if user_home is None else user_home
    if current_platform == "win32":
        local_app_data = environment.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / "Silvers" / "Relay"
    return home / ".silvers" / "relay"
