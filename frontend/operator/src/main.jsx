import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "@transit/shared/styles.css";
import Topbar from "@transit/shared/components/Topbar.jsx";
import OperatorPage from "./OperatorPage.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <div className="app">
      <Topbar title="Operator paneli" />
      <OperatorPage />
    </div>
  </StrictMode>,
);
