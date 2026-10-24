// Visual language: the demo page's palette (factory/web/static/index.html :root variables).
// All styling lives here so the compositions carry no literal text (test/no-literal-text).
import type { CSSProperties } from "react";

export const color = {
  bg: "#f6f5f1",
  panel: "#ffffff",
  ink: "#1c1b19",
  muted: "#5d5a53",
  line: "#d9d6cd",
  accent: "#2f5bd3",
  accentInk: "#ffffff",
  pass: "#1d7a3e",
  fail: "#b3261e",
  warnBg: "#fff1d6",
  warnInk: "#6b4300",
};

export const font = {
  sans: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  mono: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
};

const fill: CSSProperties = {
  background: color.bg,
  color: color.ink,
  fontFamily: font.sans,
  alignItems: "center",
  justifyContent: "center",
  padding: "100px 120px",
};

export const s: Record<string, CSSProperties> = {
  fill,
  card: {
    background: color.panel,
    border: `3px solid ${color.line}`,
    borderRadius: 28,
    padding: "72px 96px",
    width: 1320,
    display: "flex",
    flexDirection: "column",
    gap: 48,
  },
  cardTitle: { fontSize: 96, fontWeight: 700, letterSpacing: -2 },
  verdict: {
    fontSize: 96,
    fontWeight: 800,
    whiteSpace: "nowrap",
    color: color.fail,
    border: `8px solid ${color.fail}`,
    borderRadius: 20,
    padding: "12px 40px",
    alignSelf: "flex-start",
    letterSpacing: 2,
  },
  verdictSlot: { height: 176 },
  stampOrigin: { transformOrigin: "left center" },
  runId: { fontFamily: font.mono, fontSize: 44, color: color.muted },

  layers: { display: "flex", gap: 32, width: 1560 },
  layer: {
    flex: 1,
    textAlign: "center",
    fontSize: 56,
    fontWeight: 700,
    letterSpacing: 4,
    padding: "36px 0",
    background: color.panel,
    border: `3px solid ${color.line}`,
    borderRadius: 20,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "300px 1fr 1fr 1fr",
    gap: 24,
    width: 1560,
    marginTop: 80,
    alignItems: "stretch",
  },
  gridHead: { fontSize: 44, color: color.muted, textAlign: "center", paddingBottom: 12 },
  rowLabel: { fontSize: 64, fontWeight: 800, display: "flex", alignItems: "center" },
  cell: {
    height: 150,
    borderRadius: 20,
    border: `3px solid ${color.line}`,
    background: color.panel,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  cellLit: { background: color.accent, border: `3px solid ${color.accent}` },
  dot: { width: 56, height: 56, borderRadius: 28, background: color.accentInk },

  quoteWrap: { display: "flex", flexDirection: "column", gap: 28, width: 1500 },
  quote: {
    fontSize: 132,
    fontWeight: 800,
    lineHeight: 1.05,
    letterSpacing: -3,
    borderLeft: `16px solid ${color.accent}`,
    paddingLeft: 56,
  },
  attribution: { fontFamily: font.mono, fontSize: 48, color: color.muted, paddingLeft: 72 },
  lines: { display: "flex", flexDirection: "column", gap: 20, marginTop: 72, width: 1500 },
  lineItem: {
    fontSize: 64,
    fontWeight: 700,
    letterSpacing: 2,
    background: color.panel,
    border: `3px solid ${color.line}`,
    borderRadius: 16,
    padding: "20px 40px",
  },

  notes: { display: "flex", flexDirection: "column", gap: 22, width: 1640 },
  note: {
    fontSize: 32,
    lineHeight: 1.3,
    color: color.ink,
    background: color.panel,
    border: `2px solid ${color.line}`,
    borderRadius: 12,
    padding: "14px 28px",
    fontFamily: font.mono,
  },
  notePitch: { fontFamily: font.sans, fontWeight: 700, borderColor: color.accent },

  // caption overlay: transparent frame, a dark pill near the bottom safe line
  captionBox: { position: "absolute", inset: 0, display: "flex", flexDirection: "column" },
  captionFill: { justifyContent: "flex-end", alignItems: "center", paddingBottom: 100 },
  caption: {
    maxWidth: 1500,
    textAlign: "center",
    fontFamily: font.sans,
    fontSize: 46,
    fontWeight: 600,
    lineHeight: 1.25,
    color: "#ffffff",
    background: "rgba(28, 27, 25, 0.86)",
    borderRadius: 18,
    padding: "18px 36px",
    borderBottom: `6px solid ${color.line}`,
  },
  captionNarrator: { borderBottomColor: color.line },
  captionCaller: { borderBottomColor: color.accent },
  captionReply: { borderBottomColor: color.pass },
  captionInterrupted: { borderBottomColor: color.fail, fontStyle: "italic" },
};
