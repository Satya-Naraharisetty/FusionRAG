import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// PWA Service Worker Registration
if ("serviceWorker" in navigator && !import.meta.env.DEV) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((_reg) => {
        // eslint-disable-next-line no-console
        console.log("PWA Service Worker registered successfully.");
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("PWA Service Worker registration failed:", err);
      });
  });
}
