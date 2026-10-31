import { useEffect } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import { BAKU_CENTER, LEVEL_COLOR, LEVEL_LABEL, formatEta, pct } from "../format";

// Free basemap, no API key: the standard OpenStreetMap tile server (attribution required).
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> töhfəçiləri';

export function BaseMap({ children, zoom = 12 }) {
  return (
    <MapContainer center={BAKU_CENTER} zoom={zoom} preferCanvas zoomControl>
      <TileLayer url={TILE_URL} attribution={ATTRIBUTION} maxZoom={19} className="osm-tiles" />
      {children}
    </MapContainer>
  );
}

/** Fits the map to the given [lat, lng] points whenever `fitKey` changes. */
export function FitBounds({ points, fitKey, rightPadding = 40 }) {
  const map = useMap();
  useEffect(() => {
    if (points?.length > 1)
      map.fitBounds(L.latLngBounds(points), { paddingTopLeft: [40, 40], paddingBottomRight: [rightPadding, 40] });
    else if (points?.length === 1) map.setView(points[0], 16);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);
  return null;
}

const iconCache = new Map();
export function busIcon(label, level, layover = false) {
  const key = `${label}|${level}|${layover}`;
  if (!iconCache.has(key)) {
    iconCache.set(
      key,
      L.divIcon({
        className: "bus-icon",
        html: `<div class="bus-pin${layover ? " layover" : ""}" style="background:${LEVEL_COLOR[level]}">${label}</div>`,
        iconSize: [0, 0],
      }),
    );
  }
  return iconCache.get(key);
}

export function BusMarker({ bus, label }) {
  if (bus.live_latitude == null) return null;
  const layover = bus.status === "layover";
  return (
    <Marker
      position={[bus.live_latitude, bus.live_longitude]}
      icon={busIcon(label, bus.density_level, layover)}
      zIndexOffset={layover ? 0 : 1000}
    >
      <Popup>
        <strong>{bus.bus_plate}</strong>
        <br />
        Doluluq: {bus.passenger_count}/{bus.passenger_limit} ({pct(bus.passenger_percentage)}) —{" "}
        {LEVEL_LABEL[bus.density_level]}
        <br />
        {layover ? (
          "Son dayanacaqda fasilə"
        ) : (
          <>
            Növbəti: {bus.next_stop_name || "—"} ({formatEta(bus.next_stop_eta_seconds)})
            <br />
            Sürət: {bus.speed_kmh} km/s
          </>
        )}
      </Popup>
    </Marker>
  );
}
