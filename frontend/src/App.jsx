import { NavLink, Route, Routes } from "react-router-dom";
import { api, usePolling } from "./api";
import { formatClock } from "./format";
import OperatorPage from "./pages/OperatorPage";
import PassengerPage from "./pages/PassengerPage";

export default function App() {
  const { data: sim, error } = usePolling(() => api.simulation(), [], 2000);
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" /> Smart Transit Bakı
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Sərnişin
          </NavLink>
          <NavLink to="/operator">Operator paneli</NavLink>
        </nav>
        <div className="clock" title="Simulyasiya saatı">
          <span className={`live-dot ${error || !sim ? "off" : ""}`} />
          {error ? "Server əlçatan deyil" : `Simulyasiya ×${sim?.speed ?? "-"}`}
          <strong>{formatClock(sim?.clock)}</strong>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<PassengerPage />} />
        <Route path="/operator" element={<OperatorPage />} />
      </Routes>
    </div>
  );
}
