from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class CombatPlayerSummary:
    battle_inst_id: int
    display_name: str
    templateid: str | None
    squad_index: int
    total_damage: float = 0.0
    max_damage: float = 0.0
    crit_count: int = 0
    hit_count: int = 0

    @property
    def crit_rate(self) -> float:
        if self.hit_count <= 0:
            return 0.0
        return (self.crit_count / self.hit_count) * 100.0

    @property
    def damage_percent(self) -> float:
        return 0.0


@dataclass(slots=True)
class CombatRecord:
    file_path: Path
    record_index: int
    started_at_ms: int
    label: str
    players: list[CombatPlayerSummary] = field(default_factory=list)
    total_damage: float = 0.0
    duration_ms: int = 0

    @property
    def dps(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.total_damage / (self.duration_ms / 1000.0)


def load_combat_records(log_dir: Path) -> list[CombatRecord]:
    records: list[CombatRecord] = []
    for path in sorted(log_dir.rglob("session_*.ndjson"), reverse=True):
        if path.stat().st_size == 0:
            continue
        records.extend(_parse_log_file(path))
    return sorted(records, key=lambda item: item.started_at_ms, reverse=True)


def _parse_log_file(path: Path) -> list[CombatRecord]:
    records: list[CombatRecord] = []
    current_squad: dict[int, CombatPlayerSummary] = {}
    current_record: _MutableRecord | None = None
    record_index = 0

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type", ""))
        timestamp_ms = int(event.get("timestamp_ms", 0) or 0)

        members = _extract_squad_members(event_type, event)
        if members is not None:
            next_squad = {
                int(member["battle_inst_id"]): CombatPlayerSummary(
                    battle_inst_id=int(member["battle_inst_id"]),
                    display_name=str(member.get("display_name") or f"#{member['battle_inst_id']}"),
                    templateid=str(member.get("templateid")) if member.get("templateid") is not None else None,
                    squad_index=int(member.get("squad_index", 0)),
                )
                for member in members
            }
            if _squad_changed(current_squad, next_squad):
                if current_record is not None:
                    maybe_record = current_record.freeze()
                    if maybe_record is not None:
                        records.append(maybe_record)
                current_record = None
            current_squad = next_squad
            continue

        if event_type == "BattleOpModifyBattleState" and bool(event.get("is_in_battle", False)):
            if current_squad:
                if current_record is not None:
                    maybe_record = current_record.freeze()
                    if maybe_record is not None:
                        records.append(maybe_record)
                record_index += 1
                current_record = _MutableRecord(
                    file_path=path,
                    record_index=record_index,
                    started_at_ms=timestamp_ms,
                    squad=_clone_squad(current_squad),
                )
            continue

        damage_event = _extract_damage_event(event_type, event)
        if damage_event is None:
            continue
        attacker = damage_event.get("attacker", {})
        attacker_id = attacker.get("battle_inst_id")
        if attacker_id is None:
            continue
        attacker_id = int(attacker_id)
        if attacker_id not in current_squad:
            continue
        if current_record is None:
            record_index += 1
            current_record = _MutableRecord(
                file_path=path,
                record_index=record_index,
                started_at_ms=timestamp_ms,
                squad=_clone_squad(current_squad),
            )
        current_record.apply_damage(damage_event, timestamp_ms)

    if current_record is not None:
        maybe_record = current_record.freeze()
        if maybe_record is not None:
            records.append(maybe_record)
    return records


def _clone_squad(source: dict[int, CombatPlayerSummary]) -> dict[int, CombatPlayerSummary]:
    return {
        battle_inst_id: CombatPlayerSummary(
            battle_inst_id=player.battle_inst_id,
            display_name=player.display_name,
            templateid=player.templateid,
            squad_index=player.squad_index,
        )
        for battle_inst_id, player in source.items()
    }


def _squad_changed(previous: dict[int, CombatPlayerSummary], current: dict[int, CombatPlayerSummary]) -> bool:
    return sorted(previous) != sorted(current)


def _extract_squad_members(event_type: str, event: dict[str, object]) -> list[dict[str, object]] | None:
    if event_type == "squad_update":
        members = event.get("members", [])
        return members if isinstance(members, list) else None
    if event_type != "SC_SELF_SCENE_INFO":
        return None
    char_list = event.get("char_list", [])
    if not isinstance(char_list, list):
        return []
    members: list[dict[str, object]] = []
    for index, item in enumerate(char_list):
        if not isinstance(item, dict) or item.get("battle_inst_id") is None:
            continue
        members.append(
            {
                "battle_inst_id": item.get("battle_inst_id"),
                "display_name": item.get("display_name") or item.get("templateid"),
                "templateid": item.get("templateid"),
                "squad_index": item.get("squad_index", index),
            }
        )
    return members


def _extract_damage_event(event_type: str, event: dict[str, object]) -> dict[str, object] | None:
    if event_type == "damage":
        return event
    if event_type != "BattleOpTriggerAction":
        return None
    action = event.get("action")
    if not isinstance(action, dict):
        return None
    action_type = action.get("action_type")
    if action_type not in {"BattleActionDamage", 1}:
        return None
    damage_action = action.get("damage_action")
    if not isinstance(damage_action, dict):
        return None
    details = damage_action.get("details", [])
    if not isinstance(details, list):
        return None
    normalized_details: list[dict[str, object]] = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        value = float(detail.get("value", 0.0) or 0.0)
        normalized_details.append(
            {
                "target_battle_inst_id": int(detail.get("target_id", 0) or 0) or None,
                "is_crit": bool(detail.get("is_crit", False)),
                "value": value,
                "abs_value": float(detail.get("abs_value", abs(value)) or abs(value)),
                "cur_hp": detail.get("cur_hp"),
            }
        )
    if not normalized_details:
        return None
    return {
        "attacker": {
            "battle_inst_id": int(damage_action.get("attacker_id", 0) or 0) or None,
        },
        "details": normalized_details,
    }


@dataclass(slots=True)
class _MutableRecord:
    file_path: Path
    record_index: int
    started_at_ms: int
    squad: dict[int, CombatPlayerSummary]
    first_damage_ms: int | None = None
    last_damage_ms: int | None = None
    total_damage: float = 0.0

    def apply_damage(self, event: dict[str, object], timestamp_ms: int) -> None:
        attacker = event.get("attacker", {})
        attacker_id = int(attacker["battle_inst_id"])
        player = self.squad[attacker_id]
        details = event.get("details", [])
        damage = 0.0
        hit_count = 0
        crit_count = 0
        for detail in details:
            if not isinstance(detail, dict):
                continue
            value = float(detail.get("abs_value", detail.get("value", 0.0)) or 0.0)
            damage += abs(value)
            hit_count += 1
            crit_count += 1 if detail.get("is_crit") else 0
        if damage <= 0:
            return
        player.total_damage += damage
        player.max_damage = max(player.max_damage, damage)
        player.hit_count += max(hit_count, 1)
        player.crit_count += crit_count
        self.total_damage += damage
        self.first_damage_ms = timestamp_ms if self.first_damage_ms is None else min(self.first_damage_ms, timestamp_ms)
        self.last_damage_ms = timestamp_ms if self.last_damage_ms is None else max(self.last_damage_ms, timestamp_ms)

    def freeze(self) -> CombatRecord | None:
        if self.total_damage <= 0:
            return None
        started_at_ms = self.first_damage_ms or self.started_at_ms
        duration_ms = 0
        if self.first_damage_ms is not None and self.last_damage_ms is not None:
            duration_ms = max(1, self.last_damage_ms - self.first_damage_ms)
        label_time = datetime.fromtimestamp(started_at_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        players = sorted(
            self.squad.values(),
            key=lambda item: (-item.total_damage, item.squad_index, item.display_name),
        )
        return CombatRecord(
            file_path=self.file_path,
            record_index=self.record_index,
            started_at_ms=started_at_ms,
            label=f"{label_time} #{self.record_index}",
            players=players,
            total_damage=self.total_damage,
            duration_ms=duration_ms,
        )
