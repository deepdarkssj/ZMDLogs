import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import BuffOverlay from './components/BuffOverlay';
import {
  AssignedItem,
  BattleOpModifyBattleStateEvent,
  BattleOpTriggerActionEvent,
  BuffConfigEntry,
  BuffConfigResolved,
  BuffLayer,
  BuffTimer,
  EventBatch,
  HelloEvent,
  OverlayMessage,
  TriggerActionPayload,
} from './types';

import configText from '../OverlayBuff.json?raw';
import comboSkillConfigText from '../../overlay_comboskill/ComboSkillOverlay.json?raw';
import ultimateSkillText from '../../overlay_comboskill/ultimateskill.json?raw';

const PAUSE_DURATION_MS = 500;
const PAUSE_RETRIGGER_IGNORE_MS = 3000;
const ULTIMATE_PAUSE_RETRIGGER_IGNORE_MS = 5000;

const getWsUrl = (): string => {
  const params = new URLSearchParams(window.location.search);
  const wsPort = params.get('wsPort') ?? '29325';
  return `ws://127.0.0.1:${wsPort}/ws`;
};

const getInitialLocked = (): boolean => {
  const params = new URLSearchParams(window.location.search);
  return params.get('locked') === '1';
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

const asIdString = (value: unknown): string | null => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(Math.trunc(value));
  }
  return null;
};

const normalizeConfig = (
  rawText: string,
): { entries: Map<number, BuffConfigResolved>; aliasMap: Map<number, number> } => {
  const parsed = JSON.parse(rawText.replace(/\r/g, '')) as Record<string, BuffConfigEntry>;
  const entries = new Map<number, BuffConfigResolved>();
  const aliasMap = new Map<number, number>();
  for (const [key, value] of Object.entries(parsed)) {
    const configId = Number(key);
    if (!Number.isFinite(configId)) {
      continue;
    }
    const aliases = [configId, ...(Array.isArray(value.Group) ? value.Group.map(Number).filter(Number.isFinite) : [])];
    const resolved: BuffConfigResolved = {
      ...value,
      configId,
      aliases,
    };
    entries.set(configId, resolved);
    for (const alias of aliases) {
      aliasMap.set(alias, configId);
    }
  }
  return { entries, aliasMap };
};

const normalizePauseSkillIds = (rawText: string): Set<number> => {
  const parsed = JSON.parse(rawText.replace(/\r/g, '')) as Record<
    string,
    { reset_skill?: number[] | null }
  >;
  const result = new Set<number>();
  for (const [key, value] of Object.entries(parsed)) {
    const skillId = Number(key);
    if (Number.isFinite(skillId)) {
      result.add(skillId);
    }
    for (const resetSkillId of Array.isArray(value?.reset_skill) ? value.reset_skill : []) {
      if (typeof resetSkillId === 'number' && Number.isFinite(resetSkillId)) {
        result.add(resetSkillId);
      }
    }
  }
  return result;
};

const normalizeUltimatePauseConfig = (rawText: string): Map<number, number> => {
  const parsed = JSON.parse(rawText.replace(/\r/g, '')) as Record<string, number>;
  const result = new Map<number, number>();
  for (const [key, value] of Object.entries(parsed)) {
    const skillId = Number(key);
    if (Number.isFinite(skillId) && typeof value === 'number' && Number.isFinite(value) && value > 0) {
      result.set(skillId, value);
    }
  }
  return result;
};

const resolveAssignedValue = (assignedItems: AssignedItem[] | null | undefined, key: string | undefined, fallback: number): number => {
  if (!key || !Array.isArray(assignedItems)) {
    return fallback;
  }
  const matched = assignedItems.find((item) => item?.target_key === key);
  if (!matched) {
    return fallback;
  }
  const candidates = [matched.numeric_value, matched.float_value, matched.int_value];
  for (const candidate of candidates) {
    const value = asNumber(candidate);
    if (value !== null) {
      return value;
    }
  }
  return fallback;
};

const createLayer = (buffInstId: string, totalMs: number, nowMs: number): BuffLayer => ({
  buffInstId,
  totalMs,
  startedAt: nowMs,
  expiresAt: nowMs + totalMs,
  pausedUntilMs: null,
  pausedRemainingMs: null,
});

const getLayerRemaining = (layer: BuffLayer, nowMs: number): number => {
  if (layer.pausedUntilMs && layer.pausedRemainingMs !== null && layer.pausedRemainingMs !== undefined && nowMs < layer.pausedUntilMs) {
    return layer.pausedRemainingMs;
  }
  if (nowMs >= layer.expiresAt) {
    return 0;
  }
  return Math.max(0, layer.expiresAt - nowMs);
};

const settleLayerPause = (layer: BuffLayer, nowMs: number): BuffLayer => {
  if (!layer.pausedUntilMs || layer.pausedRemainingMs === null || layer.pausedRemainingMs === undefined) {
    return layer;
  }
  if (nowMs < layer.pausedUntilMs) {
    return layer;
  }
  return {
    ...layer,
    startedAt: nowMs - (layer.totalMs - layer.pausedRemainingMs),
    expiresAt: nowMs + layer.pausedRemainingMs,
    pausedUntilMs: null,
    pausedRemainingMs: null,
  };
};

const pruneTimers = (timers: BuffTimer[], nowMs: number): BuffTimer[] =>
  timers
    .map((timer) => ({
      ...timer,
      layers: timer.layers.map((layer) => settleLayerPause(layer, nowMs)).filter((layer) => nowMs < layer.expiresAt),
    }))
    .filter((timer) => timer.layers.length > 0);

const refreshLayers = (layers: BuffLayer[], totalMs: number, nowMs: number): BuffLayer[] =>
  layers.map((layer) => {
    const settled = settleLayerPause(layer, nowMs);
    return {
      ...settled,
      totalMs,
      startedAt: nowMs,
      expiresAt: nowMs + totalMs,
      pausedUntilMs: null,
      pausedRemainingMs: null,
    };
  });

const pauseTimers = (timers: BuffTimer[], pauseMs: number, nowMs: number): BuffTimer[] =>
  timers.map((timer) => ({
    ...timer,
    layers: timer.layers.map((layer) => {
      const settled = settleLayerPause(layer, nowMs);
      const remainingMs = getLayerRemaining(settled, nowMs);
      if (remainingMs <= 0) {
        return settled;
      }
      const nextPausedUntilMs =
        settled.pausedUntilMs && nowMs < settled.pausedUntilMs
          ? settled.pausedUntilMs + pauseMs
          : nowMs + pauseMs;
      return {
        ...settled,
        pausedUntilMs: nextPausedUntilMs,
        pausedRemainingMs: remainingMs,
      };
    }),
  }));

const createLayers = (buffInstId: string, totalMs: number, nowMs: number, count: number): BuffLayer[] =>
  Array.from({ length: Math.max(1, count) }, () => createLayer(buffInstId, totalMs, nowMs));

const updateTimersForCreate = (
  timers: BuffTimer[],
  config: BuffConfigResolved,
  matchedBuffNumId: number,
  targetId: string,
  buffInstId: string,
  assignedItems: AssignedItem[] | null | undefined,
  nowMs: number,
): BuffTimer[] => {
  const totalMs = Math.max(
    0,
    Math.round(resolveAssignedValue(assignedItems, config.duration.key, config.duration.default) * 1000),
  );
  const stackCount = Math.max(
    1,
    Math.round(resolveAssignedValue(assignedItems, config.number?.key, config.number?.default ?? 1)),
  );
  const maxStacks = Math.max(
    1,
    Math.round(
      resolveAssignedValue(
        assignedItems,
        config.max_stack?.key,
        typeof config.max_stack?.default === 'number' ? config.max_stack.default : 1,
      ),
    ),
  );
  const mode = config.max_stack?.mode ?? 'refresh';
  const existingIndex = timers.findIndex((timer) => timer.configId === config.configId);
  if (existingIndex < 0) {
    return [
      ...timers,
      {
        configId: config.configId,
        matchedBuffNumId,
        targetId,
        text: config.text,
        noticeTimeMs: Math.max(0, Math.round((config.notice_time ?? 0) * 1000)),
        mode,
        maxStacks,
        layers: createLayers(buffInstId, totalMs, nowMs, Math.min(stackCount, maxStacks)),
      },
    ];
  }

  const existing = timers[existingIndex];
  if (existing.targetId !== targetId) {
    return timers;
  }

  let nextLayers = existing.layers.filter((layer) => layer.buffInstId !== buffInstId);
  const nextCreatedLayers = createLayers(buffInstId, totalMs, nowMs, stackCount);
  if (mode === 'single') {
    nextLayers = [...nextLayers, ...nextCreatedLayers]
      .sort((left, right) => right.startedAt - left.startedAt)
      .slice(0, maxStacks);
  } else {
    nextLayers = refreshLayers([...nextLayers, ...nextCreatedLayers].slice(0, maxStacks), totalMs, nowMs);
  }

  const nextTimer: BuffTimer = {
    ...existing,
    matchedBuffNumId,
    noticeTimeMs: Math.max(0, Math.round((config.notice_time ?? 0) * 1000)),
    mode,
    maxStacks,
    layers: nextLayers,
  };
  return timers.map((timer, index) => (index === existingIndex ? nextTimer : timer));
};

const updateTimersForFinish = (timers: BuffTimer[], targetId: string, buffInstId: string): BuffTimer[] =>
  timers
    .map((timer) => {
      if (timer.targetId !== targetId) {
        return timer;
      }
      return {
        ...timer,
        layers: timer.layers.filter((layer) => layer.buffInstId !== buffInstId),
      };
    })
    .filter((timer) => timer.layers.length > 0);

export default function App() {
  const normalizedConfig = useMemo(() => normalizeConfig(configText), []);
  const pauseSkillIds = useMemo(() => normalizePauseSkillIds(comboSkillConfigText), []);
  const ultimatePauseConfig = useMemo(() => normalizeUltimatePauseConfig(ultimateSkillText), []);
  const [locked, setLocked] = useState(getInitialLocked);
  const [timers, setTimers] = useState<BuffTimer[]>([]);
  const [nowMs, setNowMs] = useState(Date.now());
  const [sessionId, setSessionId] = useState<string | null>(null);
  const timersRef = useRef<BuffTimer[]>([]);
  const comboPauseHistoryRef = useRef<Map<number, number>>(new Map());
  const ultimatePauseHistoryRef = useRef<Map<number, number>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const applyCreateBuff = useEffectEvent((event: BattleOpTriggerActionEvent) => {
    const action = event.action as TriggerActionPayload;
    const details = action.create_buff_action?.details;
    if (!Array.isArray(details)) {
      return;
    }
    const timestampMs = event.timestamp_ms || Date.now();
    let nextTimers = pruneTimers(timersRef.current, timestampMs);
    for (const detail of details) {
      const matchedBuffNumId = asNumber(detail.buff_num_id);
      const targetId = asIdString(detail.target_id);
      const buffInstId = asIdString(detail.buff_inst_id);
      if (matchedBuffNumId === null || targetId === null || buffInstId === null) {
        continue;
      }
      const configId = normalizedConfig.aliasMap.get(matchedBuffNumId);
      if (configId === undefined) {
        continue;
      }
      const config = normalizedConfig.entries.get(configId);
      if (!config) {
        continue;
      }
      nextTimers = updateTimersForCreate(
        nextTimers,
        config,
        matchedBuffNumId,
        targetId,
        buffInstId,
        detail.assigned_items,
        timestampMs,
      );
    }
    timersRef.current = nextTimers;
    setTimers(nextTimers);
  });

  const applyFinishBuff = useEffectEvent((event: BattleOpTriggerActionEvent) => {
    const action = event.action as TriggerActionPayload;
    const finishBuffs = action.finish_buff_action?.finish_buffs;
    if (!Array.isArray(finishBuffs)) {
      return;
    }
    const timestampMs = event.timestamp_ms || Date.now();
    let nextTimers = pruneTimers(timersRef.current, timestampMs);
    for (const detail of finishBuffs) {
      const targetId = asIdString(detail.target_id);
      const buffInstId = asIdString(detail.buff_inst_id);
      if (targetId === null || buffInstId === null) {
        continue;
      }
      nextTimers = updateTimersForFinish(nextTimers, targetId, buffInstId);
    }
    timersRef.current = nextTimers;
    setTimers(nextTimers);
  });

  const applyPauseSkill = useEffectEvent((event: BattleOpTriggerActionEvent) => {
    if ((event.template_type ?? '').toLowerCase() !== 'skill') {
      return;
    }
    const templateIntId = asNumber(event.template_int_id);
    if (templateIntId === null) {
      return;
    }
    const timestampMs = event.timestamp_ms || Date.now();
    let nextTimers = pruneTimers(timersRef.current, timestampMs);
    let changed = false;

    if (pauseSkillIds.has(templateIntId)) {
      const lastComboPauseAt = comboPauseHistoryRef.current.get(templateIntId);
      if (lastComboPauseAt === undefined || timestampMs - lastComboPauseAt >= PAUSE_RETRIGGER_IGNORE_MS) {
        comboPauseHistoryRef.current.set(templateIntId, timestampMs);
        nextTimers = pauseTimers(nextTimers, PAUSE_DURATION_MS, timestampMs);
        changed = true;
      }
    }

    const ultimatePauseSeconds = ultimatePauseConfig.get(templateIntId);
    if (ultimatePauseSeconds) {
      const lastUltimatePauseAt = ultimatePauseHistoryRef.current.get(templateIntId);
      if (
        lastUltimatePauseAt === undefined ||
        timestampMs - lastUltimatePauseAt >= ULTIMATE_PAUSE_RETRIGGER_IGNORE_MS
      ) {
        ultimatePauseHistoryRef.current.set(templateIntId, timestampMs);
        nextTimers = pauseTimers(nextTimers, Math.round(ultimatePauseSeconds * 1000), timestampMs);
        changed = true;
      }
    }

    if (!changed) {
      return;
    }
    timersRef.current = nextTimers;
    setTimers(nextTimers);
  });

  const handleMessage = useEffectEvent((message: OverlayMessage) => {
    if (message.type === 'hello') {
      const hello = message as HelloEvent;
      if (hello.session_id !== sessionId) {
        setSessionId(hello.session_id);
        comboPauseHistoryRef.current.clear();
        ultimatePauseHistoryRef.current.clear();
        timersRef.current = [];
        setTimers([]);
      }
      return;
    }
    if (message.type === 'event_batch') {
      for (const event of (message as EventBatch).events) {
        handleMessage(event as OverlayMessage);
      }
      return;
    }
    if (message.type === 'BattleOpModifyBattleState') {
      const event = message as BattleOpModifyBattleStateEvent;
      if (!event.is_in_battle) {
        comboPauseHistoryRef.current.clear();
        ultimatePauseHistoryRef.current.clear();
        timersRef.current = [];
        setTimers([]);
      }
      return;
    }
    if (message.type !== 'BattleOpTriggerAction') {
      return;
    }
    const event = message as BattleOpTriggerActionEvent;
    applyPauseSkill(event);
    const actionType = (event.action as TriggerActionPayload).action_type;
    if (actionType === 'BattleActionCreateBuff') {
      applyCreateBuff(event);
    } else if (actionType === 'BattleActionFinishBuff') {
      applyFinishBuff(event);
    }
  });

  useEffect(() => {
    const handleOverlayConfig = (event: Event) => {
      const detail = (event as CustomEvent<{ locked?: boolean }>).detail;
      setLocked(Boolean(detail?.locked));
    };
    window.addEventListener('endfield-overlay-config', handleOverlayConfig as EventListener);
    return () => window.removeEventListener('endfield-overlay-config', handleOverlayConfig as EventListener);
  }, []);

  useEffect(() => {
    let closed = false;
    const connect = () => {
      if (closed) {
        return;
      }
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onmessage = (message) => {
        try {
          handleMessage(JSON.parse(message.data) as OverlayMessage);
        } catch (error) {
          console.error('Failed to parse buff overlay message', error);
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
      const nextNow = Date.now();
      setNowMs(nextNow);
      const nextTimers = pruneTimers(timersRef.current, nextNow);
      timersRef.current = nextTimers;
      setTimers(nextTimers);
    }, 100);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="buff-overlay-root">
      <BuffOverlay locked={locked} timers={timers} nowMs={nowMs} />
    </div>
  );
}
