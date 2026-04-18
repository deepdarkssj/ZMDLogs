from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - non-Windows fallback
    winreg = None  # type: ignore[assignment]


_ACE_REGISTRY_KEYS = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\AntiCheatExpert")
    if winreg is not None
    else None,
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\AntiCheatExpert")
    if winreg is not None
    else None,
)


def _clean_display_icon(raw_value: str) -> str:
    value = str(raw_value or "").strip().strip('"').strip("'")
    if not value:
        return ""
    lower_value = value.lower()
    exe_index = lower_value.find(".exe")
    if exe_index >= 0:
        return value[: exe_index + 4]
    return value


def _candidate_game_dirs_from_display_icon(display_icon: str) -> list[Path]:
    cleaned = _clean_display_icon(display_icon)
    if not cleaned:
        return []
    candidates: list[Path] = []
    icon_path = Path(cleaned)
    icon_parts = [part.casefold() for part in icon_path.parts]
    if "endfield game".casefold() in icon_parts:
        endfield_index = icon_parts.index("endfield game".casefold())
        candidates.append(Path(*icon_path.parts[: endfield_index + 1]))
    if icon_path.parent.name.casefold() == "anticheatexpert" and icon_path.parent.parent.name:
        candidates.append(icon_path.parent.parent)
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def detect_game_exe_path() -> Path | None:
    if winreg is None:
        return None
    for candidate in _ACE_REGISTRY_KEYS:
        if candidate is None:
            continue
        root, subkey = candidate
        try:
            with winreg.OpenKey(root, subkey) as key:
                display_icon, _ = winreg.QueryValueEx(key, "DisplayIcon")
        except OSError:
            continue
        for game_dir in _candidate_game_dirs_from_display_icon(str(display_icon)):
            exe_path = game_dir / "Endfield.exe"
            if exe_path.exists():
                return exe_path.resolve()
    return None


def detect_game_dll_dir() -> Path | None:
    exe_path = detect_game_exe_path()
    if exe_path is None:
        return None
    dll_dir = exe_path.parent
    if (dll_dir / "GameAssembly.dll").exists():
        return dll_dir.resolve()
    return None
