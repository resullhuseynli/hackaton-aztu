export const LEVEL_LABEL = { low: "Aşağı", medium: "Orta", high: "Yüksək" };
export const LEVEL_COLOR = { low: "#16a34a", medium: "#f59e0b", high: "#dc2626" };
export const REPORT_OPTIONS = [
  { level: "low", label: "Boşdur" },
  { level: "medium", label: "Orta" },
  { level: "high", label: "Çox sıxdır" },
];

export function formatEta(seconds) {
  if (seconds == null) return "—";
  if (seconds < 45) return "indi";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} dəq`;
  return `${Math.floor(minutes / 60)} saat ${minutes % 60} dəq`;
}

export const pct = (value) => `${Math.round(value ?? 0)}%`;

export function formatClock(iso) {
  if (!iso) return "--:--";
  return iso.slice(11, 16);
}

export function formatDistance(meters) {
  if (meters == null) return "";
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

/** "Neftçilər m/st → 28 May m/st" for one direction of a line detail. */
export function directionName(direction) {
  const stops = direction?.stops || [];
  if (!stops.length) return "";
  return `${stops[0].name} → ${stops[stops.length - 1].name}`;
}

export const BAKU_CENTER = [40.4093, 49.8671];
