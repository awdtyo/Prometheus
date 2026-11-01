interface Props {
  status: number;
  code: string | null;
  detail: string;
  onRetry?: () => void;
}

export function ApiErrorDisplay({ status, code, detail, onRetry }: Props) {
  return (
    <div style={styles.container}>
      <p style={styles.kind}>
        {status} {code || "error"}
      </p>
      <p style={styles.detail}>{detail}</p>
      {onRetry && (
        <button style={styles.button} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 24,
    border: "1px solid var(--border-strong)",
    background: "var(--surface)",
    color: "var(--text)",
    maxWidth: 700,
    margin: "0 auto",
  },
  kind: { margin: "0 0 8px", fontFamily: "var(--mono)", fontSize: 0.85, color: "var(--red)" },
  detail: { margin: "0 0 16px", fontSize: 0.9, color: "var(--muted)" },
  button: {
    padding: "8px 16px",
    background: "var(--amber)",
    color: "#161006",
    border: "none",
    borderRadius: 6,
    fontWeight: 650,
    cursor: "pointer",
  },
};
