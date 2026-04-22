from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Protocol


class ServiceState(StrEnum):
    WAITING_RESTART = "waiting_restart"
    WAITING_GAME = "waiting_game"
    WAITING_CONNECTION = "waiting_connection"
    WAITING_HANDSHAKE = "waiting_handshake"
    LIVE = "live"


class OverlaySourceType(StrEnum):
    BUILTIN = "builtin"
    URL = "url"
    FILE = "file"


@dataclass(frozen=True, slots=True)
class Endpoint:
    ip: str
    port: int


@dataclass(frozen=True, slots=True)
class FlowKey:
    client: Endpoint
    server: Endpoint


@dataclass(slots=True)
class OverlayGeometry:
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True)
class OverlayEntry:
    id: str
    name: str
    source_type: OverlaySourceType
    source_value: str
    enabled: bool
    locked: bool
    click_through: bool
    opacity: float = 1.0
    scale: float = 1.0
    geometry: OverlayGeometry | None = None


@dataclass(slots=True)
class CapturedPacket:
    timestamp_ms: int
    src: Endpoint
    dst: Endpoint
    seq: int
    payload: bytes
    device_name: str


@dataclass(slots=True)
class EntityInfo:
    battle_inst_id: int
    obj_id: int | None
    templateid: str | None
    entity_type: int | None


@dataclass(slots=True)
class SquadMember:
    battle_inst_id: int
    obj_id: int | None
    templateid: str | None
    display_name: str | None
    is_leader: bool
    squad_index: int


@dataclass(slots=True)
class ActorRefPayload:
    battle_inst_id: int | None
    display_name: str | None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "battle_inst_id": self.battle_inst_id,
            "display_name": self.display_name,
        }


@dataclass(slots=True)
class DamageDetailPayload:
    target_battle_inst_id: int | None
    is_crit: bool
    value: float
    abs_value: float
    cur_hp: float | None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "target_battle_inst_id": self.target_battle_inst_id,
            "is_crit": self.is_crit,
            "value": self.value,
            "abs_value": self.abs_value,
            "cur_hp": self.cur_hp,
        }


@dataclass(slots=True)
class DamageEvent:
    session_id: str
    timestamp_ms: int
    seq_id: int | None
    client_tick_tms: int | None
    skill_template_id: int | None
    attacker: ActorRefPayload
    target: ActorRefPayload
    details: list[DamageDetailPayload] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "type": "damage",
            "session_id": self.session_id,
            "timestamp_ms": self.timestamp_ms,
            "seq_id": self.seq_id,
            "client_tick_tms": self.client_tick_tms,
            "skill_template_id": self.skill_template_id,
            "attacker": self.attacker.as_dict(),
            "target": self.target.as_dict(),
            "details": [detail.as_dict() for detail in self.details],
        }


@dataclass(slots=True)
class BattleLogEvent:
    session_id: str
    timestamp_ms: int
    event_type: str
    payload: dict[str, object | None]

    def as_dict(self) -> dict[str, object | None]:
        return {
            "type": self.event_type,
            "session_id": self.session_id,
            "timestamp_ms": self.timestamp_ms,
            **self.payload,
        }


@dataclass(slots=True)
class SquadMemberPayload:
    battle_inst_id: int
    templateid: str | None
    display_name: str | None
    is_leader: bool
    squad_index: int

    def as_dict(self) -> dict[str, object | None]:
        return {
            "battle_inst_id": self.battle_inst_id,
            "templateid": self.templateid,
            "display_name": self.display_name,
            "is_leader": self.is_leader,
            "squad_index": self.squad_index,
        }


class OutboundEvent(Protocol):
    def as_dict(self) -> dict[str, object]:
        ...


@dataclass(slots=True)
class SquadUpdateEvent:
    session_id: str
    timestamp_ms: int
    members: list[SquadMemberPayload] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "type": "squad_update",
            "session_id": self.session_id,
            "timestamp_ms": self.timestamp_ms,
            "members": [member.as_dict() for member in self.members],
        }


@dataclass(slots=True)
class RuntimeMetrics:
    packets_seen: int = 0
    packets_dropped_queue: int = 0
    frames_decoded: int = 0
    messages_decoded: int = 0
    outbound_events_emitted: int = 0
    ws_batches_sent: int = 0


@dataclass(slots=True)
class ServiceObserver:
    on_state_change: Callable[[ServiceState, str | None, FlowKey | None], None] | None = None
    on_runtime_metrics: Callable[[RuntimeMetrics, dict[str, int], FlowKey | None], None] | None = None
    on_event: Callable[[dict[str, object]], None] | None = None
