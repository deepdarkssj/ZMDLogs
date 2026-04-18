import { CooldownBar } from '../types';

interface SkillOverlayProps {
  locked: boolean;
  bars: Array<CooldownBar | null>;
}

const formatRemaining = (remainingMs: number, ready: boolean): string => {
  if (ready || remainingMs <= 0) {
    return 'READY';
  }
  return (remainingMs / 1000).toFixed(1);
};

export default function SkillOverlay({ locked, bars }: SkillOverlayProps) {
  if (!locked) {
    return (
      <div className="combo-overlay-shell is-placeholder">
        <div className="combo-placeholder">
          <div className="combo-placeholder-title">连携监控显示位置确认</div>
          <div className="combo-placeholder-subtitle">悬浮窗锁定后移除</div>
        </div>
      </div>
    );
  }

  const visibleBars = bars
    .filter((bar): bar is CooldownBar => bar !== null)
    .sort((left, right) => left.slotIndex - right.slotIndex);

  return (
    <div className="combo-overlay-shell">
      {visibleBars.map((bar) => {
        const progress = bar.ready || bar.totalMs <= 0 ? 100 : ((bar.totalMs - bar.remainingMs) / bar.totalMs) * 100;
        const isNotice = !bar.ready && bar.noticeTimeMs > 0 && bar.remainingMs > 0 && bar.remainingMs <= bar.noticeTimeMs;

        return (
          <div
            key={`${bar.slotIndex}-${bar.battleInstId}-${bar.triggerSkillId}`}
            className={`combo-row${bar.ready ? ' is-ready' : ''}${isNotice ? ' is-notice' : ''}`}
          >
            <div className="combo-progress" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
            <div className="combo-content">
              <span className="combo-name">{bar.text}</span>
              <span className="combo-remaining">{formatRemaining(bar.remainingMs, bar.ready)}</span>
            </div>
            {bar.ready ? <div className="combo-ready-glow" /> : null}
          </div>
        );
      })}
    </div>
  );
}
