from __future__ import annotations

import json
from pathlib import Path


def build_name_index(character_table_path: Path, i18n_path: Path) -> dict[str, str]:
    character_table = json.loads(character_table_path.read_text(encoding="utf-8-sig"))
    i18n_table = json.loads(i18n_path.read_text(encoding="utf-8-sig"))

    name_index: dict[str, str] = {}
    for templateid, payload in character_table.items():
        name_payload = payload.get("name") or {}
        name_id = name_payload.get("id")
        if name_id is None:
            continue
        text = i18n_table.get(str(name_id))
        if isinstance(text, str) and text:
            name_index[templateid] = text
    return name_index


def load_name_index(name_index_path: Path) -> dict[str, str]:
    payload = json.loads(name_index_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid name index payload: {name_index_path}")
    return {str(templateid): str(name) for templateid, name in payload.items() if isinstance(name, str) and name}
