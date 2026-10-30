/* =============================================================================
   Shared Layout Components
   ============================================================================= */

import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  ConnectionStatus,
  HealthResponse,
} from "../types/api";
import { getHealth } from "../api/client";

/* -------------------------------------------------------
   Sidebar Navigation
   ------------------------------------------------------- */

export interface SidebarNavItem {
  id: key;
  label: string;
  path: string;
  icon?: ReactNode;
  description?: string;
  disabled?: boolean;
}

const SIDEBAR_NAV: SidebarNavItem[] = [
  { id: "overview", label: "Mission Overview", path: "/", description: "Overall mission status and health" },
  { id: "scenarios", label: "Scenario Explorer", path: "/scenarios", description: "View and manage scenario configurations" },
  { id: "workspace", label: "Investigation Workspace", path: "/workspace", description: "Active investigation dashboard" },
  { id: "causal", label: "Causal Graph", path: "/causal-graph", description: "Interactive causal/temporal graph" },
  { id: "hypotheses", label: "Hypothesis Analysis", path: "/hypotheses", description: "Competing AI-generated hypotheses" },
  { id: "evaluation", label: "Evaluation Dashboard", path: "/evaluation", description: "Run metrics and evaluation results" },
];

export function Sidebar({
  currentPath,
}: {
  currentPath: string;
}) {
  return (
    <nav className="sidebar" aria-label="Main navigation">
      <ul>
        {SIDEBAR_NAV.map((item) => (
          <li
            key={item.id}
            className={`sidebar__item ${
              currentPath === item.path
                ? "sidebar__item--active"
                : ""
            }`}
            onClick={() => {
              // Prevent default link behavior; routing handled by NavLink
            }}
          >
            <span className="sidebar__mark" />
            <span className="sidebar__label">{item.label}</span>
            {item.description && (
              <span className="sidebar__description">{item.description}</span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

/* -------------------------------------------------------
   Top Navigation Bar (with status)
   ------------------------------------------------------- */

export interface TopBarProps {
  /** Current path for active link highlighting */
  currentPath: string;
  /** Callback when user clicks the brand/logo */
  onBrandClick?: () => void;
}

/** Top bar with brand, navigation, and health status */
export function TopBar({
  currentPath,
  onBrandClick,
}: TopBarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const health = useHealthStatus();

  return (
    <header className="topbar">
      <div className="topbar__left">
        <div className="brand" onClick={onBrandClick} onMouseUp={e => e.preventDefault()}>
          <div className="brand__mark" aria-hidden="true">
            <span />
          </div>
          <div>
            <p className="brand__name">Mission Autopsy</p>
            <p className="brand__sub">Incident reconstruction console</p>
          </div>
        </div>
      </div>

      <div className="topbar__center">
        <nav className="topbar-nav">
          {SIDEBAR_NAV.map((item) => (
            <button
              key={item.id}
              className={`topbar-nav__item ${
                currentPath === item.path ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate(item.path)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="topbar__right">
        <div className="health-status" aria-label="API connection status">
          <HealthBadge status={health.status} />
          <span className="health-status__text">
            {health.status === "online" ? "API online" : health.status === "offline" ? "API offline" : "Checking"}
          </span>
        </div>
      </div>
    </header>
  );
}

type HealthStatusReturn = {
  status: ConnectionStatus;
  message?: string;
};

function useHealthStatus(): HealthStatusReturn {
  const [health, setHealth] = React.useState<HealthStatusReturn>({ status: "loading" });

  React.useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((data) => {
        setHealth({
          status: "online" as ConnectionStatus,
          data,
        });
      })
      .catch(() => {
        setHealth({
          status: "offline" as ConnectionStatus,
          message: "Unable to reach the API.",
        });
      });

    return () => {
      controller.abort();
    };
  }, []);

  return health;
}

/* -------------------------------------------------------
   Page Layout Shell
   ------------------------------------------------------- */

export interface PageLayoutProps {
  /** Page title */
  title: string;
  /** Primary content */
  children: ReactNode;
  /** Show sidebar navigation */
  showSidebar?: boolean;
  /** Show top bar (breadcrumb/status) */
  showTopBar?: boolean;
}

/** Main layout wrapping sidebar, top bar, and content area */
export function PageLayout({
  title,
  children,
  showSidebar = true,
  showTopBar = true,
}: PageLayoutProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentPath = location.pathname;

  return (
    <div className="app-layout">
      {showSidebar && <Sidebar currentPath={currentPath} />}
      <main className="app-main">
        {showTopBar && (
          <TopBar
            currentPath={currentPath}
            onBrandClick={() => navigate("/")}
          />
        )}
        <section className="content">
          <h1 className="content__title">{title}</h1>
          <p className="content__subtitle">{getSubtitleForPath(currentPath)}</p>
          {children}
        </section>
      </main>
    </div>
  );
}

function getSubtitleForPath(path: string): string {
  const map: Record<string, string> = {
    "/": "Overall mission status and telemetry health",
    "/scenarios": "View and manage scenario configurations",
    "/workspace": "Active investigation dashboard",
    "/causal-graph": "Interactive causal and temporal graph",
    "/hypotheses": "Competing AI-generated hypotheses",
    "/evaluation": "Run metrics and evaluation results",
  };
  return map[path] || "Mission Autopsy";
}

/* -------------------------------------------------------
   Content Error Boundary hint
   ------------------------------------------------------- */

export function ErrorPlaceholder({
  message = "Unable to load page.",
}: { message?: string } = {}) {
  return (
    <div className="error-placeholder">
      <p className="error-placeholder__message">{message}</p>
    </div>
  );
}