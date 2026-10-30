import type { ConnectionStatus } from "../types/api";

const LABELS: Record<ConnectionStatus, string> = {
  loading: "Checking API",
  online: "API online",
  offline: "API offline",
};

interface HealthBadgeProps {
  status: ConnectionStatus;
}

export function HealthBadge({ status }: HealthBadgeProps) {
  return (
    <span className={`health-badge health-badge--${status}`}>
      <span className="health-badge__dot" aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
