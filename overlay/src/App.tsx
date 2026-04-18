import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { getAvatarUrl } from './avatar';
import { DamageOverlay } from './components/DamageOverlay';
import {
  BattleOpModifyBattleStateEvent,
  BattleOpTriggerActionEvent,
  DamageEvent,
  EventBatch,
  FooterStatus,
  HelloEvent,
  OverlayEvent,
  OverlayMessage,
  OverlayState,
  PlayerStats,
  SquadMember,
  SquadUpdateEvent,
} from './types';

const createInitialState = (): OverlayState => ({
  players: {},
  totalDamage: 0,
  damageStartTime: null,
  lastDamageTime: null,
  battleStateStartTime: null,
  battleElapsedMs: 0,
  currentTime: Date.now(),
  isInBattle: false,
  hasSquad: false,
  footerStatus: 'waiting_client',
  serviceState: 'waiting_game',
  sessionId: null,
});

const getWsUrl = (): string => {
  const params = new URLSearchParams(window.location.search);
  const wsPort = params.get('wsPort') ?? '29325';
  return `ws://127.0.0.1:${wsPort}/ws`;
};

const getFooterStatusFromService = (
  serviceState: string,
  hasSquad: boolean,
  isInBattle: boolean,
  previousStatus: FooterStatus,
): FooterStatus => {
  if (serviceState === 'waiting_game') {
    return 'waiting_client';
  }
  if (serviceState === 'waiting_restart') {
    return 'waiting_restart';
  }
  if (serviceState === 'waiting_connection' || serviceState === 'waiting_handshake') {
    return 'waiting_login';
  }
  if (!hasSquad) {
    return 'waiting_battle';
  }
  if (isInBattle) {
    return 'in_battle';
  }
  if (previousStatus === 'battle_ended') {
    return 'battle_ended';
  }
  return 'waiting_battle';
};

const createPlayer = (
  member: SquadMember,
  existing: PlayerStats | undefined,
  preserveStats: boolean,
  fallbackTime: number,
): PlayerStats => {
  const avatarUrl = getAvatarUrl(member.templateid) ?? existing?.avatarUrl ?? null;
  return {
    id: String(member.battle_inst_id),
    battleInstId: member.battle_inst_id,
    templateId: member.templateid ?? existing?.templateId ?? null,
    name: member.display_name ?? existing?.name ?? `#${member.battle_inst_id}`,
    avatarUrl,
    totalDamage: preserveStats ? (existing?.totalDamage ?? 0) : 0,
    maxDamage: preserveStats ? (existing?.maxDamage ?? 0) : 0,
    critCount: preserveStats ? (existing?.critCount ?? 0) : 0,
    hitCount: preserveStats ? (existing?.hitCount ?? 0) : 0,
    lastUpdate: preserveStats ? (existing?.lastUpdate ?? fallbackTime) : fallbackTime,
    squadIndex: member.squad_index,
    isLeader: member.is_leader,
  };
};

const sameSquadIds = (players: Record<string, PlayerStats>, members: SquadMember[]): boolean => {
  const previousIds = Object.values(players)
    .map((player) => player.battleInstId)
    .sort((a, b) => a - b);
  const incomingIds = members
    .map((member) => member.battle_inst_id)
    .sort((a, b) => a - b);
  if (previousIds.length !== incomingIds.length) {
    return false;
  }
  return previousIds.every((value, index) => value === incomingIds[index]);
};

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const asBoolean = (value: unknown): boolean => Boolean(value);

const deriveSquadUpdate = (event: OverlayEvent): SquadUpdateEvent | null => {
  if (event.type === 'squad_update') {
    return event;
  }
  if (event.type !== 'SC_SELF_SCENE_INFO') {
    return null;
  }
  return {
    type: 'squad_update',
    session_id: event.session_id,
    timestamp_ms: event.timestamp_ms,
    members: event.char_list
      .filter((item) => item && item.battle_inst_id !== undefined && item.battle_inst_id !== null)
      .map((item, index) => ({
        battle_inst_id: item.battle_inst_id,
        templateid: item.templateid ?? null,
        display_name: item.display_name ?? item.templateid ?? null,
        is_leader: Boolean(item.is_leader),
        squad_index: item.squad_index ?? index,
      })),
  };
};

const deriveDamageEvent = (event: OverlayEvent): DamageEvent | null => {
  if (event.type === 'damage') {
    return event;
  }
  if (event.type !== 'BattleOpTriggerAction') {
    return null;
  }
  const trigger = event as BattleOpTriggerActionEvent;
  const action = asRecord(trigger.action);
  if (!action) {
    return null;
  }
  if (action.action_type !== 'BattleActionDamage' && action.action_type !== 1) {
    return null;
  }
  const damageAction = asRecord(action.damage_action);
  if (!damageAction) {
    return null;
  }
  const detailList = Array.isArray(damageAction.details) ? damageAction.details : [];
  const details = detailList
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((detail) => {
      const rawValue = asNumber(detail.value) ?? 0;
      const absValue = asNumber(detail.abs_value) ?? Math.abs(rawValue);
      return {
        target_battle_inst_id: asNumber(detail.target_id),
        is_crit: asBoolean(detail.is_crit),
        value: rawValue,
        abs_value: absValue,
        cur_hp: asNumber(detail.cur_hp),
      };
    });
  if (details.length === 0) {
    return null;
  }
  const sourceTemplate = asRecord(damageAction.original_source_template_id);
  return {
    type: 'damage',
    session_id: trigger.session_id,
    timestamp_ms: trigger.timestamp_ms,
    seq_id: trigger.seq_id,
    client_tick_tms: trigger.client_tick_tms,
    skill_template_id: sourceTemplate ? asNumber(sourceTemplate.int_id) : null,
    attacker: {
      battle_inst_id: asNumber(damageAction.attacker_id),
      display_name: null,
    },
    target: {
      battle_inst_id: details[0]?.target_battle_inst_id ?? null,
      display_name: null,
    },
    details,
  };
};

export default function App() {
  const [state, setState] = useState<OverlayState>(createInitialState);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const applySquadUpdate = useEffectEvent((event: SquadUpdateEvent) => {
    setState((prev) => {
      const preserveStats = prev.hasSquad && sameSquadIds(prev.players, event.members);
      const fallbackTime = event.timestamp_ms || prev.currentTime;
      const nextPlayers: Record<string, PlayerStats> = {};

      for (const member of event.members) {
        nextPlayers[String(member.battle_inst_id)] = createPlayer(
          member,
          preserveStats ? prev.players[String(member.battle_inst_id)] : undefined,
          preserveStats,
          fallbackTime,
        );
      }

      return {
        ...prev,
        players: nextPlayers,
        totalDamage: preserveStats ? prev.totalDamage : 0,
        damageStartTime: preserveStats ? prev.damageStartTime : null,
        lastDamageTime: preserveStats ? prev.lastDamageTime : null,
        battleStateStartTime: preserveStats ? prev.battleStateStartTime : null,
        battleElapsedMs: preserveStats ? prev.battleElapsedMs : 0,
        currentTime: fallbackTime,
        isInBattle: preserveStats ? prev.isInBattle : false,
        hasSquad: event.members.length > 0,
        footerStatus: preserveStats
          ? getFooterStatusFromService(prev.serviceState, event.members.length > 0, prev.isInBattle, prev.footerStatus)
          : getFooterStatusFromService(prev.serviceState, event.members.length > 0, false, 'waiting_battle'),
        sessionId: event.session_id,
      };
    });
  });

  const applyDamage = useEffectEvent((event: DamageEvent) => {
    const attackerId = event.attacker.battle_inst_id;
    if (attackerId === null) {
      return;
    }

    const actorKey = String(attackerId);
    const damage = event.details.reduce((sum, detail) => sum + Math.abs(detail.abs_value ?? detail.value ?? 0), 0);
    if (damage <= 0) {
      return;
    }

    setState((prev) => {
      const existing = prev.players[actorKey];
      if (!existing) {
        return prev;
      }

      const now = event.timestamp_ms || Date.now();
      const hitCount = Math.max(event.details.length, 1);
      const critCount = event.details.reduce((sum, detail) => sum + (detail.is_crit ? 1 : 0), 0);

      return {
        ...prev,
        players: {
          ...prev.players,
          [actorKey]: {
            ...existing,
            name: event.attacker.display_name ?? existing.name,
            totalDamage: existing.totalDamage + damage,
            maxDamage: Math.max(existing.maxDamage, damage),
            critCount: existing.critCount + critCount,
            hitCount: existing.hitCount + hitCount,
            lastUpdate: now,
          },
        },
        totalDamage: prev.totalDamage + damage,
        damageStartTime: prev.damageStartTime ?? now,
        lastDamageTime: now,
        currentTime: now,
        sessionId: event.session_id,
      };
    });
  });

  const applyBattleState = useEffectEvent((event: BattleOpModifyBattleStateEvent) => {
    setState((prev) => {
      const timestamp = event.timestamp_ms || Date.now();

      if (event.is_in_battle) {
        if (prev.isInBattle) {
          return {
            ...prev,
            currentTime: timestamp,
            footerStatus: 'in_battle',
            sessionId: event.session_id,
          };
        }
        const resetPlayers: Record<string, PlayerStats> = {};
        for (const player of Object.values(prev.players) as PlayerStats[]) {
          resetPlayers[player.id] = {
            ...player,
            totalDamage: 0,
            maxDamage: 0,
            critCount: 0,
            hitCount: 0,
            lastUpdate: timestamp,
          };
        }
        return {
          ...prev,
          players: resetPlayers,
          totalDamage: 0,
          damageStartTime: null,
          lastDamageTime: null,
          battleStateStartTime: timestamp,
          battleElapsedMs: 0,
          currentTime: timestamp,
          isInBattle: true,
          footerStatus: 'in_battle',
          sessionId: event.session_id,
        };
      }

      const elapsedMs =
        prev.isInBattle && prev.battleStateStartTime !== null
          ? prev.battleElapsedMs + Math.max(0, timestamp - prev.battleStateStartTime)
          : prev.battleElapsedMs;

      return {
        ...prev,
        battleStateStartTime: null,
        battleElapsedMs: elapsedMs,
        currentTime: timestamp,
        isInBattle: false,
        footerStatus: getFooterStatusFromService(prev.serviceState, prev.hasSquad, false, 'battle_ended'),
        sessionId: event.session_id,
      };
    });
  });

  const handleEvent = useEffectEvent((event: OverlayEvent) => {
    const squadEvent = deriveSquadUpdate(event);
    if (squadEvent) {
      applySquadUpdate(squadEvent);
      if (event.type === 'SC_SELF_SCENE_INFO') {
        return;
      }
    }

    const damageEvent = deriveDamageEvent(event);
    if (damageEvent) {
      applyDamage(damageEvent);
      return;
    }
    if (event.type === 'BattleOpModifyBattleState') {
      applyBattleState(event);
    }
  });

  const handleMessage = useEffectEvent((message: OverlayMessage) => {
    if (message.type === 'hello') {
      const hello = message as HelloEvent;
      setState((prev) => {
        const shouldReset = prev.sessionId !== null && hello.session_id !== prev.sessionId;
        const base = shouldReset ? createInitialState() : prev;
        return {
          ...base,
          currentTime: Date.now(),
          serviceState: hello.state,
          footerStatus: getFooterStatusFromService(
            hello.state,
            base.hasSquad,
            base.isInBattle,
            base.footerStatus,
          ),
          sessionId: hello.session_id,
        };
      });
      return;
    }

    if (message.type === 'event_batch') {
      const batch = message as EventBatch;
      for (const event of batch.events) {
        handleEvent(event);
      }
      return;
    }

    handleEvent(message);
  });

  useEffect(() => {
    let closed = false;

    const connect = () => {
      if (closed) {
        return;
      }

      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onmessage = (msg) => {
        try {
          handleMessage(JSON.parse(msg.data) as OverlayMessage);
        } catch (error) {
          console.error('Failed to parse overlay WS message', error);
        }
      };

      ws.onclose = () => {
        if (closed) {
          return;
        }
        reconnectTimerRef.current = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setState((prev) => {
        if (!prev.isInBattle) {
          return prev;
        }
        return {
          ...prev,
          currentTime: Date.now(),
        };
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="h-screen w-screen overflow-hidden bg-transparent">
      <DamageOverlay state={state} />
    </div>
  );
}
