import { useEffect, useRef, useState } from "react";

async function request(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

const qs = (params) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v != null && v !== "" && search.set(k, v));
  const s = search.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // passenger
  lines: (q) => request(`/api/lines${qs({ q })}`),
  line: (id) => request(`/api/lines/${id}`),
  lineBuses: (id) => request(`/api/lines/${id}/buses`),
  stops: (q, limit = 30) => request(`/api/stops${qs({ q, limit })}`),
  stop: (id) => request(`/api/stops/${id}`),
  report: (body) => post("/api/reports", body),
  // operator
  overview: () => request("/api/operator/overview"),
  density: (level) => request(`/api/operator/density${qs({ level })}`),
  fleet: () => request("/api/operator/buses"),
  history: (lineId, minutes = 60) => request(`/api/operator/density/${lineId}/history${qs({ minutes })}`),
  alerts: (status, limit = 50) => request(`/api/operator/alerts${qs({ status, limit })}`),
  resolve: (id) => post(`/api/operator/alerts/${id}/resolve`),
  dispatch: (id, body) => post(`/api/operator/alerts/${id}/dispatch`, body),
  // demo
  simulation: () => request("/api/demo/simulation"),
  surge: (lineId) => post(`/api/demo/surge/${lineId}`),
};

/** Live push from /ws/live. Reconnects automatically; switching lineId doesn't reconnect. */
export function useLive({ lineId = null, operator = false } = {}) {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  const lineRef = useRef(lineId);
  lineRef.current = lineId;

  useEffect(() => {
    let closed = false;
    let retry;
    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const params = qs({ line_id: lineRef.current, operator: operator ? "true" : null });
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/live${params}`);
      socketRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onmessage = (event) => setData(JSON.parse(event.data));
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socketRef.current?.close();
    };
  }, [operator]);

  useEffect(() => {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ line_id: lineId }));
  }, [lineId]);

  return { data, connected };
}

/** Calls `load` now and every `intervalMs`, re-starting when `deps` change. */
export function usePolling(load, deps, intervalMs) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let active = true;
    const run = () =>
      load()
        .then((result) => active && (setData(result), setError(null)))
        .catch((err) => active && setError(err));
    if (deps.every((d) => d !== null && d !== undefined)) {
      run();
      const timer = setInterval(run, intervalMs);
      return () => {
        active = false;
        clearInterval(timer);
      };
    }
    setData(null);
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, setData };
}
