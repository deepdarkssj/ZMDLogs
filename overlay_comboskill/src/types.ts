export interface SceneInfoChar {
  battle_inst_id: number;
  templateid: string | null;
  display_name?: string | null;
  potential_level?: number;
  squad_index?: number;
}

export interface SceneInfoEvent {
  type: 'SC_SELF_SCENE_INFO';
  session_id: string;
  timestamp_ms: number;
  char_list: SceneInfoChar[];
}

export interface BattleOpTriggerActionEvent {
  type: 'BattleOpTriggerAction';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  owner_id?: number | null;
  owner_type?: string | null;
  inst_id?: number | null;
  template_type: string | null;
  template_int_id: number | null;
  template_str_id?: string | null;
  level?: number | null;
  action: Record<string, unknown>;
}

export interface BattleOpModifyBattleStateEvent {
  type: 'BattleOpModifyBattleState';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  is_in_battle: boolean;
}

export interface HelloEvent {
  type: 'hello';
  schema_version: number;
  service_version: string;
  state: string;
  session_id: string | null;
}

export interface EventBatch {
  type: 'event_batch';
  session_id: string | null;
  sent_at_ms: number;
  events: OverlayEvent[];
}

export type OverlayEvent =
  | SceneInfoEvent
  | BattleOpTriggerActionEvent
  | BattleOpModifyBattleStateEvent
  | Record<string, unknown>;
export type OverlayMessage = HelloEvent | EventBatch | OverlayEvent;

export interface OverlayRuntimeConfig {
  id?: string;
  locked: boolean;
  click_through?: boolean;
  opacity?: number;
  builtin?: string;
}

export interface ComboSkillConfigEntry {
  text: string;
  duration: {
    default: number;
    skill_level: number[];
    potential_level: number[];
  };
  notice_time?: number;
  Refresh_skill?: number[];
  reset_skill?: number[];
}

export interface SquadSlot {
  battleInstId: number;
  displayName: string;
  templateId: string | null;
  squadIndex: number;
  potentialLevel: number;
}

export interface CooldownBar {
  slotIndex: number;
  battleInstId: number;
  triggerSkillId: number;
  text: string;
  totalMs: number;
  noticeTimeMs: number;
  lastStartedAt: number;
  ready: boolean;
  remainingMs: number;
  refreshSkillIds: number[];
  resetSkillIds: number[];
  pausedUntilMs?: number | null;
  pausedRemainingMs?: number | null;
}
