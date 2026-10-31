-- Static network (imported from map.ayna.gov.az)
CREATE TABLE IF NOT EXISTS lines (
    id               INTEGER PRIMARY KEY,
    number           TEXT NOT NULL UNIQUE,
    carrier          TEXT,
    first_point      TEXT,
    last_point       TEXT,
    route_length_km  REAL,
    duration_minutes INTEGER,
    tariff           TEXT,
    payment_type     TEXT,
    region           TEXT,
    working_zone     TEXT
);

CREATE TABLE IF NOT EXISTS stops (
    id               INTEGER PRIMARY KEY,
    code             TEXT,
    name             TEXT NOT NULL,
    address          TEXT,
    latitude         REAL,
    longitude        REAL,
    is_transport_hub INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS line_stops (
    line_id          INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    stop_id          INTEGER NOT NULL REFERENCES stops(id),
    direction        TEXT NOT NULL CHECK (direction IN ('forward', 'backward')),
    stop_order       INTEGER NOT NULL,
    distance_along_m REAL NOT NULL,
    PRIMARY KEY (line_id, direction, stop_order)
);
CREATE INDEX IF NOT EXISTS idx_line_stops_stop ON line_stops(stop_id);

CREATE TABLE IF NOT EXISTS route_shapes (
    line_id          INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    direction        TEXT NOT NULL CHECK (direction IN ('forward', 'backward')),
    seq              INTEGER NOT NULL,
    latitude         REAL NOT NULL,
    longitude        REAL NOT NULL,
    distance_along_m REAL NOT NULL,
    PRIMARY KEY (line_id, direction, seq)
);

-- Fleet and live state
CREATE TABLE IF NOT EXISTS buses (
    line_id              INTEGER NOT NULL REFERENCES lines(id),
    bus_id               INTEGER PRIMARY KEY,
    bus_plate            TEXT NOT NULL UNIQUE,
    passenger_count      INTEGER NOT NULL DEFAULT 0 CHECK (passenger_count >= 0),
    passenger_percentage REAL GENERATED ALWAYS AS (ROUND(passenger_count * 100.0 / passenger_limit, 1)) VIRTUAL,
    passenger_limit      INTEGER NOT NULL CHECK (passenger_limit > 0),
    forwarding_stop_id   INTEGER REFERENCES stops(id),
    live_longitude       REAL,
    live_latitude        REAL,
    direction            TEXT NOT NULL DEFAULT 'forward' CHECK (direction IN ('forward', 'backward')),
    position_m           REAL NOT NULL DEFAULT 0,
    speed_kmh            REAL NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'in_service' CHECK (status IN ('in_service', 'layover')),
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_buses_line ON buses(line_id);

CREATE TABLE IF NOT EXISTS bus_telemetry (
    id              INTEGER PRIMARY KEY,
    bus_id          INTEGER NOT NULL REFERENCES buses(bus_id) ON DELETE CASCADE,
    line_id         INTEGER NOT NULL REFERENCES lines(id),
    latitude        REAL,
    longitude       REAL,
    passenger_count INTEGER NOT NULL,
    speed_kmh       REAL NOT NULL,
    recorded_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_line_time ON bus_telemetry(line_id, recorded_at);

-- Crowdsourcing and analytics
CREATE TABLE IF NOT EXISTS crowd_reports (
    id          INTEGER PRIMARY KEY,
    line_id     INTEGER NOT NULL REFERENCES lines(id),
    stop_id     INTEGER REFERENCES stops(id),
    bus_id      INTEGER REFERENCES buses(bus_id) ON DELETE SET NULL,
    level       TEXT NOT NULL CHECK (level IN ('low', 'medium', 'high')),
    source      TEXT NOT NULL CHECK (source IN ('passenger', 'simulated')),
    reported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_line_time ON crowd_reports(line_id, reported_at);

CREATE TABLE IF NOT EXISTS line_density (
    id            INTEGER PRIMARY KEY,
    line_id       INTEGER NOT NULL REFERENCES lines(id),
    occupancy_pct REAL NOT NULL,
    report_score  REAL,
    score         REAL NOT NULL,
    level         TEXT NOT NULL CHECK (level IN ('low', 'medium', 'high')),
    active_buses  INTEGER NOT NULL,
    computed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_density_line_time ON line_density(line_id, computed_at);
CREATE INDEX IF NOT EXISTS idx_density_time ON line_density(computed_at);

CREATE TABLE IF NOT EXISTS alerts (
    id                      INTEGER PRIMARY KEY,
    line_id                 INTEGER NOT NULL REFERENCES lines(id),
    type                    TEXT NOT NULL,
    message                 TEXT NOT NULL,
    suggested_bus_count     INTEGER NOT NULL DEFAULT 1,
    suggested_donor_line_id INTEGER REFERENCES lines(id),
    status                  TEXT NOT NULL CHECK (status IN ('open', 'resolved')),
    created_at              TEXT NOT NULL,
    resolved_at             TEXT,
    resolved_by             TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, line_id);
