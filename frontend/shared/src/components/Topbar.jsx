import { api, usePolling } from "../api";
import { formatClock } from "../format";

/** App header: product name, which app this is, and the simulated clock. */
export default function Topbar({ title }) {
  const { data: sim, error } = usePolling(() => api.simulation(), [], 2000);
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-dot" /> Smart Transit Bakı
      </div>
      <span className="app-tag">{title}</span>
      <div className="clock" title="Simulyasiya saatı">
        <span className={`live-dot ${error || !sim ? "off" : ""}`} />
        {error ? "Server əlçatan deyil" : `Simulyasiya ×${sim?.speed ?? "-"}`}
        <strong>{formatClock(sim?.clock)}</strong>
      </div>
    </header>
  );
}
