from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import psutil
import websockets
from google.protobuf.json_format import MessageToDict

from .crypto.srsa_bridge import SRSABridge
from .crypto.xxe1 import XXE1
from .flow import TcpStreamReassembler
from .game_data import load_name_index
from .message_registry import DecodedMessage, MessageRegistry
from .models import (
    BattleLogEvent,
    CapturedPacket,
    Endpoint,
    EntityInfo,
    FlowKey,
    OutboundEvent,
    RuntimeMetrics,
    ServiceObserver,
    ServiceState,
    SquadMember,
)
from .npcap import CaptureManager
from .protocol import (
    load_private_key_from_txt,
    maybe_decompress_session_body,
    parse_head,
    parse_sc_login,
    pop_frame,
    rsa_decrypt_session_key,
)
from .runtime_paths import bundle_root

LOGGER = logging.getLogger(__name__)


def _load_multi_phase_dungeon_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for dungeon_id, templateid in payload.items():
        dungeon = str(dungeon_id or "").strip()
        template = str(templateid or "").strip()
        if dungeon and template:
            result[dungeon] = template
    return result


@dataclass(slots=True)
class ServiceConfig:
    ws_port: int
    log_dir: Path
    log_level: str
    game_exe: str
    npcap_device: str
    dll_dir: Path
    debug_enabled: bool
    debug_dir: Path
    rsa_key_txt: Path
    name_index_path: Path
    merge_multi_phase_enemy_battles: bool = False


class SessionPipeline:
    ENDMIN_VARIANTS = ("chr_0002_endminm", "chr_0003_endminf")

    def __init__(
        self,
        flow: FlowKey,
        session_id: str,
        registry: MessageRegistry,
        private_key: Any,
        srsa_bridge: SRSABridge,
        name_index: dict[str, str],
        multi_phase_dungeon_map: dict[str, str],
        merge_multi_phase_enemy_battles: bool,
        on_event: Callable[[OutboundEvent], None],
        on_debug_message: Callable[[DecodedMessage, int], None] | None,
        on_debug_record: Callable[[dict[str, object]], None] | None,
        metrics: RuntimeMetrics,
    ) -> None:
        self.flow = flow
        self.session_id = session_id
        self.registry = registry
        self.private_key = private_key
        self.srsa_bridge = srsa_bridge
        self.name_index = name_index
        self.multi_phase_dungeon_map = multi_phase_dungeon_map
        self.merge_multi_phase_enemy_battles = merge_multi_phase_enemy_battles
        self.on_event = on_event
        self.on_debug_message = on_debug_message
        self.on_debug_record = on_debug_record
        self.metrics = metrics

        self.client_reassembler = TcpStreamReassembler()
        self.server_reassembler = TcpStreamReassembler()
        self.client_buffer = bytearray()
        self.server_buffer = bytearray()
        self.pending_client_session_frames: deque[tuple[int, bytes, bytes, int]] = deque()
        self._last_gap_report: dict[str, tuple[int, int, int]] = {}
        self.pending_multi_frames: dict[tuple[str, int, int], dict[str, object]] = {}

        self.client_login_done = False
        self.server_login_done = False
        self.client_cipher: XXE1 | None = None
        self.server_cipher: XXE1 | None = None

        self.entity_index: dict[int, EntityInfo] = {}
        self.obj_to_battle: dict[int, int] = {}
        self.squad_index: dict[int, SquadMember] = {}
        self.char_potential_levels: dict[str, int] = {}
        self.skill_levels_by_battle_inst: dict[int, dict[str, int]] = {}
        self.global_skill_levels: dict[str, int] = {}
        self.tracked_dungeon_id: str | None = None
        self.tracked_enemy_templateid: str | None = None
        self.tracked_enemy_inst_ids: set[int] = set()
        self.merged_battle_active = False

    @property
    def is_live(self) -> bool:
        return (
            self.client_login_done
            and self.server_login_done
            and self.client_cipher is not None
            and self.server_cipher is not None
        )

    def process_packet(self, packet: CapturedPacket) -> None:
        direction = "cs" if packet.src == self.flow.client else "sc"
        reassembler = self.client_reassembler if direction == "cs" else self.server_reassembler
        buffer = self.client_buffer if direction == "cs" else self.server_buffer
        flushed_chunks = reassembler.accept(packet.seq, packet.payload)
        if flushed_chunks:
            self._last_gap_report.pop(direction, None)
        else:
            gap = reassembler.gap_state()
            if gap is not None and self.on_debug_record is not None and self._last_gap_report.get(direction) != gap:
                self._last_gap_report[direction] = gap
                missing_from_seq, next_seen_seq, missing_bytes = gap
                self.on_debug_record(
                    {
                        "type": "debug_tcp_gap",
                        "session_id": self.session_id,
                        "timestamp_ms": packet.timestamp_ms,
                        "direction": direction,
                        "missing_from_seq": missing_from_seq,
                        "next_seen_seq": next_seen_seq,
                        "missing_bytes": missing_bytes,
                        "packet_seq": packet.seq,
                        "packet_len": len(packet.payload),
                    }
                )
        for chunk in flushed_chunks:
            buffer.extend(chunk)
            self._drain_direction(direction, packet.timestamp_ms)

    def _drain_direction(self, direction: str, timestamp_ms: int) -> None:
        buffer = self.client_buffer if direction == "cs" else self.server_buffer
        while True:
            frame = pop_frame(buffer)
            if frame is None:
                return
            head_len, head_bytes, payload = frame
            if direction == "cs" and not self.client_login_done:
                self.client_login_done = True
                continue
            if direction == "sc" and not self.server_login_done:
                plain = self.srsa_bridge.decrypt_login_body(payload)
                login_info = parse_sc_login(plain)
                session_key = rsa_decrypt_session_key(self.private_key, login_info["session_key_encrypted"])
                nonce = login_info["session_nonce"]
                self.client_cipher = XXE1(session_key, nonce, counter=1)
                self.server_cipher = XXE1(session_key, nonce, counter=1)
                self.server_login_done = True
                self._drain_pending_client_session_frames()
                continue
            cipher = self.client_cipher if direction == "cs" else self.server_cipher
            if cipher is None:
                if direction == "cs":
                    self.pending_client_session_frames.append((head_len, head_bytes, payload, timestamp_ms))
                continue
            self._decode_session_frame(direction, head_len, head_bytes, payload, timestamp_ms)

    def _drain_pending_client_session_frames(self) -> None:
        while self.pending_client_session_frames and self.client_cipher is not None:
            head_len, head_bytes, payload, timestamp_ms = self.pending_client_session_frames.popleft()
            self._decode_session_frame("cs", head_len, head_bytes, payload, timestamp_ms)

    def _decode_session_frame(
        self,
        direction: str,
        head_len: int,
        head_bytes: bytes,
        payload: bytes,
        timestamp_ms: int,
    ) -> None:
        cipher = self.client_cipher if direction == "cs" else self.server_cipher
        if cipher is None:
            return
        plain = cipher.process(head_bytes + payload)
        plain_head = plain[:head_len]
        plain_body = plain[head_len:]
        head = parse_head(plain_head)
        if self.on_debug_record is not None and "parse_error" in head:
            self.on_debug_record(
                {
                    "type": "debug_frame_error",
                    "session_id": self.session_id,
                    "timestamp_ms": timestamp_ms,
                    "direction": direction,
                    "error": head["parse_error"],
                    "head_len": head_len,
                    "plain_head_hex": plain_head.hex(),
                    "plain_body_prefix_hex": plain_body[:64].hex(),
                }
            )
        if "parse_error" in head:
            return
        if self.on_debug_record is not None:
            msg_id = int(head.get("msgid", 0) or 0)
            self.on_debug_record(
                {
                    "type": "debug_session_head",
                    "session_id": self.session_id,
                    "timestamp_ms": timestamp_ms,
                    "direction": direction,
                    "msg_id": msg_id,
                    "class_name": self.registry.resolve_class_name(direction, msg_id),
                    "head": head,
                    "head_len": head_len,
                    "plain_head_hex": plain_head.hex(),
                    "plain_body_len": len(plain_body),
                    "plain_body_prefix_hex": plain_body[:64].hex(),
                }
            )
        assembled = self._assemble_multi_pack_message(direction, head, plain_body, timestamp_ms)
        if assembled is None:
            return
        head, body, is_already_decompressed = assembled
        msg_id = int(head.get("msgid", 0) or 0)
        if not self.registry.should_decode_message(direction, msg_id):
            return
        if not is_already_decompressed:
            body = maybe_decompress_session_body(head, body)
        self.metrics.frames_decoded += 1
        decoded_messages = self.registry.decode_messages(direction, head, body)
        if self.on_debug_record is not None and not decoded_messages:
            self.on_debug_record(
                {
                    "type": "debug_undecoded_frame",
                    "session_id": self.session_id,
                    "timestamp_ms": timestamp_ms,
                    "direction": direction,
                    "head": head,
                    "head_len": head_len,
                    "plain_head_hex": plain_head.hex(),
                    "plain_body_prefix_hex": body[:128].hex(),
                }
            )
        for decoded in decoded_messages:
            self.metrics.messages_decoded += 1
            self._handle_message(decoded, timestamp_ms)

    def _assemble_multi_pack_message(
        self,
        direction: str,
        head: dict[str, Any],
        plain_body: bytes,
        timestamp_ms: int,
    ) -> tuple[dict[str, Any], bytes, bool] | None:
        total_pack_count = int(head.get("total_pack_count", 1) or 1)
        if total_pack_count <= 1:
            return head, plain_body, False

        current_pack_index = int(head.get("current_pack_index", 0) or 0)
        seqid = int(head.get("down_seqid", head.get("up_seqid", 0)) or 0)
        if seqid <= 0:
            return None
        base_seqid = seqid - current_pack_index
        key = (direction, int(head.get("msgid", 0) or 0), base_seqid)
        state = self.pending_multi_frames.setdefault(
            key,
            {
                "total_pack_count": total_pack_count,
                "head": dict(head),
                "parts": {},
                "first_timestamp_ms": timestamp_ms,
                "last_timestamp_ms": timestamp_ms,
            },
        )
        parts = state["parts"]
        assert isinstance(parts, dict)
        parts[current_pack_index] = maybe_decompress_session_body(head, plain_body)
        state["last_timestamp_ms"] = timestamp_ms
        if len(parts) < total_pack_count:
            if self.on_debug_record is not None:
                self.on_debug_record(
                    {
                        "type": "debug_multipack_pending",
                        "session_id": self.session_id,
                        "timestamp_ms": timestamp_ms,
                        "direction": direction,
                        "msg_id": int(head.get("msgid", 0) or 0),
                        "seqid": seqid,
                        "base_seqid": base_seqid,
                        "total_pack_count": total_pack_count,
                        "current_pack_index": current_pack_index,
                        "received_indexes": sorted(int(index) for index in parts.keys()),
                    }
                )
            return None

        combined = b"".join(parts[index] for index in range(total_pack_count) if index in parts)
        if len(parts) != total_pack_count:
            return None
        full_head = dict(state["head"])
        full_head["is_compress"] = False
        self.pending_multi_frames.pop(key, None)
        return full_head, combined, True

    def flush_debug_state(self) -> None:
        if self.on_debug_record is None:
            self.pending_multi_frames.clear()
            return
        for (direction, msg_id, base_seqid), state in list(self.pending_multi_frames.items()):
            parts = state.get("parts", {})
            if not isinstance(parts, dict):
                continue
            self.on_debug_record(
                {
                    "type": "debug_multipack_incomplete",
                    "session_id": self.session_id,
                    "timestamp_ms": int(state.get("last_timestamp_ms", state.get("first_timestamp_ms", 0)) or 0),
                    "direction": direction,
                    "msg_id": msg_id,
                    "base_seqid": base_seqid,
                    "total_pack_count": int(state.get("total_pack_count", 0) or 0),
                    "received_indexes": sorted(int(index) for index in parts.keys()),
                    "first_timestamp_ms": int(state.get("first_timestamp_ms", 0) or 0),
                    "last_timestamp_ms": int(state.get("last_timestamp_ms", 0) or 0),
                    "head": state.get("head", {}),
                }
            )
        self.pending_multi_frames.clear()

    def _handle_message(self, decoded: DecodedMessage, timestamp_ms: int) -> None:
        if self.on_debug_message is not None and decoded.class_name in {
            "CS_BATTLE_OP",
            "SC_SELF_SCENE_INFO",
            "SC_SYNC_CHAR_BAG_INFO",
            "CS_ENTER_DUNGEON",
            "CS_LEAVE_DUNGEON",
            "SC_OBJECT_ENTER_VIEW",
        }:
            self.on_debug_message(decoded, timestamp_ms)
        if decoded.class_name == "CS_ENTER_DUNGEON":
            self._handle_enter_dungeon(decoded.message)
            return
        if decoded.class_name == "CS_LEAVE_DUNGEON":
            self._handle_leave_dungeon(timestamp_ms)
            return
        if decoded.class_name == "SC_SYNC_CHAR_BAG_INFO":
            self._update_char_bag_info(decoded.message)
            return
        if decoded.class_name == "SC_SELF_SCENE_INFO":
            self._update_squad_index(decoded.message, timestamp_ms)
            return
        if decoded.class_name == "SC_OBJECT_ENTER_VIEW":
            self._update_entity_index(decoded.message)
            return
        if decoded.class_name == "SC_OBJECT_LEAVE_VIEW":
            self._remove_entities(decoded.message)
            return
        if decoded.class_name == "CS_BATTLE_OP":
            self._emit_battle_events(decoded.message, timestamp_ms)

    def _iter_detail_objects(self, detail: Any):
        for field_desc, value in detail.ListFields():
            if field_desc.label != field_desc.LABEL_REPEATED:
                continue
            for item in value:
                common_info = getattr(item, "common_info", None)
                battle_info = getattr(item, "battle_info", None)
                if common_info is None or battle_info is None:
                    continue
                battle_inst_id = int(getattr(battle_info, "battle_inst_id", 0))
                if not battle_inst_id:
                    continue
                yield item, common_info, battle_info

    def _update_entity_index(self, message: Any) -> None:
        detail = getattr(message, "detail", None)
        if detail is None:
            return
        for _, common_info, battle_info in self._iter_detail_objects(detail):
            info = EntityInfo(
                battle_inst_id=int(getattr(battle_info, "battle_inst_id", 0)),
                obj_id=int(getattr(common_info, "id", 0)) or None,
                templateid=str(getattr(common_info, "templateid", "")) or None,
                entity_type=int(getattr(common_info, "type", 0)) or None,
            )
            self.entity_index[info.battle_inst_id] = info
            if info.obj_id is not None:
                self.obj_to_battle[info.obj_id] = info.battle_inst_id
            if (
                self.merge_multi_phase_enemy_battles
                and self.tracked_enemy_templateid is not None
                and info.templateid == self.tracked_enemy_templateid
            ):
                self.tracked_enemy_inst_ids.add(info.battle_inst_id)

    def _handle_enter_dungeon(self, message: Any) -> None:
        if not self.merge_multi_phase_enemy_battles:
            return
        dungeon_id = str(getattr(message, "dungeon_id", "") or "").strip()
        templateid = self.multi_phase_dungeon_map.get(dungeon_id)
        if not templateid:
            self.tracked_dungeon_id = None
            self.tracked_enemy_templateid = None
            self.tracked_enemy_inst_ids.clear()
            self.merged_battle_active = False
            return
        self.tracked_dungeon_id = dungeon_id
        self.tracked_enemy_templateid = templateid
        self.tracked_enemy_inst_ids.clear()
        for info in self.entity_index.values():
            if info.templateid == templateid:
                self.tracked_enemy_inst_ids.add(info.battle_inst_id)

    def _handle_leave_dungeon(self, timestamp_ms: int) -> None:
        if self.merge_multi_phase_enemy_battles and self.merged_battle_active:
            self._emit_event(
                BattleLogEvent(
                    session_id=self.session_id,
                    timestamp_ms=timestamp_ms,
                    event_type="BattleOpModifyBattleState",
                    payload={
                        "seq_id": None,
                        "client_tick_tms": None,
                        "is_in_battle": False,
                    },
                )
            )
        self.tracked_dungeon_id = None
        self.tracked_enemy_templateid = None
        self.tracked_enemy_inst_ids.clear()
        self.merged_battle_active = False

    def _update_squad_index(self, message: Any, timestamp_ms: int) -> None:
        detail = getattr(message, "detail", None)
        team_info = getattr(message, "team_info", None)
        if detail is None:
            return
        char_list = list(getattr(detail, "char_list", []))
        if not char_list:
            LOGGER.info(
                "ignoring SC_SELF_SCENE_INFO without char_list self_info_reason=%s",
                getattr(message, "self_info_reason", None),
            )
            return
        current_leader_id = int(getattr(team_info, "cur_leader_id", 0)) if team_info is not None else 0
        self.squad_index.clear()
        self.skill_levels_by_battle_inst.clear()
        self.global_skill_levels.clear()
        for squad_index, char_info in enumerate(char_list):
            common_info = getattr(char_info, "common_info", None)
            battle_info = getattr(char_info, "battle_info", None)
            if common_info is None or battle_info is None:
                continue
            battle_inst_id = int(getattr(battle_info, "battle_inst_id", 0))
            if not battle_inst_id:
                continue
            obj_id = int(getattr(common_info, "id", 0)) or None
            templateid = self._resolve_scene_templateid(common_info, battle_info)
            display_name = self.name_index.get(templateid or "", templateid)
            member = SquadMember(
                battle_inst_id=battle_inst_id,
                obj_id=obj_id,
                templateid=templateid,
                display_name=display_name,
                is_leader=obj_id == current_leader_id,
                squad_index=squad_index,
            )
            self.squad_index[battle_inst_id] = member
            self.entity_index[battle_inst_id] = EntityInfo(
                battle_inst_id=battle_inst_id,
                obj_id=obj_id,
                templateid=templateid,
                entity_type=int(getattr(common_info, "type", 0)) or None,
            )
            if obj_id is not None:
                self.obj_to_battle[obj_id] = battle_inst_id
            self._cache_scene_skill_levels(battle_inst_id, battle_info)
        self._emit_scene_info_event(timestamp_ms)

    def _update_char_bag_info(self, message: Any) -> None:
        for char_info in getattr(message, "char_info", []):
            templateid = str(getattr(char_info, "templateid", "")) or None
            if not templateid:
                continue
            level = int(getattr(char_info, "potential_level", 0) or 0)
            self.char_potential_levels[templateid] = level
        LOGGER.info('检测到潜能：%s',self.char_potential_levels)

    @staticmethod
    def _template_key(template_type: str | None, template_int_id: int | None, template_str_id: str | None) -> str | None:
        if template_str_id:
            prefix = (template_type or "unknown").lower()
            return f"{prefix}:str:{template_str_id}"
        if template_int_id is not None:
            prefix = (template_type or "unknown").lower()
            return f"{prefix}:int:{template_int_id}"
        return None

    def _cache_scene_skill_levels(self, battle_inst_id: int, battle_info: Any) -> None:
        per_battle: dict[str, int] = {}
        for skill in getattr(battle_info, "skill_list", []):
            skill_id = getattr(skill, "skill_id", None)
            template_type, template_int_id, template_str_id = self._template_id_payload(skill_id)
            key = self._template_key(template_type, template_int_id, template_str_id)
            if key is None:
                continue
            level = int(getattr(skill, "level", 1) or 1)
            per_battle[key] = level
            self.global_skill_levels[key] = level
        if per_battle:
            self.skill_levels_by_battle_inst[battle_inst_id] = per_battle

    def _remove_entities(self, message: Any) -> None:
        for item in getattr(message, "obj_list", []):
            obj_id = int(getattr(item, "obj_id", 0))
            if not obj_id:
                continue
            battle_inst_id = self.obj_to_battle.pop(obj_id, None)
            if battle_inst_id is not None:
                self.entity_index.pop(battle_inst_id, None)
                self.squad_index.pop(battle_inst_id, None)

    def _resolve_display_name(self, templateid: str | None) -> str | None:
        if templateid is None:
            return None
        return self.name_index.get(templateid, templateid)

    @classmethod
    def _extract_endmin_variant(cls, text: str | None) -> str | None:
        if not text:
            return None
        for variant in cls.ENDMIN_VARIANTS:
            if variant in text:
                return variant
        return None

    @classmethod
    def _infer_endmin_variant(cls, battle_info: Any) -> str | None:
        if battle_info is None:
            return None

        for buff in getattr(battle_info, "buff_list", []):
            variant = cls._extract_endmin_variant(str(getattr(buff, "stacking_group_id", "")) or None)
            if variant is not None:
                return variant

        for group in getattr(battle_info, "stacking_group_list", []):
            variant = cls._extract_endmin_variant(str(getattr(group, "stacking_key", "")) or None)
            if variant is not None:
                return variant

        for skill in getattr(battle_info, "skill_list", []):
            for node_id in getattr(skill, "talent_node_ids", []):
                variant = cls._extract_endmin_variant(str(node_id))
                if variant is not None:
                    return variant
            blackboard = getattr(getattr(skill, "blackboard", None), "blackboard", None)
            if blackboard is None:
                continue
            for value in blackboard.values():
                variant = cls._extract_endmin_variant(str(getattr(value, "str_value", "")) or None)
                if variant is not None:
                    return variant

        return None

    def _resolve_scene_templateid(self, common_info: Any, battle_info: Any) -> str | None:
        templateid = str(getattr(common_info, "templateid", "")) or None
        if templateid != "chr_9000_endmin":
            return templateid
        return self._infer_endmin_variant(battle_info) or templateid

    def _emit_scene_info_event(self, timestamp_ms: int) -> None:
        members = sorted(self.squad_index.values(), key=lambda item: item.squad_index)
        LOGGER.info(
            "squad update members=%s",
            [(member.squad_index, member.display_name, member.battle_inst_id) for member in members],
        )
        self._emit_event(
            BattleLogEvent(
                session_id=self.session_id,
                timestamp_ms=timestamp_ms,
                event_type="SC_SELF_SCENE_INFO",
                payload={
                    "char_list": [
                        {
                            "id": member.obj_id,
                            "templateid": member.templateid,
                            "battle_inst_id": member.battle_inst_id,
                            "display_name": member.display_name or self._resolve_display_name(member.templateid),
                            "potential_level": self._potential_level_for_template(member.templateid),
                            "is_leader": member.is_leader,
                            "squad_index": member.squad_index,
                        }
                        for member in members
                    ]
                },
            )
        )

    def _potential_level_for_template(self, templateid: str | None) -> int:
        if templateid is None:
            return 0
        level = self.char_potential_levels.get(templateid)
        if level is not None:
            return level
        if templateid in self.ENDMIN_VARIANTS:
            return self.char_potential_levels.get("chr_9000_endmin", 0)
        return 0

    def _skill_level_for_trigger(
        self,
        op: Any,
        trigger_data: Any,
        template_type: str | None,
        template_int_id: int | None,
        template_str_id: str | None,
        action: Any,
    ) -> int:
        key = self._template_key(template_type, template_int_id, template_str_id)
        if key is None:
            return 1
        candidates: list[int] = []
        damage_action = getattr(action, "damage_action", None)
        attacker_id = int(getattr(damage_action, "attacker_id", 0)) if damage_action is not None else 0
        if attacker_id:
            candidates.append(attacker_id)
        trigger_owner = int(getattr(trigger_data, "owner_id", 0) or 0)
        if trigger_owner:
            candidates.append(trigger_owner)
        op_owner = int(getattr(op, "owner_id", 0) or 0)
        if op_owner:
            candidates.append(op_owner)
        seen: set[int] = set()
        for battle_inst_id in candidates:
            if battle_inst_id in seen:
                continue
            seen.add(battle_inst_id)
            level = self.skill_levels_by_battle_inst.get(battle_inst_id, {}).get(key)
            if level is not None:
                return level
        return self.global_skill_levels.get(key, 1)

    @staticmethod
    def _read_float_presence(detail: Any, field_name: str) -> float | None:
        try:
            if detail.HasField(field_name):
                return float(getattr(detail, field_name))
        except ValueError:
            value = float(getattr(detail, field_name, 0.0))
            if value != 0.0:
                return value
        return None

    @staticmethod
    def _field_enum_name(message: Any, field_name: str, default: str | None = None) -> str | None:
        try:
            field = type(message).DESCRIPTOR.fields_by_name[field_name]
            return field.enum_type.values_by_number[int(getattr(message, field_name))].name
        except Exception:
            return default

    @classmethod
    def _template_id_payload(cls, template_id: Any) -> tuple[str | None, int | None, str | None]:
        if template_id is None:
            return None, None, None
        return (
            cls._field_enum_name(template_id, "type"),
            int(getattr(template_id, "int_id", 0)) or None,
            str(getattr(template_id, "str_id", "")) or None,
        )

    @staticmethod
    def _message_to_payload(message: Any) -> dict[str, object]:
        if message is None:
            return {}
        return MessageToDict(
            message,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

    def _emit_event(self, event: OutboundEvent) -> None:
        self.metrics.outbound_events_emitted += 1
        self.on_event(event)

    def _emit_battle_events(self, message: Any, timestamp_ms: int) -> None:
        client_data = getattr(message, "client_data", None)
        if client_data is None:
            return
        for op in getattr(client_data, "op_list", []):
            op_type_name = self._field_enum_name(op, "op_type")
            if op_type_name is None:
                continue
            seq_id = int(getattr(op, "seq_id", 0)) or None
            client_tick_tms = int(getattr(op, "client_tick_tms", 0)) or None

            if op_type_name == "BattleOpTriggerAction":
                self._emit_trigger_action_event(op, seq_id, client_tick_tms, timestamp_ms)
                continue
            if op_type_name == "BattleOpFinishBuff":
                finish_data = getattr(op, "finish_buff_op_data", None)
                if finish_data is None:
                    continue
                self._emit_event(
                    BattleLogEvent(
                        session_id=self.session_id,
                        timestamp_ms=timestamp_ms,
                        event_type=op_type_name,
                        payload={
                            "seq_id": seq_id,
                            "client_tick_tms": client_tick_tms,
                            "buff_inst_id": int(getattr(finish_data, "buff_inst_id", 0)) or None,
                        },
                    )
                )
                continue
            if op_type_name == "BattleOpAddBuff":
                add_data = getattr(op, "add_buff_op_data", None)
                if add_data is None:
                    continue
                _, template_int_id, template_str_id = self._template_id_payload(getattr(add_data, "buff_id", None))
                payload: dict[str, object | None] = {
                    "seq_id": seq_id,
                    "client_tick_tms": client_tick_tms,
                    "int_id": template_int_id,
                    "buff_inst_id": int(getattr(add_data, "buff_inst_id", 0)) or None,
                    "src_inst_id": int(getattr(add_data, "src_inst_id", 0)) or None,
                    "target_inst_id": int(getattr(add_data, "target_inst_id", 0)) or None,
                    "assigned_items": self._message_to_payload(getattr(add_data, "assigned_items", None)),
                }
                if template_str_id:
                    payload["str_id"] = template_str_id
                self._emit_event(
                    BattleLogEvent(
                        session_id=self.session_id,
                        timestamp_ms=timestamp_ms,
                        event_type=op_type_name,
                        payload=payload,
                    )
                )
                continue
            if op_type_name == "BattleOpEnablePassiveSkill":
                enable_data = getattr(op, "skill_enable_op_data", None)
                if enable_data is None:
                    continue
                self._emit_event(
                    BattleLogEvent(
                        session_id=self.session_id,
                        timestamp_ms=timestamp_ms,
                        event_type=op_type_name,
                        payload={
                            "seq_id": seq_id,
                            "client_tick_tms": client_tick_tms,
                            "skill_inst_id": int(getattr(enable_data, "skill_inst_id", 0)) or None,
                        },
                    )
                )
                continue
            if op_type_name == "BattleOpEntityDie":
                die_data = getattr(op, "entity_die_op_data", None)
                if die_data is None:
                    continue
                entity_inst_id = int(getattr(die_data, "entity_inst_id", 0)) or None
                self._emit_event(
                    BattleLogEvent(
                        session_id=self.session_id,
                        timestamp_ms=timestamp_ms,
                        event_type=op_type_name,
                        payload={
                            "seq_id": seq_id,
                            "client_tick_tms": client_tick_tms,
                            "entity_inst_id": entity_inst_id,
                        },
                    )
                )
                if (
                    self.merge_multi_phase_enemy_battles
                    and self.merged_battle_active
                    and entity_inst_id is not None
                    and entity_inst_id in self.tracked_enemy_inst_ids
                ):
                    self._emit_event(
                        BattleLogEvent(
                            session_id=self.session_id,
                            timestamp_ms=timestamp_ms,
                            event_type="BattleOpModifyBattleState",
                            payload={
                                "seq_id": seq_id,
                                "client_tick_tms": client_tick_tms,
                                "is_in_battle": False,
                            },
                        )
                    )
                    self.merged_battle_active = False
                    self.tracked_enemy_inst_ids.clear()
                continue
            if op_type_name == "BattleOpModifyBattleState":
                battle_state_data = getattr(op, "modify_battle_state_op_data", None)
                if battle_state_data is None:
                    continue
                is_in_battle = bool(getattr(battle_state_data, "is_in_battle", False))
                if self.merge_multi_phase_enemy_battles and self.tracked_enemy_templateid is not None:
                    if is_in_battle and not self.merged_battle_active:
                        self.merged_battle_active = True
                    else:
                        continue
                self._emit_event(
                    BattleLogEvent(
                        session_id=self.session_id,
                        timestamp_ms=timestamp_ms,
                        event_type=op_type_name,
                        payload={
                            "seq_id": seq_id,
                            "client_tick_tms": client_tick_tms,
                            "is_in_battle": is_in_battle,
                        },
                    )
                )

    def _emit_trigger_action_event(
        self,
        op: Any,
        seq_id: int | None,
        client_tick_tms: int | None,
        timestamp_ms: int,
    ) -> None:
        trigger_data = getattr(op, "trigger_action_op_data", None)
        if trigger_data is None:
            return
        action = getattr(trigger_data, "action", None)
        if action is None:
            return
        template_type, template_int_id, template_str_id = self._template_id_payload(getattr(trigger_data, "template_id", None))
        payload: dict[str, object | None] = {
            "seq_id": seq_id,
            "client_tick_tms": client_tick_tms,
            "owner_id": int(getattr(trigger_data, "owner_id", 0) or getattr(op, "owner_id", 0)) or None,
            "owner_type": str(getattr(trigger_data, "owner_type", "")) or None,
            "inst_id": int(getattr(trigger_data, "inst_id", 0)) or None,
            "template_type": template_type,
            "template_int_id": template_int_id,
            "action": self._message_to_payload(action),
        }
        if template_str_id:
            payload["template_str_id"] = template_str_id
        if (template_type or "").lower() == "skill":
            payload["level"] = self._skill_level_for_trigger(
                op,
                trigger_data,
                template_type,
                template_int_id,
                template_str_id,
                action,
            )
        self._emit_event(
            BattleLogEvent(
                session_id=self.session_id,
                timestamp_ms=timestamp_ms,
                event_type="BattleOpTriggerAction",
                payload=payload,
            )
        )


class DamageLogService:
    def __init__(self, config: ServiceConfig, observer: ServiceObserver | None = None) -> None:
        self.config = config
        self.observer = observer
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._fatal_exception: BaseException | None = None
        self.state = ServiceState.WAITING_GAME
        self.metrics = RuntimeMetrics()
        self.packet_queue: asyncio.Queue[CapturedPacket] = asyncio.Queue(maxsize=20000)
        self.clients: set[Any] = set()
        self.registry = MessageRegistry(bundle_root() / "data")
        self.name_index = load_name_index(config.name_index_path)
        self.multi_phase_dungeon_map = _load_multi_phase_dungeon_map(bundle_root() / "jsondata" / "Dungeon.json")
        self.private_key = load_private_key_from_txt(config.rsa_key_txt)
        self.srsa_bridge = SRSABridge(config.dll_dir)
        self.capture_manager = CaptureManager.create(config.npcap_device, self._on_packet_from_thread)
        self.pending_packets: dict[FlowKey, deque[CapturedPacket]] = defaultdict(lambda: deque(maxlen=8192))
        self.active_flow: FlowKey | None = None
        self.active_session: SessionPipeline | None = None
        self.batch: list[dict[str, object]] = []
        self.log_file = None
        self.debug_session_dir: Path | None = None
        self.debug_counters: dict[tuple[str, str], int] = defaultdict(int)
        self.server = None
    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self.server = await websockets.serve(self._ws_handler, "127.0.0.1", self.config.ws_port)
        self.capture_manager.start()
        self._set_state(ServiceState.WAITING_RESTART if self._game_running() else ServiceState.WAITING_GAME)
        tasks = [
            asyncio.create_task(self._process_monitor_loop(), name="process-monitor"),
            asyncio.create_task(self._packet_loop(), name="packet-loop"),
            asyncio.create_task(self._batch_flush_loop(), name="batch-flush"),
            asyncio.create_task(self._stats_loop(), name="stats-loop"),
        ]
        for task in tasks:
            task.add_done_callback(self._on_background_task_done)
        try:
            await self._stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.capture_manager.stop()
            if self.server is not None:
                self.server.close()
                await self.server.wait_closed()
            if self.log_file is not None:
                self.log_file.close()
                self.log_file = None
            self.server = None
            self.loop = None
            self._stop_event = None
            if self._fatal_exception is not None:
                exc = self._fatal_exception
                self._fatal_exception = None
                raise exc

    def request_stop(self) -> None:
        if self.loop is None or self._stop_event is None:
            return
        if self.loop.is_closed():
            return
        try:
            self.loop.call_soon_threadsafe(self._stop_event.set)
        except RuntimeError:
            return

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return
        LOGGER.exception("background task failed", exc_info=exc)
        self._fatal_exception = exc
        if self.loop is not None and self._stop_event is not None and not self._stop_event.is_set():
            if self.loop.is_closed():
                return
            try:
                self.loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                return

    def _on_packet_from_thread(self, packet: CapturedPacket) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._queue_packet, packet)

    def _queue_packet(self, packet: CapturedPacket) -> None:
        self.metrics.packets_seen += 1
        try:
            self.packet_queue.put_nowait(packet)
        except asyncio.QueueFull:
            self.metrics.packets_dropped_queue += 1

    async def _ws_handler(self, websocket):
        self.clients.add(websocket)
        try:
            await websocket.send(json.dumps(self._hello_payload(), ensure_ascii=False))
            await websocket.wait_closed()
        finally:
            self.clients.discard(websocket)

    def _hello_payload(self) -> dict[str, object]:
        return {
            "type": "hello",
            "schema_version": 2,
            "service_version": "0.1.0",
            "state": self.state.value,
            "session_id": self.active_session.session_id if self.active_session else None,
        }

    async def _broadcast(self, payload: dict[str, object]) -> None:
        if not self.clients:
            return
        message = json.dumps(payload, ensure_ascii=False)
        await asyncio.gather(*(client.send(message) for client in tuple(self.clients)), return_exceptions=True)

    def _set_state(self, state: ServiceState) -> None:
        if self.state == state:
            return
        self.state = state
        LOGGER.info("service state -> %s", state.value)
        if self.observer is not None and self.observer.on_state_change is not None:
            self.observer.on_state_change(
                self.state,
                self.active_session.session_id if self.active_session else None,
                self.active_flow,
            )
        if self.loop is not None:
            self.loop.create_task(self._broadcast(self._hello_payload()))

    def _game_running(self) -> bool:
        target = self.config.game_exe.lower()
        for process in psutil.process_iter(["name"]):
            if (process.info.get("name") or "").lower() == target:
                return True
        return False

    def _find_game_pids(self) -> set[int]:
        target = self.config.game_exe.lower()
        pids: set[int] = set()
        for process in psutil.process_iter(["name"]):
            if (process.info.get("name") or "").lower() == target:
                pids.add(int(process.pid))
        return pids

    def _find_active_flow(self, game_pids: set[int]) -> FlowKey | None:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.pid not in game_pids:
                continue
            if not conn.laddr or not conn.raddr:
                continue
            if int(conn.raddr.port) != 30000:
                continue
            return FlowKey(
                client=Endpoint(str(conn.laddr.ip), int(conn.laddr.port)),
                server=Endpoint(str(conn.raddr.ip), int(conn.raddr.port)),
            )
        return None

    async def _process_monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            game_pids = self._find_game_pids()
            if self.state == ServiceState.WAITING_RESTART:
                if not game_pids:
                    self._set_state(ServiceState.WAITING_GAME)
                continue
            if not game_pids:
                if self.active_flow is not None:
                    LOGGER.info("game process exited; clearing session")
                self._reset_session()
                self._set_state(ServiceState.WAITING_GAME)
                continue
            flow = self._find_active_flow(game_pids)
            if flow is None:
                if self.active_flow is not None:
                    LOGGER.info("game connection closed; returning to discovery capture")
                    self._reset_session()
                self._set_state(ServiceState.WAITING_CONNECTION)
                continue
            if self.active_flow != flow:
                self._activate_flow(flow)
            if self.active_session and self.active_session.is_live:
                self._set_state(ServiceState.LIVE)
            else:
                self._set_state(ServiceState.WAITING_HANDSHAKE)

    async def _packet_loop(self) -> None:
        while True:
            packet = await self.packet_queue.get()
            if self.state == ServiceState.WAITING_RESTART:
                continue
            flow = self._normalize_flow(packet)
            if flow is None:
                continue
            self.pending_packets[flow].append(packet)
            if self.active_flow == flow and self.active_session is not None:
                self.active_session.process_packet(packet)
                if self.active_session.is_live:
                    self._set_state(ServiceState.LIVE)

    @staticmethod
    def _normalize_flow(packet: CapturedPacket) -> FlowKey | None:
        if packet.src.port == 30000:
            return FlowKey(client=packet.dst, server=packet.src)
        if packet.dst.port == 30000:
            return FlowKey(client=packet.src, server=packet.dst)
        return None

    @staticmethod
    def _pending_sort_key(flow: FlowKey, packet: CapturedPacket) -> tuple[int, int, int]:
        direction_rank = 0 if packet.src == flow.client else 1
        return (direction_rank, int(packet.seq), int(packet.timestamp_ms))

    def _activate_flow(self, flow: FlowKey) -> None:
        LOGGER.info(
            "activating flow %s:%d -> %s:%d",
            flow.client.ip,
            flow.client.port,
            flow.server.ip,
            flow.server.port,
        )
        if self.active_session is not None:
            self.active_session.flush_debug_state()
        pending = sorted(
            list(self.pending_packets.get(flow, ())),
            key=lambda packet: self._pending_sort_key(flow, packet),
        )
        observed_device_names = {packet.device_name for packet in pending}
        self.capture_manager.lock_to_flow(flow, observed_device_names)
        self.active_flow = flow
        self.active_session = SessionPipeline(
            flow=flow,
            session_id=str(uuid.uuid4()),
            registry=self.registry,
            private_key=self.private_key,
            srsa_bridge=self.srsa_bridge,
            name_index=self.name_index,
            multi_phase_dungeon_map=self.multi_phase_dungeon_map,
            merge_multi_phase_enemy_battles=self.config.merge_multi_phase_enemy_battles,
            on_event=self._handle_outbound_event,
            on_debug_message=self._handle_debug_message if self.config.debug_enabled else None,
            on_debug_record=self._handle_debug_record if self.config.debug_enabled else None,
            metrics=self.metrics,
        )
        self._open_log_file(self.active_session.session_id)
        self._open_debug_session_dir(self.active_session.session_id)
        LOGGER.info("replaying %d buffered packets for active flow", len(pending))
        for packet in pending:
            self.active_session.process_packet(packet)

    def _open_log_file(self, session_id: str) -> None:
        if self.log_file is not None:
            self.log_file.close()
        timestamp = datetime.now().strftime("%Y%m%d")
        day_dir = self.config.log_dir / timestamp
        day_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"session_{session_id}.ndjson"
        self.log_file = (day_dir / file_name).open("a", encoding="utf-8")

    def _open_debug_session_dir(self, session_id: str) -> None:
        self.debug_session_dir = None
        self.debug_counters.clear()
        if not self.config.debug_enabled:
            return
        timestamp = datetime.now().strftime("%Y%m%d")
        session_dir = self.config.debug_dir / timestamp / f"session_{session_id}"
        (session_dir / "proto" / "CS_BATTLE_OP").mkdir(parents=True, exist_ok=True)
        (session_dir / "proto" / "SC_SELF_SCENE_INFO").mkdir(parents=True, exist_ok=True)
        (session_dir / "proto" / "SC_SYNC_CHAR_BAG_INFO").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "frame_error").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "session_head").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "undecoded_frame").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "tcp_gap").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "multipack_pending").mkdir(parents=True, exist_ok=True)
        (session_dir / "issues" / "multipack_incomplete").mkdir(parents=True, exist_ok=True)
        self.debug_session_dir = session_dir
        LOGGER.info("debug output -> %s", session_dir)

    def _reset_session(self) -> None:
        if self.active_session is not None:
            self.active_session.flush_debug_state()
        self.active_flow = None
        self.active_session = None
        self.capture_manager.restore_default_filters()
        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None
        self.debug_session_dir = None
        self.debug_counters.clear()

    def _handle_outbound_event(self, event: OutboundEvent) -> None:
        payload = event.as_dict()
        self.batch.append(payload)
        if self.observer is not None and self.observer.on_event is not None:
            self.observer.on_event(payload)
        if self.log_file is not None:
            self.log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.log_file.flush()
        if len(self.batch) >= 128 and self.loop is not None:
            self.loop.create_task(self._flush_batch())

    def _handle_debug_message(self, decoded: DecodedMessage, timestamp_ms: int) -> None:
        if self.debug_session_dir is None or self.active_session is None:
            return
        payload = {
            "type": "debug_proto",
            "session_id": self.active_session.session_id,
            "timestamp_ms": timestamp_ms,
            "direction": decoded.direction,
            "class_name": decoded.class_name,
            "msg_id": decoded.msg_id,
            "head": decoded.head,
            "message": MessageToDict(
                decoded.message,
                preserving_proto_field_name=True,
                use_integers_for_enums=False,
            ),
            "message_enum_ints": MessageToDict(
                decoded.message,
                preserving_proto_field_name=True,
                use_integers_for_enums=True,
            ),
        }
        self._write_debug_json("proto", decoded.class_name, payload, timestamp_ms, decoded.direction)

    def _handle_debug_record(self, payload: dict[str, object]) -> None:
        if self.debug_session_dir is None:
            return
        record_type = str(payload.get("type", "record"))
        if record_type == "debug_frame_error":
            category = "frame_error"
        elif record_type == "debug_session_head":
            category = "session_head"
        elif record_type == "debug_tcp_gap":
            category = "tcp_gap"
        elif record_type == "debug_multipack_pending":
            category = "multipack_pending"
        elif record_type == "debug_multipack_incomplete":
            category = "multipack_incomplete"
        else:
            category = "undecoded_frame"
        direction = str(payload.get("direction", "na"))
        timestamp_ms = int(payload.get("timestamp_ms", 0))
        self._write_debug_json("issues", category, payload, timestamp_ms, direction)

    def _write_debug_json(
        self,
        top_level: str,
        bucket: str,
        payload: dict[str, object],
        timestamp_ms: int,
        direction: str,
    ) -> None:
        if self.debug_session_dir is None:
            return
        key = (top_level, bucket)
        self.debug_counters[key] += 1
        index = self.debug_counters[key]
        target_dir = self.debug_session_dir / top_level / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{index:06d}_{timestamp_ms}_{direction}.json"
        path = target_dir / file_name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _batch_flush_loop(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        if not self.batch:
            return
        payload = {
            "type": "event_batch",
            "session_id": self.active_session.session_id if self.active_session else None,
            "sent_at_ms": int(datetime.now().timestamp() * 1000),
            "events": self.batch[:128],
        }
        del self.batch[:128]
        self.metrics.ws_batches_sent += 1
        await self._broadcast(payload)

    async def _stats_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            stats = self.capture_manager.stats_snapshot()
            if self.observer is not None and self.observer.on_runtime_metrics is not None:
                self.observer.on_runtime_metrics(replace(self.metrics), dict(stats), self.active_flow)
            LOGGER.info(
                "metrics packets=%d queue_drop=%d frames=%d messages=%d events=%d batches=%d ps_drop=%d active_flow=%s",
                self.metrics.packets_seen,
                self.metrics.packets_dropped_queue,
                self.metrics.frames_decoded,
                self.metrics.messages_decoded,
                self.metrics.outbound_events_emitted,
                self.metrics.ws_batches_sent,
                stats["ps_drop"],
                self.active_flow,
            )
