import { BuffLayer, BuffTimer } from '../types';

interface BuffOverlayProps {
  locked: boolean;
  timers: BuffTimer[];
  nowMs: number;
}

const formatTime = (remainingMs: number): string => (remainingMs <= 0 ? '0' : (remainingMs / 1000).toFixed(1));

const calcLayerRemaining = (layer: BuffLayer, nowMs: number): number => {
  if (layer.pausedUntilMs && layer.pausedRemainingMs !== null && layer.pausedRemainingMs !== undefined && nowMs < layer.pausedUntilMs) {
    return layer.pausedRemainingMs;
  }
  if (nowMs >= layer.expiresAt) {
    return 0;
  }
  return Math.max(0, layer.expiresAt - nowMs);
};

const calcLayerWidth = (layer: BuffLayer, nowMs: number): number => {
  if (layer.totalMs <= 0) {
    return 100;
  }
  const remainingMs = calcLayerRemaining(layer, nowMs);
  return Math.max(0, Math.min(100, (remainingMs / layer.totalMs) * 100));
};

const maxRemaining = (timer: BuffTimer, nowMs: number): number =>
  timer.layers.reduce((max, layer) => Math.max(max, calcLayerRemaining(layer, nowMs)), 0);

const isReady = (timer: BuffTimer, nowMs: number): boolean => timer.layers.some((layer) => nowMs >= layer.expiresAt);

export default function BuffOverlay({ locked, timers, nowMs }: BuffOverlayProps) {
  if (!locked) {
    return (
      <div className="buff-overlay-shell is-placeholder">
        <div className="buff-placeholder">
          <div className="buff-placeholder-title">Buff监控显示位置确认</div>
          <div className="buff-placeholder-subtitle">悬浮窗锁定后移除</div>
        </div>
      </div>
    );
  }

  const visibleTimers = timers;

  return (
    <div className="buff-overlay-root-shell">
      <div className="buff-overlay-shell">
        {visibleTimers.map((timer) => {
          const remainingMs = maxRemaining(timer, nowMs);
          const ready = remainingMs <= 0;
          const isNotice = !ready && timer.noticeTimeMs > 0 && remainingMs <= timer.noticeTimeMs;
          const stackCount = timer.layers.length;
          const label = stackCount > 1 ? `${timer.text} x${stackCount}` : timer.text;
          const sortedLayers = [...timer.layers].sort((left, right) => calcLayerRemaining(right, nowMs) - calcLayerRemaining(left, nowMs));

          return (
            <div
              key={`${timer.configId}-${timer.targetId}`}
              className={`buff-row${ready ? ' is-ready' : ''}${isNotice ? ' is-notice' : ''}${timer.mode === 'single' ? ' is-single' : ''}`}
            >
              <div className="buff-progress-layers">
                {sortedLayers.map((layer, index) => (
                  <div
                    key={layer.buffInstId}
                    className={`buff-progress-layer buff-progress-layer-${Math.min(index, 4)}`}
                    style={{ width: `${calcLayerWidth(layer, nowMs)}%` }}
                  />
                ))}
              </div>
              <div className="buff-content">
                <span className="buff-name">{label}</span>
                <span className="buff-remaining">{formatTime(remainingMs)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
