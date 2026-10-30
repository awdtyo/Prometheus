/* =============================================================================
   React Router Configuration
   -------------------------------------------------------
   Defines all routes for the Mission Autopsy command center.
   Uses data-driven routing where the sidebar and top bar derive their
   active state from the current pathname.
   ============================================================================= */

import { createBrowserRouter, RouterProvider, RouteObject } from "react-router-dom";
import type { ReactNode } from "react";

import { MissionOverviewPage } from "./pages/MissionOverview";
import { ScenarioExplorerPage } from "./pages/ScenarioExplorer";
import { InvestigationWorkspacePage } from "./pages/InvestigationWorkspace";
import { CausalGraphPage } from "./pages/CausalGraph";
import { HypothesisAnalysisPage } from "./pages/HypothesisAnalysis";
import { EvaluationDashboardPage } from "./pages/EvaluationDashboard";
import { LiveInvestigationPage } from "./pages/LiveInvestigation";
import { ErrorPlaceholder } from "./components/Layout";

/* -------------------------------------------------------
   Route definitions
   ------------------------------------------------------- */

const routes: RouteObject[] = [
  {
    path: "/",
    element: <MissionOverviewPage />,
    errorElement: <ErrorPlaceholder message="Mission overview not found." />,
  },
  {
    path: "/scenarios",
    element: <ScenarioExplorerPage />,
    errorElement: <ErrorPlaceholder message="Scenario explorer not found." />,
  },
  {
    path: "/workspace",
    element: <InvestigationWorkspacePage />,
    errorElement: <ErrorPlaceholder message="Investigation workspace not found." />,
  },
  {
    path: "/causal-graph",
    element: <CausalGraphPage />,
    errorElement: <ErrorPlaceholder message="Causal graph not found." />,
  },
  {
    path: "/hypotheses",
    element: <HypothesisAnalysisPage />,
    errorElement: <ErrorPlaceholder message="Hypothesis analysis not found." />,
  },
  {
    path: "/evaluation",
    element: <EvaluationDashboardPage />,
    errorElement: <ErrorPlaceholder message="Evaluation dashboard not found." />,
  },
  {
    path: "/investigation",
    element: <LiveInvestigationPage />,
    errorElement: <ErrorPlaceholder message="Live investigation not found." />,
  },
  /* -------------------------------------------------------
     Catch-all 404
     ------------------------------------------------------- */
  {
    path: "/*",
    element: (
      <div className="page">
        <h2>404 — Page not found</h2>
        <p>The route you requested does not exist in the Mission Autopsy command center.</p>
        <ErrorPlaceholder message="Unknown route." />
      </div>
    ),
  },
];

/* -------------------------------------------------------
   Router creation
   ------------------------------------------------------- */

export const router = createBrowserRouter(routes);

/* -------------------------------------------------------
   Root renderer
   ------------------------------------------------------- */

type RootElement = ReactNode;

export function RouterRoot({ initialEntries }: { initialEntries?: string[] }) {
  return <RouterProvider router={router} initial={initialEntries} />;
}