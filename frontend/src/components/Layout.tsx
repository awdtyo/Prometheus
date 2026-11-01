import { Outlet, NavLink } from "react-router-dom";

interface Props {}

export function Layout(_props: Props) {

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__left">
          <div className="brand">
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
            <NavLink
              to="/"
              className={({ isActive }) => `topbar-nav__item${isActive ? " topbar-nav__item--active" : ""}`}
            >
              Scenarios
            </NavLink>
            <NavLink
              to="/causal-graph"
              className={({ isActive }) => `topbar-nav__item${isActive ? " topbar-nav__item--active" : ""}`}
            >
              Causal Graph
            </NavLink>
            <NavLink
              to="/hypotheses"
              className={({ isActive }) => `topbar-nav__item${isActive ? " topbar-nav__item--active" : ""}`}
            >
              Hypotheses
            </NavLink>
            <NavLink
              to="/evaluation"
              className={({ isActive }) => `topbar-nav__item${isActive ? " topbar-nav__item--active" : ""}`}
            >
              Evaluation
            </NavLink>
          </nav>
        </div>

        <div className="topbar__right">
          <a href="/docs" target="_blank" rel="noreferrer" style={linkStyle}>
            API docs
          </a>
        </div>
      </header>

      <main className="page-wrap">
        <Outlet />
      </main>
    </div>
  );
}

const linkStyle: React.CSSProperties = {
  color: "var(--muted)",
  textDecoration: "none",
  fontFamily: "var(--mono)",
  fontSize: 0.75,
  padding: "6px 10px",
  border: "1px solid var(--border)",
  borderRadius: 4,
  marginLeft: 10,
};
