import { useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, Polyline, Tooltip } from "react-leaflet";
import { api, useLive, usePolling } from "@transit/shared/api.js";
import { DensityBadge, Sparkline, beep, useToast } from "@transit/shared/components/common.jsx";
import { BaseMap, BusMarker, FitBounds } from "@transit/shared/components/map.jsx";
import { LEVEL_COLOR, LEVEL_LABEL, formatClock, pct } from "@transit/shared/format.js";

const LEVEL_FILTERS = [
  { value: null, label: "Hamısı" },
  { value: "high", label: "Yüksək" },
  { value: "medium", label: "Orta" },
  { value: "low", label: "Aşağı" },
];
const TREND = { up: ["▲", "trend-up"], down: ["▼", "trend-down"], flat: ["–", "muted"] };

export default function OperatorPage() {
  const [lineId, setLineId] = useState(() => Number(new URLSearchParams(window.location.search).get("line")) || null);
  const [toast, showToast] = useToast();
  const { data: live } = useLive({ operator: true, lineId });
  const overview = live?.overview;
  const density = useMemo(() => live?.density || [], [live]);
  const openAlerts = useMemo(() => live?.alerts || [], [live]);
  const lineBuses = live?.line_id === lineId ? live?.buses || [] : [];

  const fleet = usePolling(() => api.fleet(), [], 4000).data || [];
  const resolved = usePolling(() => api.alerts("resolved", 8), [], 8000).data || [];
  const history = usePolling(() => api.history(lineId, 60), [lineId], 10000).data;
  const detailState = usePolling(() => api.line(lineId), [lineId], 10 * 60 * 1000).data;
  const detail = detailState?.line.id === lineId ? detailState : null;
  const selected = density.find((d) => d.line_id === lineId);

  // Flash and beep when a new alert appears.
  const seen = useRef(null);
  const [fresh, setFresh] = useState(new Set());
  useEffect(() => {
    if (!live) return;
    const ids = openAlerts.map((a) => a.id);
    if (seen.current === null) {
      seen.current = new Set(ids);
      return;
    }
    const added = ids.filter((id) => !seen.current.has(id));
    if (added.length) {
      beep();
      setFresh(new Set(added));
      added.forEach((id) => seen.current.add(id));
    }
  }, [live, openAlerts]);

  const act = async (promise, success) => {
    try {
      showToast(success(await promise));
    } catch (err) {
      showToast(`Xəta: ${err.message}`);
    }
  };

  return (
    <div className="operator">
      <Kpis overview={overview} />
      <div className="operator-main">
        <aside className="alerts-panel">
          <div className="sidebar-scroll">
            <div className="section-title" style={{ marginTop: 0 }}>
              Aktiv xəbərdarlıqlar <span className="muted">({openAlerts.length})</span>
            </div>
            {openAlerts.map((a) => (
              <AlertCard
                key={a.id}
                alert={a}
                fresh={fresh.has(a.id)}
                onSelect={() => setLineId(a.line_id)}
                onDispatch={() =>
                  act(api.dispatch(a.id), (r) =>
                    `${r.moved_bus_ids.length} avtobus yönləndirildi: Xətt ${a.donor_line_number} → Xətt ${a.line_number}`,
                  )
                }
                onResolve={() => act(api.resolve(a.id), () => `Xəbərdarlıq bağlandı: Xətt ${a.line_number}`)}
              />
            ))}
            {!openAlerts.length && <div className="empty">Aktiv xəbərdarlıq yoxdur</div>}

            {resolved.length > 0 && (
              <>
                <div className="section-title">Son bağlananlar</div>
                {resolved.map((a) => (
                  <div key={a.id} className="alert-card resolved" onClick={() => setLineId(a.line_id)}>
                    <div className="alert-title">
                      Xətt {a.line_number}
                      <span className="spacer" />
                      <span className="small muted">
                        {formatClock(a.created_at)}–{formatClock(a.resolved_at)} ·{" "}
                        {a.resolved_by === "operator" ? "operator" : "avtomatik"}
                      </span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </aside>

        <div className="operator-center">
          <div className="operator-map">
            <BaseMap zoom={11}>
              {detail?.directions.map((d) => (
                <Polyline
                  key={d.direction}
                  positions={d.route}
                  pathOptions={{ color: "#1a73e8", weight: d.direction === "forward" ? 5 : 3, opacity: 0.7 }}
                />
              ))}
              {detail && (
                <FitBounds points={detail.directions.flatMap((d) => d.route)} fitKey={lineId} rightPadding={360} />
              )}
              {fleet
                .filter((b) => b.line_id !== lineId && b.latitude != null)
                .map((b) => (
                  <CircleMarker
                    key={b.bus_id}
                    center={[b.latitude, b.longitude]}
                    radius={b.density_level === "high" ? 5 : 3.5}
                    pathOptions={{
                      stroke: false,
                      fillColor: LEVEL_COLOR[b.density_level],
                      fillOpacity: b.status === "layover" ? 0.3 : 0.85,
                    }}
                    eventHandlers={{ click: () => setLineId(b.line_id) }}
                  >
                    <Tooltip>
                      Xətt {b.line_number} · {pct(b.passenger_percentage)}
                    </Tooltip>
                  </CircleMarker>
                ))}
              {lineBuses.map((b) => (
                <BusMarker key={b.bus_id} bus={b} label={detail?.line.number ?? ""} />
              ))}
            </BaseMap>
            {lineId != null && (
              <SelectedLine
                detail={detail}
                density={selected}
                history={history?.line_id === lineId ? history.points : null}
                onSurge={() => act(api.surge(lineId), (r) => r.message)}
                onClose={() => setLineId(null)}
              />
            )}
            <div className="legend">
              <strong>Avtobus doluluğu:</strong>
              {Object.entries(LEVEL_LABEL).map(([level, label]) => (
                <span key={level} className="row">
                  <span className="dot" style={{ background: LEVEL_COLOR[level] }} /> {label}
                </span>
              ))}
            </div>
          </div>
          <DensityTable rows={density} selectedId={lineId} onSelect={setLineId} />
        </div>
      </div>
      {toast}
    </div>
  );
}

function Kpis({ overview }) {
  const o = overview;
  return (
    <div className="kpis">
      <div className="kpi">
        <div className="kpi-label">Xəttdə olan avtobuslar</div>
        <div className="kpi-value">{o?.active_buses ?? "—"}</div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Orta doluluq</div>
        <div className="kpi-value">{o ? `${o.average_occupancy}%` : "—"}</div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Xətlər üzrə sıxlıq</div>
        <div className="kpi-sub" style={{ fontSize: 15, fontWeight: 700, marginTop: 6 }}>
          {["high", "medium", "low"].map((level) => (
            <span key={level} style={{ color: LEVEL_COLOR[level] }}>
              {o?.lines_by_level[level] ?? 0} {LEVEL_LABEL[level].toLowerCase()}
            </span>
          ))}
        </div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Aktiv xəbərdarlıq</div>
        <div className="kpi-value" style={{ color: o?.open_alerts ? "var(--high)" : undefined }}>
          {o?.open_alerts ?? "—"}
        </div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Sərnişin bildirişi (10 dəq)</div>
        <div className="kpi-value">{o?.reports_last_window ?? "—"}</div>
      </div>
    </div>
  );
}

function AlertCard({ alert, fresh, onSelect, onDispatch, onResolve }) {
  const [busy, setBusy] = useState(false);
  const run = (fn) => async (event) => {
    event.stopPropagation();
    setBusy(true);
    await fn();
    setBusy(false);
  };
  return (
    <div className={`alert-card ${fresh ? "fresh" : ""}`} onClick={onSelect} style={{ cursor: "pointer" }}>
      <div className="alert-title">
        <span className="pill" style={{ background: "var(--high)" }}>
          {alert.line_number}
        </span>
        Əlavə avtobus lazımdır
        <span className="spacer" />
        <span className="small muted">{formatClock(alert.created_at)}</span>
      </div>
      <div className="alert-msg">{alert.message}</div>
      <div className="alert-actions">
        <button className="btn small danger" disabled={busy || !alert.suggested_donor_line_id} onClick={run(onDispatch)}>
          {alert.suggested_donor_line_id
            ? `${alert.suggested_bus_count} avtobus yönləndir`
            : "Donor xətt yoxdur"}
        </button>
        <button className="btn small ghost" disabled={busy} onClick={run(onResolve)}>
          Bağla
        </button>
      </div>
    </div>
  );
}

function SelectedLine({ detail, density, history, onSurge, onClose }) {
  return (
    <div className="map-overlay" style={{ maxHeight: "calc(100% - 24px)", overflowY: "auto" }}>
      <div className="row">
        <div className="line-number" style={{ height: 34, minWidth: 44, fontSize: 16 }}>
          {detail?.line.number ?? "…"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="ellipsis" style={{ fontWeight: 600 }}>
            {detail ? `${detail.line.first_point} — ${detail.line.last_point}` : "Yüklənir…"}
          </div>
          <div className="small muted">{detail?.line.carrier}</div>
        </div>
        <button className="link" onClick={onClose} aria-label="Bağla">
          ✕
        </button>
      </div>
      {density && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 12, fontSize: 13 }}>
          <span>
            Səviyyə: <DensityBadge level={density.level} />
          </span>
          <span>
            Sıxlıq balı: <strong>{density.score}</strong>
          </span>
          <span>Doluluq: {pct(density.occupancy_pct)}</span>
          <span>Bildiriş balı: {density.report_score ?? "—"}</span>
          <span>Avtobus: {density.active_buses}</span>
          <span>Bildirişlər: {density.reports_last_window}</span>
        </div>
      )}
      <div className="section-title" style={{ marginTop: 12 }}>
        Son 60 dəqiqə
      </div>
      <Sparkline points={history} />
      <div className="small muted" style={{ marginTop: 4 }}>
        Qırmızı xətt: 85 (Yüksək), sarı xətt: 50 (Orta)
      </div>
      <button className="btn ghost small" style={{ marginTop: 12, width: "100%" }} onClick={onSurge}>
        Demo: bu xətti sıxlaşdır
      </button>
    </div>
  );
}

function DensityTable({ rows, selectedId, onSelect }) {
  const [level, setLevel] = useState(null);
  const [query, setQuery] = useState("");
  const filtered = rows.filter(
    (r) =>
      (!level || r.level === level) &&
      (!query || r.line_number.toLowerCase().startsWith(query.toLowerCase())),
  );
  return (
    <div className="table-wrap">
      <div className="table-tools">
        <strong>Xətlər üzrə sıxlıq</strong>
        <div className="tabs">
          {LEVEL_FILTERS.map((f) => (
            <button key={f.label} className={level === f.value ? "active" : ""} onClick={() => setLevel(f.value)}>
              {f.label}
            </button>
          ))}
        </div>
        <input className="search" placeholder="Xətt nömrəsi" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr>
            <th>Xətt</th>
            <th>Marşrut</th>
            <th>Səviyyə</th>
            <th className="num">Bal</th>
            <th className="num">Doluluq</th>
            <th className="num">Bildiriş balı</th>
            <th className="num">Bildirişlər</th>
            <th className="num">Avtobus</th>
            <th>Trend</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((r) => {
            const [arrow, cls] = TREND[r.trend];
            return (
              <tr
                key={r.line_id}
                className={`clickable ${r.line_id === selectedId ? "selected" : ""}`}
                onClick={() => onSelect(r.line_id)}
              >
                <td>
                  <strong>{r.line_number}</strong> {r.has_open_alert && <span title="Aktiv xəbərdarlıq">🔴</span>}
                </td>
                <td className="ellipsis" style={{ maxWidth: 280 }}>
                  {r.first_point} — {r.last_point}
                </td>
                <td>
                  <DensityBadge level={r.level} />
                </td>
                <td className="num">
                  <strong>{r.score}</strong>
                </td>
                <td className="num">{pct(r.occupancy_pct)}</td>
                <td className="num">{r.report_score ?? "—"}</td>
                <td className="num">{r.reports_last_window}</td>
                <td className="num">{r.active_buses}</td>
                <td className={cls}>{arrow}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!filtered.length && <div className="empty">Məlumat yoxdur</div>}
    </div>
  );
}
