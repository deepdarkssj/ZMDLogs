export interface OverlayRuntimeConfig {
  id?: string;
  locked?: boolean;
  click_through?: boolean;
  opacity?: number;
  builtin?: string;
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

export interface AssignedItem {
  target_key?: string | null;
  numeric_value?: number | null;
  float_value?: number | null;
  int_value?: number | null;
}

export interface CreateBuffDetail {
  source_id?: number | string | null;
  target_id?: number | string | null;
  buff_inst_id?: number | string | null;
  buff_num_id?: number | string | null;
  assigned_items?: AssignedItem[] | null;
}

export interface FinishBuffDetail {
  target_id?: number | string | null;
  buff_inst_id?: number | string | null;
}

export interface TriggerActionPayload {
  action_type?: string | null;
  create_buff_action?: {
    details?: CreateBuffDetail[] | null;
  } | null;
  finish_buff_action?: {
    finish_buffs?: FinishBuffDetail[] | null;
  } | null;
}

export interface BattleOpTriggerActionEvent {
  type: 'BattleOpTriggerAction';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  template_type?: string | null;
  template_int_id?: number | null;
  action: TriggerActionPayload | Record<string, unknown>;
}

export interface BattleOpModifyBattleStateEvent {
  type: 'BattleOpModifyBattleState';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  is_in_battle: boolean;
}

export type OverlayEvent = BattleOpTriggerActionEvent | BattleOpModifyBattleStateEvent | Record<string, unknown>;
export type OverlayMessage = HelloEvent | EventBatch | OverlayEvent;

export interface BuffConfigValue {
  default: number;
  key?: string;
}

export interface BuffConfigStack extends BuffConfigValue {
  mode: 'single' | 'refresh';
}

export interface BuffConfigEntry {
  text: string;
  Group?: number[];
  duration: BuffConfigValue;
  max_stack?: BuffConfigStack;
  number?: BuffConfigValue;
  notice_time?: number;
}

export interface BuffConfigResolved extends BuffConfigEntry {
  configId: number;
  aliases: number[];
}

export interface BuffLayer {
  buffInstId: string;
  totalMs: number;
  startedAt: number;
  expiresAt: number;
  pausedUntilMs?: number | null;
  pausedRemainingMs?: number | null;
}

export interface BuffTimer {
  configId: number;
  matchedBuffNumId: number;
  targetId: string;
  text: string;
  noticeTimeMs: number;
  mode: 'single' | 'refresh';
  maxStacks: number;
  layers: BuffLayer[];
}
