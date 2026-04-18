import React, { useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FooterStatus, OverlayState, PlayerStats } from '../types';

interface DamageOverlayProps {
  state: OverlayState;
}

const FOOTER_META: Record<FooterStatus, { label: string; accent: string; text: string; pulse: boolean }> = {
  waiting_client: {
    label: '等待客户端运行',
    accent: 'bg-red-500/20',
    text: 'text-black',
    pulse: false,
  },
  waiting_login: {
    label: '等待游戏登录',
    accent: 'bg-red-500/20',
    text: 'text-black',
    pulse: false,
  },
  waiting_restart: {
    label: '等待重开游戏',
    accent: 'bg-red-500/20',
    text: 'text-black',
    pulse: false,
  },
  waiting_battle: {
    label: '等待战斗',
    accent: 'bg-slate-400/20',
    text: 'text-black',
    pulse: false,
  },
  in_battle: {
    label: '战斗中',
    accent: 'bg-amber-300/35',
    text: 'text-black',
    pulse: true,
  },
  battle_ended: {
    label: '战斗结束',
    accent: 'bg-slate-400/20',
    text: 'text-black',
    pulse: false,
  },
};

const getInitials = (name: string): string => {
  const trimmed = name.trim();
  if (!trimmed) {
    return '--';
  }
  if (trimmed.length <= 2) {
    return trimmed.toUpperCase();
  }
  return trimmed.slice(0, 2).toUpperCase();
};

const formatNumber = (value: number): string => value.toFixed(2);

const formatTimer = (ms: number): string => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const DamageRow: React.FC<{ stats: PlayerStats; totalDamage: number; index: number }> = ({ stats, totalDamage, index }) => {
  const damagePercent = totalDamage > 0 ? (stats.totalDamage / totalDamage) * 100 : 0;
  const critRate = stats.hitCount > 0 ? (stats.critCount / stats.hitCount) * 100 : 0;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.2, delay: index * 0.04 }}
      className="group relative grid h-13 grid-cols-[60px_1fr_120px_65px_65px] items-center gap-0 overflow-hidden border border-outline-variant bg-white transition-colors hover:border-primary"
    >
      <div className="pointer-events-none absolute inset-0 z-0">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${damagePercent}%` }}
          className="h-full border-r-2 border-tertiary/40 bg-tertiary/15 transition-all duration-500"
        />
      </div>

      <div className="absolute bottom-0 left-0 top-0 z-10 w-1.5 bg-primary" />

      <div className="relative z-10 ml-2 flex aspect-square h-full items-center justify-center overflow-hidden">
        {stats.avatarUrl ? (
          <img
            src={stats.avatarUrl}
            alt={stats.name}
            className="h-full w-full object-cover"
            draggable={false}
          />
        ) : (
          <div className="font-mono text-xl font-bold tracking-tight text-primary">{getInitials(stats.name)}</div>
        )}
      </div>

      <div className="z-10 flex min-w-0 flex-col justify-center">
        <span className="truncate font-headline text-base font-black uppercase leading-tight">{stats.name}</span>
        <span className="text-[12px] font-bold tracking-tight text-neutral">
          最大伤害 {formatNumber(stats.maxDamage)}
        </span>
      </div>

      <div className="z-10 flex h-full flex-col items-center justify-center border-x border-outline-variant/30">
        <span className="font-mono text-lg font-bold leading-none text-black">{formatNumber(stats.totalDamage)}</span>
      </div>

      <div className="z-10 flex h-full flex-col items-center justify-center border-r border-outline-variant/30">
        <span className="font-mono text-base font-bold leading-none text-black">{damagePercent.toFixed(1)}%</span>
      </div>

      <div className="z-10 flex h-full flex-col items-center justify-center">
        <span className="font-mono text-base font-bold leading-none text-error">{critRate.toFixed(1)}%</span>
      </div>
    </motion.div>
  );
};

export const DamageOverlay: React.FC<DamageOverlayProps> = ({ state }) => {
  const damageDurationMs =
    state.damageStartTime !== null && state.lastDamageTime !== null
      ? Math.max(1, state.lastDamageTime - state.damageStartTime)
      : 0;
  const totalDps = damageDurationMs > 0 ? state.totalDamage / (damageDurationMs / 1000) : 0;
  const battleTimerMs =
    state.battleElapsedMs +
    (state.isInBattle && state.battleStateStartTime !== null
      ? Math.max(0, state.currentTime - state.battleStateStartTime)
      : 0);
  const footerMeta = FOOTER_META[state.footerStatus];

  const sortedPlayers = useMemo(() => {
    return Object.values(state.players).sort((a: PlayerStats, b: PlayerStats) => {
      if (b.totalDamage !== a.totalDamage) {
        return b.totalDamage - a.totalDamage;
      }
      if (a.squadIndex !== null && b.squadIndex !== null) {
        return a.squadIndex - b.squadIndex;
      }
      return a.name.localeCompare(b.name, 'zh-Hans-CN');
    });
  }, [state.players]);

  return (
    <div className="relative flex h-full w-full select-none flex-col overflow-hidden border-[3px] border-inverse-surface bg-surface shadow-2xl">
      <div className="relative shrink-0 border-b-[3px] border-inverse-surface bg-black px-6">
        <div className="absolute left-0 top-0 h-1 w-full opacity-30 diagonal-hashing-heavy" />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-3">
              <span className="text-[17px] font-black uppercase tracking-tighter text-primary-container opacity-70">总伤害</span>
              <span className="font-mono text-xl font-bold leading-none text-white">{formatNumber(state.totalDamage)}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[17px] font-black uppercase tracking-tighter text-primary-container opacity-70">总 DPS</span>
              <span className="font-mono text-xl font-bold leading-none text-white">{formatNumber(totalDps)}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`h-1.5 w-1.5 bg-primary-container ${footerMeta.pulse ? 'animate-pulse' : ''}`} />
            <div className="font-mono text-lg font-bold text-primary-container">{formatTimer(battleTimerMs)}</div>
          </div>
        </div>
      </div>

      <div className="shrink-0 border-b border-outline-variant/30 bg-black/5 px-8 py-0.5">
        <div className="grid grid-cols-[60px_1fr_120px_65px_55px] gap-0">
          <div className="col-span-2 pl-2 text-[12px] font-black tracking-widest text-black">队员</div>
          <div className="text-center text-[12px] font-black uppercase tracking-widest text-black">伤害</div>
          <div className="text-center text-[12px] font-black uppercase tracking-widest text-black">占比</div>
          <div className="text-center text-[12px] font-black uppercase tracking-widest text-black">暴击率</div>
        </div>
      </div>

      <div className="relative flex-grow overflow-y-auto px-6 py-3 custom-scrollbar">
        <div className="flex flex-col gap-1.5">
          <AnimatePresence mode="popLayout">
            {sortedPlayers.map((player, index) => (
              <DamageRow
                key={player.id}
                stats={player}
                totalDamage={state.totalDamage}
                index={index}
              />
            ))}
          </AnimatePresence>
          {sortedPlayers.length === 0 && (
            <div className="flex h-32 items-center justify-center border border-dashed border-outline-variant">
              <span className="font-mono text-xs uppercase tracking-widest text-neutral opacity-50">
                {footerMeta.label}
              </span>
            </div>
          )}
        </div>
        <div className="pointer-events-none absolute bottom-0 right-0 h-24 w-24 opacity-20 diagonal-hashing" />
      </div>

      <div className={`footer-hatching relative h-6 shrink-0 overflow-hidden border-t-[3px] border-inverse-surface ${footerMeta.accent} ${footerMeta.pulse ? 'flowing-hatching' : ''}`}>
        <div className="absolute inset-0 bg-black/10" />
        <span className={`relative z-10 flex h-full items-center justify-center pl-[0.4em] font-headline text-sm font-black tracking-[0.4em] drop-shadow-sm ${footerMeta.text}`}>
          {footerMeta.label}
        </span>
      </div>

      <div className="absolute -left-[1px] -top-[1px] z-20 h-6 w-6 border-l-2 border-t-2 border-primary-container" />
      <div className="absolute -right-[1px] -top-[1px] z-20 h-6 w-6 border-r-2 border-t-2 border-primary-container" />
    </div>
  );
};
