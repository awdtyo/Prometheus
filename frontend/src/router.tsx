import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ScenariosPage } from "./pages/Scenarios";
import { InvestigationWorkspacePage } from "./pages/InvestigationWorkspace";
import { CausalGraphPage } from "./pages/CausalGraph";
import { HypothesesPage } from "./pages/Hypotheses";
import { EvaluationPage } from "./pages/Evaluation";

function ErrorElement() {
  return (
    <div style={{ padding: 24, color: "var(--text)", fontFamily: "var(--mono)" }}>
      <h2>Route error</h2>
      <p>The requested route could not be rendered.</p>
    </div>
  );
}

function NotFound() {
  return (
    <div style={{ padding: 24, color: "var(--text)", fontFamily: "var(--mono)" }}>
      <h2>404 — Page not found</h2>
      <p>The route you requested does not exist.</p>
    </div>
  );
}

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    errorElement: <ErrorElement />,
    children: [
      { index: true, element: <ScenariosPage /> },
      { path: "scenarios", element: <ScenariosPage /> },
      { path: "investigation/:id", element: <InvestigationWorkspacePage /> },
      { path: "causal-graph", element: <CausalGraphPage /> },
      { path: "hypotheses", element: <HypothesesPage /> },
      { path: "evaluation", element: <EvaluationPage /> },
      { path: "/*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
