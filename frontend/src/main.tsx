import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import App from "./App";
import "./index.css";
import { router } from "./router";
import { RouterRoot } from "./router";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element #root was not found.");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <RouterRoot />
  </React.StrictMode>
);