from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.protobuf.message import DecodeError, Message

from .protocol import iter_merged_frames, maybe_decompress_session_body, parse_head


@dataclass(slots=True)
class DecodedMessage:
    direction: str
    class_name: str
    msg_id: int
    head: dict[str, Any]
    message: Message


class MessageRegistry:
    def __init__(self, data_dir: Path, package_name: str = "endfieldlogs.proto_generated") -> None:
        self._package_name = package_name
        self._class_cache: dict[str, type[Message]] = {}
        self._maps = {
            "cs": self._load_map(data_dir / "message_ids_cs.json"),
            "sc": self._load_map(data_dir / "message_ids_sc.json"),
        }
        self._interesting_class_names = {
            "CS_BATTLE_OP",
            "CS_ENTER_DUNGEON",
            "CS_LEAVE_DUNGEON",
            "SC_OBJECT_ENTER_VIEW",
            "SC_SELF_SCENE_INFO",
            "SC_SYNC_CHAR_BAG_INFO",
            "CS_MERGE_MSG",
            "SC_MERGE_MSG",
        }
        self._interesting_msg_ids = {
            direction: {
                msg_id
                for msg_id, class_name in mapping.items()
                if class_name in self._interesting_class_names
            }
            for direction, mapping in self._maps.items()
        }

    @staticmethod
    def _load_map(path: Path) -> dict[int, str]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.values() if isinstance(payload, dict) else payload
        return {
            int(entry["msg_id"]): str(entry["class_name"])
            for entry in values
            if entry.get("msg_id") is not None and entry.get("class_name")
        }

    def resolve_class_name(self, direction: str, msg_id: int) -> str | None:
        return self._maps.get(direction, {}).get(msg_id)

    def should_decode_message(self, direction: str, msg_id: int) -> bool:
        return msg_id in self._interesting_msg_ids.get(direction, set())

    def load_message_class(self, class_name: str) -> type[Message] | None:
        cached = self._class_cache.get(class_name)
        if cached is not None:
            return cached

        try:
            module = importlib.import_module(f"{self._package_name}.{class_name}_pb2")
        except ModuleNotFoundError:
            return None

        cls = getattr(module, class_name, None)
        if cls is None:
            return None
        self._class_cache[class_name] = cls
        return cls

    def decode_messages(self, direction: str, head: dict[str, Any], body: bytes) -> list[DecodedMessage]:
        msg_id = int(head.get("msgid", 0))
        if not self.should_decode_message(direction, msg_id):
            return []
        class_name = self.resolve_class_name(direction, msg_id)
        if not class_name:
            return []
        message_class = self.load_message_class(class_name)
        if message_class is None:
            return []

        message = message_class()
        try:
            message.ParseFromString(body)
        except DecodeError:
            return []

        decoded = [DecodedMessage(direction=direction, class_name=class_name, msg_id=msg_id, head=head, message=message)]
        if class_name.endswith("MERGE_MSG"):
            merged_bytes = getattr(message, "msg", b"")
            if merged_bytes:
                for _, _, sub_head_bytes, sub_body in iter_merged_frames(merged_bytes):
                    sub_head = parse_head(sub_head_bytes)
                    sub_body = maybe_decompress_session_body(sub_head, sub_body)
                    decoded.extend(self.decode_messages(direction, sub_head, sub_body))
        return decoded
