import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Marker, Polyline, Popup, Tooltip } from "react-leaflet";
import { api, useLive, usePolling } from "@transit/shared/api.js";
import { DensityBadge, LoadBar, useToast } from "@transit/shared/components/common.jsx";
import { BaseMap, BusMarker, FitBounds, busIcon } from "@transit/shared/components/map.jsx";
import { LEVEL_COLOR, LEVEL_LABEL, REPORT_OPTIONS, directionName, formatDistance, formatEta, pct } from "@transit/shared/format.js";

const urlParam = (name) => {
  const value = new URLSearchParams(window.location.search).get(name);
  return value ? Number(value) : null;
};

export default function PassengerPage() {
  const [tab, setTab] = useState("lines");
  const [lineId, setLineId] = useState(() => urlParam("line"));
  const [direction, setDirection] = useState("forward");
  const [stopId, setStopId] = useState(() => urlParam("stop"));
  const [toast, showToast] = useToast();

  const lines = usePolling(() => api.lines(), [], 30000).data || [];
  const detailState = usePolling(() => api.line(lineId), [lineId], 10 * 60 * 1000).data;
  const detail = detailState?.line.id === lineId ? detailState : null;
  const { data: live } = useLive({ lineId });
  const buses = live?.line_id === lineId ? live.buses || [] : [];
  const stopState = usePolling(() => api.stop(stopId), [stopId], 4000).data;
  const stop = stopState?.stop.id === stopId ? stopState : null;

  const currentDirection = detail?.directions.find((d) => d.direction === direction) || detail?.directions[0];
  const otherDirection = detail?.directions.find((d) => d !== currentDirection);

  const selectLine = (id) => {
    setLineId(id);
    setDirection("forward");
    setTab("lines");
  };

  return (
    <div className="page">
      <aside className="sidebar">
        <div className="sidebar-scroll">
          <div className="tabs">
            <button className={tab === "lines" ? "active" : ""} onClick={() => setTab("lines")}>
              Marşrutlar
            </button>
            <button className={tab === "stops" ? "active" : ""} onClick={() => setTab("stops")}>
              Dayanacaqlar
            </button>
          </div>
          {tab === "lines" &&
            (lineId == null ? (
              <LineGrid lines={lines} onSelect={selectLine} />
            ) : (
              <LinePanel
                summary={lines.find((l) => l.id === lineId)}
                detail={detail}
                current={currentDirection}
                buses={buses}
                onDirection={setDirection}
                onBack={() => setLineId(null)}
                onStop={setStopId}
                onReported={showToast}
              />
            ))}
          {tab === "stops" && <StopSearch onSelect={setStopId} selectedId={stopId} />}
        </div>
      </aside>

      <div className="map-wrap">
        <BaseMap>
          {otherDirection && (
            <Polyline positions={otherDirection.route} pathOptions={{ color: "#94a3b8", weight: 3, dashArray: "6 6" }} />
          )}
          {currentDirection && (
            <>
              <Polyline positions={currentDirection.route} pathOptions={{ color: "#1a73e8", weight: 5, opacity: 0.8 }} />
              {currentDirection.stops.map((s) => (
                <CircleMarker
                  key={`${s.id}-${s.stop_order}`}
                  center={[s.latitude, s.longitude]}
                  radius={5}
                  pathOptions={{ color: "#1a73e8", weight: 2, fillColor: "#fff", fillOpacity: 1 }}
                  eventHandlers={{ click: () => setStopId(s.id) }}
                >
                  <Tooltip direction="top">{s.name}</Tooltip>
                </CircleMarker>
              ))}
              <FitBounds
                points={currentDirection.route}
                fitKey={`${lineId}-${currentDirection.direction}`}
                rightPadding={stopId != null ? 370 : 40}
              />
            </>
          )}
          {buses.map((b) => (
            <BusMarker key={b.bus_id} bus={b} label={detail?.line.number ?? ""} />
          ))}
          {stop && (
            <>
              <CircleMarker
                center={[stop.stop.latitude, stop.stop.longitude]}
                radius={10}
                pathOptions={{ color: "#fff", weight: 3, fillColor: "#dc2626", fillOpacity: 1 }}
              >
                <Tooltip permanent direction="top" offset={[0, -10]}>
                  {stop.stop.name}
                </Tooltip>
              </CircleMarker>
              {lineId == null &&
                stop.arrivals
                  .filter((a) => a.latitude != null)
                  .map((a) => (
                    <Marker key={a.bus_id} position={[a.latitude, a.longitude]} icon={busIcon(a.line_number, a.density_level)}>
                      <Popup>
                        Xətt {a.line_number} · {a.bus_plate}
                        <br />
                        {formatEta(a.eta_seconds)} · {pct(a.passenger_percentage)} dolu
                      </Popup>
                    </Marker>
                  ))}
              {lineId == null && (
                <FitBounds points={[[stop.stop.latitude, stop.stop.longitude]]} fitKey={`stop-${stopId}`} />
              )}
            </>
          )}
        </BaseMap>
        <div className="legend">
          {Object.entries(LEVEL_LABEL).map(([level, label]) => (
            <span key={level} className="row">
              <span className="dot" style={{ background: LEVEL_COLOR[level] }} /> {label}
            </span>
          ))}
        </div>
        {stopId != null && (
          <StopPanel
            data={stop}
            onClose={() => setStopId(null)}
            onLine={selectLine}
            onReported={showToast}
          />
        )}
      </div>
      {toast}
    </div>
  );
}

function LineGrid({ lines, onSelect }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return lines;
    return lines.filter(
      (l) =>
        l.number.toLowerCase().startsWith(q) ||
        l.first_point?.toLowerCase().includes(q) ||
        l.last_point?.toLowerCase().includes(q),
    );
  }, [lines, query]);
  return (
    <>
      <input className="search" placeholder="Marşrut axtar" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="section-title">
        Marşrutlar <span className="muted">({filtered.length})</span>
      </div>
      <div className="line-grid">
        {filtered.map((l) => (
          <button key={l.id} className="line-btn" onClick={() => onSelect(l.id)} title={`${l.first_point} — ${l.last_point}`}>
            {l.density_level && <span className="dot" style={{ background: LEVEL_COLOR[l.density_level] }} />}
            {l.number}
          </button>
        ))}
      </div>
      {!filtered.length && <div className="empty">Marşrut tapılmadı</div>}
    </>
  );
}

function LinePanel({ summary, detail, current, buses, onDirection, onBack, onStop, onReported }) {
  if (!detail) return <div className="empty">Yüklənir…</div>;
  const { line } = detail;
  const directionBuses = buses
    .filter((b) => b.direction === current?.direction)
    .sort((a, b) => (a.next_stop_eta_seconds ?? 1e9) - (b.next_stop_eta_seconds ?? 1e9));
  return (
    <>
      <button className="link" onClick={onBack}>
        ← Bütün marşrutlar
      </button>
      <div className="line-header" style={{ marginTop: 12 }}>
        <div className="line-number">{line.number}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600 }}>
            {line.first_point} — {line.last_point}
          </div>
          <div className="line-meta">
            {line.carrier} · {line.tariff} · {line.route_length_km} km · ~{line.duration_minutes} dəq
          </div>
          <div style={{ marginTop: 6 }}>
            <DensityBadge level={summary?.density_level}>
              Sıxlıq: {summary?.density_level ? LEVEL_LABEL[summary.density_level] : ""}
            </DensityBadge>
          </div>
        </div>
      </div>

      {detail.directions.length > 1 && (
        <div className="dir-toggle">
          {detail.directions.map((d) => (
            <button
              key={d.direction}
              className={d.direction === current?.direction ? "active" : ""}
              onClick={() => onDirection(d.direction)}
            >
              {directionName(d)}
            </button>
          ))}
        </div>
      )}

      <div className="section-title">Sıxlığı bildir</div>
      <ReportBox lineId={line.id} onReported={onReported} />

      <div className="section-title">
        Avtobuslar <span className="muted">({directionBuses.length})</span>
      </div>
      {directionBuses.map((b) => (
        <div className="bus-item" key={b.bus_id}>
          <div className="grow">
            <div className="row">
              <strong>{b.bus_plate}</strong>
              <DensityBadge level={b.density_level}>{pct(b.passenger_percentage)}</DensityBadge>
            </div>
            <div className="small muted ellipsis" style={{ margin: "4px 0" }}>
              {b.status === "layover" ? "Son dayanacaqda fasilə" : `Növbəti: ${b.next_stop_name || "—"}`}
            </div>
            <LoadBar percent={b.passenger_percentage} level={b.density_level} />
          </div>
          {b.status !== "layover" && (
            <div className={`eta ${b.next_stop_eta_seconds < 45 ? "now" : ""}`}>{formatEta(b.next_stop_eta_seconds)}</div>
          )}
        </div>
      ))}
      {!directionBuses.length && <div className="empty">Bu istiqamətdə avtobus yoxdur</div>}

      <div className="section-title">
        Dayanacaqlar <span className="muted">({current?.stops.length})</span>
      </div>
      {current?.stops.map((s) => (
        <div className="stop-item" key={`${s.id}-${s.stop_order}`} onClick={() => onStop(s.id)}>
          <span className="stop-order">{s.stop_order}</span>
          <span className="ellipsis">{s.name}</span>
        </div>
      ))}
    </>
  );
}

function StopSearch({ onSelect, selectedId }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  useEffect(() => {
    const timer = setTimeout(() => api.stops(query.trim(), 40).then(setResults).catch(() => setResults([])), 250);
    return () => clearTimeout(timer);
  }, [query]);
  return (
    <>
      <input className="search" placeholder="Dayanacaq axtar" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="section-title">Dayanacaqlar</div>
      {results.map((s) => (
        <div
          className="stop-item"
          key={s.id}
          onClick={() => onSelect(s.id)}
          style={s.id === selectedId ? { color: "var(--blue)", fontWeight: 600 } : undefined}
        >
          <span className="dot" style={{ background: s.is_transport_hub ? "var(--blue)" : "#cbd5e1" }} />
          <span className="ellipsis">{s.name}</span>
          <span className="spacer" />
          <span className="small muted">{s.code}</span>
        </div>
      ))}
      {!results.length && <div className="empty">Dayanacaq tapılmadı</div>}
    </>
  );
}

function StopPanel({ data, onClose, onLine, onReported }) {
  const [reportLine, setReportLine] = useState(null);
  useEffect(() => setReportLine(data?.lines[0]?.id ?? null), [data?.stop.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="map-overlay" style={{ maxHeight: "calc(100% - 24px)", overflowY: "auto" }}>
      <div className="row">
        <strong style={{ fontSize: 15 }}>{data?.stop.name ?? "Yüklənir…"}</strong>
        <span className="spacer" />
        <button className="link" onClick={onClose} aria-label="Bağla">
          ✕
        </button>
      </div>
      {data && (
        <>
          <div className="small muted">Kod: {data.stop.code}</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 4, marginTop: 8 }}>
            {data.lines.map((l) => (
              <button key={l.id} className="btn ghost small" onClick={() => onLine(l.id)}>
                {l.number}
              </button>
            ))}
          </div>
          <div className="section-title">Gələn avtobuslar</div>
          {data.arrivals.map((a) => (
            <div className="arrival-item" key={a.bus_id}>
              <div className="pill" style={{ background: LEVEL_COLOR[a.density_level] }}>
                {a.line_number}
              </div>
              <div className="grow">
                <div className="small">
                  {pct(a.passenger_percentage)} dolu · {LEVEL_LABEL[a.density_level]}
                </div>
                <div className="small muted">
                  {formatDistance(a.distance_m)} · {a.stops_away} dayanacaq
                </div>
              </div>
              <div className={`eta ${a.eta_seconds < 45 ? "now" : ""}`}>{formatEta(a.eta_seconds)}</div>
            </div>
          ))}
          {!data.arrivals.length && <div className="empty">Yaxın vaxtda avtobus gözlənilmir</div>}
          {data.lines.length > 0 && (
            <>
              <div className="section-title">Dayanacaqda sıxlıq</div>
              <select
                value={reportLine ?? ""}
                onChange={(e) => setReportLine(Number(e.target.value))}
                style={{ width: "100%", padding: 6, borderRadius: 8, border: "1px solid var(--line)" }}
              >
                {data.lines.map((l) => (
                  <option key={l.id} value={l.id}>
                    Xətt {l.number}
                  </option>
                ))}
              </select>
              {reportLine && <ReportBox lineId={reportLine} stopId={data.stop.id} onReported={onReported} />}
            </>
          )}
        </>
      )}
    </div>
  );
}

function ReportBox({ lineId, stopId = null, onReported }) {
  const [busy, setBusy] = useState(false);
  const send = async (level) => {
    setBusy(true);
    try {
      await api.report({ line_id: lineId, stop_id: stopId, level });
      onReported("Təşəkkürlər! Bildirişiniz qəbul olundu.");
    } catch (err) {
      onReported(`Xəta: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="report-box">
      {REPORT_OPTIONS.map((o) => (
        <button
          key={o.level}
          className="btn ghost small"
          disabled={busy}
          onClick={() => send(o.level)}
          style={{ borderLeft: `3px solid ${LEVEL_COLOR[o.level]}` }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
