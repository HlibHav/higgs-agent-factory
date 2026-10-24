// Graphic, item and cue ids of docs/demo-film/lines.json, kept out of the compositions so
// they hold no string literal at all (test/no-literal-text). A wrong id throws at render time
// (itemText / slot), and test/ids.test.ts checks every id here exists in the data.
import type { GraphicId } from "./data.ts";

export const hook: GraphicId = "hook";
export const market: GraphicId = "market";
export const decision: GraphicId = "decision";
export const endCard: GraphicId = "end-card";

export const item = {
  hookCard: "card",
  hookVerdict: "verdict",
  hookRunId: "run-id",
  layers: ["layer-models", "layer-platforms", "layer-apps"],
  caps: ["cap-s2s", "cap-tts", "cap-avatar"],
  marketRow: "row",
  quote: "quote",
  attribution: "attribution",
  decisionLines: ["line-1", "line-2"],
} as const;

export const cue = {
  verdictStamp: "verdict-stamp",
  bosonRow: "boson-row",
  twoLines: "two-lines",
} as const;
