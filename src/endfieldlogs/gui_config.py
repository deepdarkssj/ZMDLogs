from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from .install_detect import detect_game_dll_dir
from .models import OverlayEntry, OverlayGeometry, OverlaySourceType
from .runtime_paths import app_root, bundle_root
from .service import ServiceConfig

_LEGACY_BUILTIN_NAMES = {
    "",
    "悬浮窗",
    "内置悬浮窗",
    "伤害统计",
}
_BUILTIN_DAMAGE_NAME = "伤害统计"
_BUILTIN_COMBO_NAME = "连携cd监控"
_BUILTIN_BUFF_NAME = "buff监控"
_BUILTIN_UID_MASK_NAME = "UID遮挡"


@dataclass(slots=True)
class AppConfig:
    service: ServiceConfig
    overlays: list[OverlayEntry] = field(default_factory=list)
    theme_mode: str = "system"
    toggle_overlays_hotkey: str = "Ctrl+O"


def default_config_path() -> Path:
    return app_root() / "endfieldlogs.gui.json"


def default_service_config() -> ServiceConfig:
    bundle = bundle_root()
    app = app_root()
    detected_dll_dir = detect_game_dll_dir() or Path(r"E:\Hypergryph Launcher\games\Endfield Game")
    return ServiceConfig(
        ws_port=29325,
        log_dir=(app / "logs").resolve(),
        log_level="INFO",
        game_exe="Endfield.exe",
        npcap_device="auto",
        dll_dir=detected_dll_dir.resolve(),
        debug_enabled=False,
        debug_dir=(app / "debug").resolve(),
        rsa_key_txt=(app / "rsa_keys.txt").resolve(),
        name_index_path=(bundle / "jsondata" / "CharacterNameIndex.json").resolve(),
        merge_multi_phase_enemy_battles=False,
    )


def default_overlay_entries() -> list[OverlayEntry]:
    return [
        OverlayEntry(
            id=str(uuid.uuid4()),
            name=_BUILTIN_DAMAGE_NAME,
            source_type=OverlaySourceType.BUILTIN,
            source_value="damage",
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
            geometry=None,
        ),
        OverlayEntry(
            id=str(uuid.uuid4()),
            name=_BUILTIN_COMBO_NAME,
            source_type=OverlaySourceType.BUILTIN,
            source_value="combo_skill",
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
            geometry=None,
        ),
        OverlayEntry(
            id=str(uuid.uuid4()),
            name=_BUILTIN_BUFF_NAME,
            source_type=OverlaySourceType.BUILTIN,
            source_value="buff",
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
            geometry=None,
        ),
        OverlayEntry(
            id=str(uuid.uuid4()),
            name=_BUILTIN_UID_MASK_NAME,
            source_type=OverlaySourceType.BUILTIN,
            source_value="uid_mask",
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
            geometry=None,
        ),
    ]


def load_app_config(path: Path | None = None) -> AppConfig:
    target = path or default_config_path()
    if not target.exists():
        return AppConfig(service=default_service_config(), overlays=default_overlay_entries())
    payload = json.loads(target.read_text(encoding="utf-8"))
    service_default = default_service_config()
    service_payload = payload.get("service", {})
    overlays_payload = payload.get("overlays", [])
    config = AppConfig(
        service=ServiceConfig(
            ws_port=int(service_payload.get("ws_port", service_default.ws_port)),
            log_dir=Path(service_payload.get("log_dir", str(service_default.log_dir))).resolve(),
            log_level=str(service_payload.get("log_level", service_default.log_level)),
            game_exe=str(service_payload.get("game_exe", service_default.game_exe)),
            npcap_device=str(service_payload.get("npcap_device", service_default.npcap_device)),
            dll_dir=Path(service_payload.get("dll_dir", str(service_default.dll_dir))).resolve(),
            debug_enabled=bool(service_payload.get("debug_enabled", service_default.debug_enabled)),
            debug_dir=Path(service_payload.get("debug_dir", str(service_default.debug_dir))).resolve(),
            rsa_key_txt=Path(service_payload.get("rsa_key_txt", str(service_default.rsa_key_txt))).resolve(),
            name_index_path=Path(service_payload.get("name_index_path", str(service_default.name_index_path))).resolve(),
            merge_multi_phase_enemy_battles=bool(
                service_payload.get(
                    "merge_multi_phase_enemy_battles",
                    service_default.merge_multi_phase_enemy_battles,
                )
            ),
        ),
        overlays=[_overlay_entry_from_dict(item) for item in overlays_payload] or default_overlay_entries(),
        theme_mode=_normalize_theme_mode(payload.get("theme_mode")),
        toggle_overlays_hotkey=_normalize_hotkey(payload.get("toggle_overlays_hotkey")),
    )
    if getattr(sys, "frozen", False):
        app = app_root().resolve()
        bundle = bundle_root().resolve()
        if not config.service.log_dir.exists():
            config.service.log_dir = (app / "logs").resolve()
        if not config.service.debug_dir.exists():
            config.service.debug_dir = (app / "debug").resolve()
        if not config.service.rsa_key_txt.exists():
            config.service.rsa_key_txt = (app / "rsa_keys.txt").resolve()
        if not config.service.name_index_path.exists():
            config.service.name_index_path = (bundle / "jsondata" / "CharacterNameIndex.json").resolve()
    config.overlays = _ensure_builtin_entries(config.overlays)
    return config


def save_app_config(config: AppConfig, path: Path | None = None) -> None:
    target = path or default_config_path()
    target.write_text(
        json.dumps(
            {
                "service": {
                    "ws_port": config.service.ws_port,
                    "log_dir": str(config.service.log_dir),
                    "log_level": config.service.log_level,
                    "game_exe": config.service.game_exe,
                    "npcap_device": config.service.npcap_device,
                    "dll_dir": str(config.service.dll_dir),
                    "debug_enabled": config.service.debug_enabled,
                    "debug_dir": str(config.service.debug_dir),
                    "rsa_key_txt": str(config.service.rsa_key_txt),
                    "name_index_path": str(config.service.name_index_path),
                    "merge_multi_phase_enemy_battles": config.service.merge_multi_phase_enemy_battles,
                },
                "overlays": [_overlay_entry_to_dict(entry) for entry in config.overlays],
                "theme_mode": _normalize_theme_mode(config.theme_mode),
                "toggle_overlays_hotkey": _normalize_hotkey(config.toggle_overlays_hotkey),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _overlay_entry_from_dict(payload: dict[str, object]) -> OverlayEntry:
    geometry_payload = payload.get("geometry")
    geometry = None
    if isinstance(geometry_payload, dict):
        geometry = OverlayGeometry(
            x=int(geometry_payload.get("x", 0)),
            y=int(geometry_payload.get("y", 0)),
            width=int(geometry_payload.get("width", 980)),
            height=int(geometry_payload.get("height", 492)),
        )

    source_type = OverlaySourceType(str(payload.get("source_type", OverlaySourceType.BUILTIN.value)))
    source_value = str(payload.get("source_value") or "").strip()
    raw_name = str(payload.get("name") or "").strip()

    if source_type == OverlaySourceType.BUILTIN and not source_value:
        source_value = "damage"

    if source_type == OverlaySourceType.BUILTIN and source_value == "damage":
        name = _BUILTIN_DAMAGE_NAME if raw_name in _LEGACY_BUILTIN_NAMES else (raw_name or _BUILTIN_DAMAGE_NAME)
    elif source_type == OverlaySourceType.BUILTIN and source_value == "combo_skill":
        name = raw_name or _BUILTIN_COMBO_NAME
    elif source_type == OverlaySourceType.BUILTIN and source_value == "buff":
        name = raw_name or _BUILTIN_BUFF_NAME
    elif source_type == OverlaySourceType.BUILTIN and source_value == "uid_mask":
        name = raw_name or _BUILTIN_UID_MASK_NAME
    else:
        name = raw_name or "悬浮窗"

    return OverlayEntry(
        id=str(payload.get("id") or uuid.uuid4()),
        name=name,
        source_type=source_type,
        source_value=source_value,
        enabled=bool(payload.get("enabled", True)),
        locked=bool(payload.get("locked", False)),
        click_through=bool(payload.get("click_through", False)),
        opacity=max(0.1, min(1.0, float(payload.get("opacity", 1.0) or 1.0))),
        scale=max(0.5, min(3.0, float(payload.get("scale", 1.0) or 1.0))),
        geometry=geometry,
    )


def _ensure_builtin_entries(entries: list[OverlayEntry]) -> list[OverlayEntry]:
    normalized: list[OverlayEntry] = []
    damage_present = False
    combo_present = False
    buff_present = False
    uid_mask_present = False
    for entry in entries:
        if entry.source_type != OverlaySourceType.BUILTIN:
            normalized.append(entry)
            continue
        source_value = (entry.source_value or "damage").strip().lower()
        if source_value == "damage":
            damage_present = True
            normalized.append(replace(entry, source_value="damage", name=_BUILTIN_DAMAGE_NAME))
            continue
        if source_value == "combo_skill":
            combo_present = True
            normalized.append(replace(entry, source_value="combo_skill", name=entry.name or _BUILTIN_COMBO_NAME))
            continue
        if source_value == "buff":
            buff_present = True
            normalized.append(replace(entry, source_value="buff", name=entry.name or _BUILTIN_BUFF_NAME))
            continue
        if source_value == "uid_mask":
            uid_mask_present = True
            normalized.append(replace(entry, source_value="uid_mask", name=entry.name or _BUILTIN_UID_MASK_NAME))
            continue
        normalized.append(entry)
    defaults = default_overlay_entries()
    if not damage_present:
        normalized.insert(0, defaults[0])
    if not combo_present:
        normalized.append(defaults[1])
    if not buff_present:
        normalized.append(defaults[2])
    if not uid_mask_present:
        normalized.append(defaults[3])
    return normalized


def _overlay_entry_to_dict(entry: OverlayEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "name": entry.name,
        "source_type": entry.source_type.value,
        "source_value": entry.source_value,
        "enabled": entry.enabled,
        "locked": entry.locked,
        "click_through": entry.click_through,
        "opacity": entry.opacity,
        "scale": entry.scale,
        "geometry": None
        if entry.geometry is None
        else {
            "x": entry.geometry.x,
            "y": entry.geometry.y,
            "width": entry.geometry.width,
            "height": entry.geometry.height,
        },
    }


def _normalize_theme_mode(value: object) -> str:
    mode = str(value or "system").strip().lower()
    if mode in {"light", "dark", "system"}:
        return mode
    return "system"


def _normalize_hotkey(value: object) -> str:
    hotkey = str(value or "Ctrl+O").strip()
    return hotkey or "Ctrl+O"
