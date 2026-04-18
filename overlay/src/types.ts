export interface SquadMember {
  battle_inst_id: number;
  templateid: string | null;
  display_name: string | null;
  is_leader: boolean;
  squad_index: number;
}

export interface ActorRef {
  battle_inst_id: number | null;
  display_name: string | null;
}

export interface DamageDetail {
  target_battle_inst_id: number | null;
  is_crit: boolean;
  value: number;
  abs_value: number;
  cur_hp: number | null;
}

export interface DamageEvent {
  type: 'damage';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  skill_template_id: number | null;
  attacker: ActorRef;
  target: ActorRef;
  details: DamageDetail[];
}

export interface SquadUpdateEvent {
  type: 'squad_update';
  session_id: string;
  timestamp_ms: number;
  members: SquadMember[];
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

export interface BattleOpFinishBuffEvent {
  type: 'BattleOpFinishBuff';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  buff_inst_id: number | null;
}

export interface BattleOpAddBuffEvent {
  type: 'BattleOpAddBuff';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  int_id: number | null;
  str_id?: string | null;
  buff_inst_id: number | null;
  src_inst_id: number | null;
  target_inst_id: number | null;
  assigned_items: Record<string, unknown>;
}

export interface BattleOpEnablePassiveSkillEvent {
  type: 'BattleOpEnablePassiveSkill';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  skill_inst_id: number | null;
}

export interface BattleOpEntityDieEvent {
  type: 'BattleOpEntityDie';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  entity_inst_id: number | null;
}

export interface BattleOpModifyBattleStateEvent {
  type: 'BattleOpModifyBattleState';
  session_id: string;
  timestamp_ms: number;
  seq_id: number | null;
  client_tick_tms: number | null;
  is_in_battle: boolean;
}

export interface SceneInfoChar {
  id: number | null;
  templateid: string | null;
  battle_inst_id: number;
  display_name?: string | null;
  potential_level?: number;
  is_leader?: boolean;
  squad_index?: number;
}

export interface SceneInfoEvent {
  type: 'SC_SELF_SCENE_INFO';
  session_id: string;
  timestamp_ms: number;
  char_list: SceneInfoChar[];
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
  | DamageEvent
  | SquadUpdateEvent
  | BattleOpTriggerActionEvent
  | BattleOpFinishBuffEvent
  | BattleOpAddBuffEvent
  | BattleOpEnablePassiveSkillEvent
  | BattleOpEntityDieEvent
  | BattleOpModifyBattleStateEvent
  | SceneInfoEvent;

export type OverlayMessage = HelloEvent | EventBatch | OverlayEvent;

export interface PlayerStats {
  id: string;
  battleInstId: number;
  templateId: string | null;
  name: string;
  avatarUrl: string | null;
  totalDamage: number;
  maxDamage: number;
  critCount: number;
  hitCount: number;
  lastUpdate: number;
  squadIndex: number | null;
  isLeader: boolean;
}

export type FooterStatus =
  | 'waiting_client'
  | 'waiting_login'
  | 'waiting_restart'
  | 'waiting_battle'
  | 'in_battle'
  | 'battle_ended';

export interface OverlayState {
  players: Record<string, PlayerStats>;
  totalDamage: number;
  damageStartTime: number | null;
  lastDamageTime: number | null;
  battleStateStartTime: number | null;
  battleElapsedMs: number;
  currentTime: number;
  isInBattle: boolean;
  hasSquad: boolean;
  footerStatus: FooterStatus;
  serviceState: string;
  sessionId: string | null;
}
