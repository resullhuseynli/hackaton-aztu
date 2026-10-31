import { useCallback, useEffect, useRef, useState } from "react";
import { LEVEL_COLOR, LEVEL_LABEL } from "../format";

export function DensityBadge({ level, children }) {
  if (!level) return <span className="badge none">Məlumat yoxdur</span>;
  return (
    <span className={`badge ${level}`}>
      <span className="dot" style={{ background: LEVEL_COLOR[level] }} />
      {children ?? LEVEL_LABEL[level]}
    </span>
  );
}

export function LoadBar({ percent, level }) {
  return (
    <div className="loadbar">
      <div style={{ width: `${Math.min(100, percent)}%`, background: LEVEL_COLOR[level] }} />
    </div>
  );
}

export function useToast() {
  const [message, setMessage] = useState(null);
  const timer = useRef();
  const show = useCallback((text) => {
    setMessage(text);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMessage(null), 3000);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  const toast = message ? <div className="toast">{message}</div> : null;
  return [toast, show];
}

/** Density score over time with the 50 / 85 thresholds. */
export function Sparkline({ points }) {
  if (!points?.length) return <div className="empty small">Tarixçə hələ yığılır…</div>;
  const width = 300;
  const height = 90;
  const pad = 4;
  const x = (i) => pad + (i * (width - 2 * pad)) / Math.max(1, points.length - 1);
  const y = (score) => height - pad - (Math.min(100, score) * (height - 2 * pad)) / 100;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <rect x="0" y={y(100)} width={width} height={y(85) - y(100)} fill="#fee2e2" />
      <rect x="0" y={y(85)} width={width} height={y(50) - y(85)} fill="#fef3c7" opacity="0.6" />
      <line x1="0" x2={width} y1={y(85)} y2={y(85)} stroke="#dc2626" strokeDasharray="4 3" strokeWidth="1" />
      <line x1="0" x2={width} y1={y(50)} y2={y(50)} stroke="#f59e0b" strokeDasharray="4 3" strokeWidth="1" />
      <path d={path} fill="none" stroke="#1f2937" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.score)} r="2.2" fill={LEVEL_COLOR[p.level]} />
      ))}
    </svg>
  );
}

/** Short beep for new alerts (WebAudio, no asset needed). */
export function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  } catch {
    /* audio not allowed yet */
  }
}
