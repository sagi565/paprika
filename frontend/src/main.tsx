import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { CardSaved } from "./pages/CardSaved";
import { Terms } from "./pages/Terms";
import { SiteFooter } from "./components/SiteFooter";
import "./styles.css";

// Public pages skip the login gate: /card-saved (Grow redirects customers there) and /terms.
const PUBLIC_PAGES: Record<string, () => React.JSX.Element> = { "/card-saved": CardSaved, "/terms": Terms };
const Page = PUBLIC_PAGES[window.location.pathname.replace(/\/+$/, "")] ?? App;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Page />
    <SiteFooter />
  </React.StrictMode>,
);
