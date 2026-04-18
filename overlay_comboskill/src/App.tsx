import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import SkillOverlay from './components/SkillOverlay';
import {
  BattleOpModifyBattleStateEvent,
  BattleOpTriggerActionEvent,
  ComboSkillConfigEntry,
  CooldownBar,
  EventBatch,
  HelloEvent,
  OverlayMessage,
  OverlayRuntimeConfig,
  SceneInfoEvent,
  SquadSlot,
} from './types';

import comboConfigText from '../ComboSkillOverlay.json?raw';

const COMBO_EVENT_NAME = 'endfield-overlay-config';
const TRIGGER_RESET_IGNORE_MS = 3000;

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

const normalizeConfig = (rawText: string): Map<number, ComboSkillConfigEntry> => {
  const parsed = JSON.parse(rawText.replace(/\r/g, '')) as Record<string, ComboSkillConfigEntry>;
  const result = new Map<number, ComboSkillConfigEntry>();
  for (const [key, value] of Object.entries(parsed)) {
    const skillId = Number(key);
    if (Number.isFinite(skillId)) {
      result.set(skillId, value);
    }
  }
  return result;
};

const buildResetTriggerMap = (configMap: Map<number, ComboSkillConfigEntry>): Map<number, number[]> => {
  const result = new Map<number, number[]>();
  for (const [configId, entry] of configMap.entries()) {
    for (const resetSkillId of Array.isArray(entry.reset_skill) ? entry.reset_skill : []) {
      const existing = result.get(resetSkillId) ?? [];
      existing.push(configId);
      result.set(resetSkillId, existing);
    }
  }
  return result;
};

const createInitialBars = (): Array<CooldownBar | null> => [null, null, null, null];

const clampIndex = (index: number, max: number): number => {
  if (index < 0) {
    return 0;
  }
  if (index >= max) {
    return max - 1;
  }
  return index;
};

const resolveAdjustment = (values: number[] | undefined, rawIndex: number, fallback: number): number => {
  if (!Array.isArray(values) || values.length === 0) {
    return fallback;
  }
  const index = clampIndex(rawIndex, values.length);
  const value = values[index];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
};

const createBar = (
  slotIndex: number,
  member: SquadSlot,
  skillId: number,
  eventLevel: number,
  entry: ComboSkillConfigEntry,
  timestampMs: number,
): CooldownBar => {
  const defaultDuration = typeof entry.duration?.default === 'number' ? entry.duration.default : 0;
  const skillAdjustment = resolveAdjustment(entry.duration?.skill_level, eventLevel - 1, 0);
  const potentialAdjustment = resolveAdjustment(entry.duration?.potential_level, member.potentialLevel, 0);
  const totalMs = Math.max(0, Math.round((defaultDuration + skillAdjustment + potentialAdjustment) * 1000));
  return {
    slotIndex,
    battleInstId: member.battleInstId,
    triggerSkillId: skillId,
    text: entry.text,
    totalMs,
    noticeTimeMs: Math.max(0, Math.round((entry.notice_time ?? 0) * 1000)),
    lastStartedAt: timestampMs,
    ready: totalMs <= 0,
    remainingMs: totalMs,
    refreshSkillIds: Array.isArray(entry.Refresh_skill) ? entry.Refresh_skill : [],
    resetSkillIds: Array.isArray(entry.reset_skill) ? entry.reset_skill : [],
    pausedUntilMs: null,
    pausedRemainingMs: null,
  };
};

const applyTick = (bars: Array<CooldownBar | null>, nowMs: number): Array<CooldownBar | null> =>
  bars.map((bar) => {
    if (!bar || bar.ready) {
      return bar;
    }
    const remainingMs = Math.max(0, bar.totalMs - (nowMs - bar.lastStartedAt));
    if (remainingMs <= 0) {
      return {
        ...bar,
        ready: true,
        remainingMs: 0,
      };
    }
    if (remainingMs === bar.remainingMs) {
      return bar;
    }
    return {
      ...bar,
      remainingMs,
    };
  });

const resolveReplacementSlotIndex = (
  bars: Array<CooldownBar | null>,
  preferredSlotIndex: number,
  nextText: string,
  nextSkillId: number,
): number => {
  const existingSameTextIndex = bars.findIndex(
    (bar) => bar !== null && bar.text === nextText && bar.triggerSkillId !== nextSkillId,
  );
  return existingSameTextIndex >= 0 ? existingSameTextIndex : preferredSlotIndex;
};

const updateSquadSlots = (
  previousSlots: Array<SquadSlot | null>,
  previousBars: Array<CooldownBar | null>,
  members: SceneInfoEvent['char_list'],
): { slots: Array<SquadSlot | null>; bars: Array<CooldownBar | null> } => {
  const nextSlots: Array<SquadSlot | null> = [null, null, null, null];
  const nextBars = [...previousBars];
  for (const rawMember of members) {
    const battleInstId = asNumber(rawMember.battle_inst_id);
    if (battleInstId === null) {
      continue;
    }
    const slotIndex = clampIndex(rawMember.squad_index ?? 0, nextSlots.length);
    nextSlots[slotIndex] = {
      battleInstId,
      displayName: rawMember.display_name ?? rawMember.templateid ?? `#${battleInstId}`,
      templateId: rawMember.templateid ?? null,
      squadIndex: slotIndex,
      potentialLevel: Math.max(0, rawMember.potential_level ?? 0),
    };
  }
  for (let i = 0; i < nextSlots.length; i += 1) {
    const previous = previousSlots[i];
    const current = nextSlots[i];
    if (!previous || !current || previous.battleInstId !== current.battleInstId) {
      nextBars[i] = null;
    }
  }
  return { slots: nextSlots, bars: nextBars };
};

export default function App() {
  const comboConfig = useMemo(() => normalizeConfig(comboConfigText), []);
  const resetTriggerMap = useMemo(() => buildResetTriggerMap(comboConfig), [comboConfig]);
  const [locked, setLocked] = useState(getInitialLocked);
  const [squadSlots, setSquadSlots] = useState<Array<SquadSlot | null>>([null, null, null, null]);
  const [bars, setBars] = useState<Array<CooldownBar | null>>(createInitialBars);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const squadSlotsRef = useRef<Array<SquadSlot | null>>([null, null, null, null]);
  const triggerResetHistoryRef = useRef<Map<number, number>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const applySceneInfo = useEffectEvent((event: SceneInfoEvent) => {
    setBars((prevBars) => {
      const updated = updateSquadSlots(squadSlotsRef.current, prevBars, event.char_list);
      squadSlotsRef.current = updated.slots;
      setSquadSlots(updated.slots);
      return updated.bars;
    });
  });

  const applyTriggerAction = useEffectEvent((event: BattleOpTriggerActionEvent) => {
    if ((event.template_type ?? '').toLowerCase() !== 'skill') {
      return;
    }
    const templateIntId = asNumber(event.template_int_id);
    if (templateIntId === null) {
      return;
    }
    const timestampMs = event.timestamp_ms || Date.now();
    const ownerId = asNumber(event.owner_id);

    setBars((prevBars) => {
      const nextBars = [...applyTick(prevBars, timestampMs)];
      if (ownerId === null) {
        return nextBars;
      }
      const slotIndex = squadSlotsRef.current.findIndex((member) => member?.battleInstId === ownerId);
      if (slotIndex < 0) {
        return nextBars;
      }
      const member = squadSlotsRef.current[slotIndex];
      if (!member) {
        return nextBars;
      }
      const eventLevel = Math.max(1, asNumber(event.level) ?? 1);
      const mainConfig = comboConfig.get(templateIntId);
      const existing = nextBars[slotIndex];
      const resetCandidates = resetTriggerMap.get(templateIntId) ?? [];
      const selectedResetConfigId =
        existing && resetCandidates.includes(existing.triggerSkillId) ? existing.triggerSkillId : resetCandidates[0];
      const resetConfig = selectedResetConfigId !== undefined ? comboConfig.get(selectedResetConfigId) ?? null : null;
      const lastTriggerResetAt = triggerResetHistoryRef.current.get(templateIntId);
      const canTriggerOrReset =
        lastTriggerResetAt === undefined || timestampMs - lastTriggerResetAt >= TRIGGER_RESET_IGNORE_MS;

      if (existing && existing.refreshSkillIds.includes(templateIntId)) {
        nextBars[slotIndex] = {
          ...existing,
          ready: true,
          remainingMs: 0,
        };
      }

      if (mainConfig && canTriggerOrReset) {
        triggerResetHistoryRef.current.set(templateIntId, timestampMs);
        const targetSlotIndex = resolveReplacementSlotIndex(nextBars, slotIndex, mainConfig.text, templateIntId);
        if (targetSlotIndex !== slotIndex) {
          nextBars[slotIndex] = null;
        }
        nextBars[targetSlotIndex] = createBar(
          targetSlotIndex,
          member,
          templateIntId,
          eventLevel,
          mainConfig,
          timestampMs,
        );
        return nextBars;
      }

      if (resetConfig && canTriggerOrReset) {
        triggerResetHistoryRef.current.set(templateIntId, timestampMs);
        const targetSlotIndex = resolveReplacementSlotIndex(
          nextBars,
          slotIndex,
          resetConfig.text,
          resetConfig.configId,
        );
        if (targetSlotIndex !== slotIndex) {
          nextBars[slotIndex] = null;
        }
        nextBars[targetSlotIndex] = createBar(
          targetSlotIndex,
          member,
          resetConfig.configId,
          eventLevel,
          resetConfig,
          timestampMs,
        );
      }
      return nextBars;
    });
  });

  const handleMessage = useEffectEvent((message: OverlayMessage) => {
    if (message.type === 'hello') {
      const hello = message as HelloEvent;
      if (hello.session_id !== sessionId) {
        setSessionId(hello.session_id);
        setSquadSlots([null, null, null, null]);
        squadSlotsRef.current = [null, null, null, null];
        triggerResetHistoryRef.current.clear();
        setBars(createInitialBars());
      }
      return;
    }
    if (message.type === 'event_batch') {
      for (const event of (message as EventBatch).events) {
        handleMessage(event as OverlayMessage);
      }
      return;
    }
    if (message.type === 'SC_SELF_SCENE_INFO') {
      applySceneInfo(message as SceneInfoEvent);
      return;
    }
    if (message.type === 'BattleOpTriggerAction') {
      applyTriggerAction(message as BattleOpTriggerActionEvent);
      return;
    }
    if (message.type === 'BattleOpModifyBattleState') {
      const battleState = message as BattleOpModifyBattleStateEvent;
      if (!battleState.is_in_battle) {
        triggerResetHistoryRef.current.clear();
        setBars(createInitialBars());
      }
    }
  });

  useEffect(() => {
    const handleOverlayConfig = (event: Event) => {
      const detail = (event as CustomEvent<OverlayRuntimeConfig>).detail;
      setLocked(Boolean(detail?.locked));
    };
    window.addEventListener(COMBO_EVENT_NAME, handleOverlayConfig as EventListener);
    return () => window.removeEventListener(COMBO_EVENT_NAME, handleOverlayConfig as EventListener);
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
          console.error('Failed to parse combo overlay message', error);
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
      setBars((prevBars) => applyTick(prevBars, Date.now()));
    }, 100);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="combo-overlay-root">
      <SkillOverlay locked={locked} bars={bars} />
    </div>
  );
}
