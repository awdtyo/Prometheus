interface Props {
  message?: string;
  action?: React.ReactNode;
}

export function Empty({ message = "No data available.", action }: Props) {
  return (
    <div style={styles.container}>
      <p style={styles.text}>{message}</p>
      {action && <div style={styles.action}>{action}</div>}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: 48,
    color: "var(--muted)",
    textAlign: "center",
  },
  text: { margin: "0 0 16px", fontSize: 0.9, fontFamily: "var(--mono)" },
  action: { marginTop: 0 },
};
