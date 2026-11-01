export function Loading() {
  return (
    <div style={styles.container}>
      <p style={styles.text}>Loading…</p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 48,
    color: "var(--muted)",
    fontFamily: "var(--mono)",
    fontSize: 0.85,
  },
  text: { margin: 0 },
};
