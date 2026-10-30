import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { CardSaved } from "./pages/CardSaved";
import "./styles.css";

// /card-saved is public (Grow redirects customers there), so it skips the login gate.
const isPublicPage = window.location.pathname === "/card-saved";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isPublicPage ? <CardSaved /> : <App />}</React.StrictMode>,
);
