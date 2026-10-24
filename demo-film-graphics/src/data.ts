// Zod mirror of factory/film/line_data.py (source) and docs/demo-film/film-data.schema.json.
// Changes go source first, then the schema file, then this mirror; test/schema-mirror.test.ts
// holds the three together.
import { z } from "zod";

const GraphicId = z.enum(["hook", "market", "decision", "end-card"]);
const BeatId = z.enum([
  "hook",
  "market",
  "decision",
  "skills",
  "gate-coach",
  "not-rubber-stamp",
  "talk",
  "for-boson",
]);

const NarratorLine = z.strictObject({ id: z.string(), text: z.string() });
const BeatImage = z.strictObject({ id: z.string(), path: z.string(), at_line: z.string() });
const Beat = z.strictObject({
  number: z.number().int().min(1).max(8),
  id: BeatId,
  target_s: z.number(),
  picture: z.enum(["graphic", "page", "take", "images+graphic"]),
  narrator: z.array(NarratorLine),
  images: z.array(BeatImage).default([]),
});
const DialogueLine = z.strictObject({ id: z.enum(["T1", "T2"]), text: z.string() });
const GraphicItem = z.strictObject({ id: z.string(), text: z.string() });
const GraphicCue = z.strictObject({ id: z.string(), at_line: z.string() });
const Graphic = z.strictObject({
  id: GraphicId,
  beat: z.number().int().min(1).max(8),
  starts_at_line: z.string().nullable(),
  items: z.array(GraphicItem),
  cues: z.array(GraphicCue),
});
const ClaimMapping = z.strictObject({
  line_id: z.string(),
  phrase: z.string(),
  row: z.string().nullable(),
});
const Exemption = z.strictObject({ line_id: z.string(), phrase: z.string(), reason: z.string() });
const Highlight = z.strictObject({
  id: z.string(),
  beat: z.literal(5),
  at_line: z.string(),
  target: z.string(),
});

export const LineDataSchema = z.strictObject({
  schema_version: z.literal(1),
  beats: z.array(Beat),
  dialogue: z.array(DialogueLine),
  graphics: z.array(Graphic),
  claims: z.array(ClaimMapping),
  exemptions: z.array(Exemption),
  highlights: z.array(Highlight),
  interrupted_caption: z.string(),
});

const Cue = z.strictObject({ id: z.string(), frame: z.number().int() });
const GraphicSlot = z.strictObject({
  id: GraphicId,
  frames: z.number().int(),
  cues: z.array(Cue),
});
const CaptionCue = z.strictObject({
  id: z.string(),
  kind: z.enum(["narrator", "caller", "interrupted", "reply"]),
  text: z.string(),
  start_frame: z.number().int().min(0),
  end_frame: z.number().int().min(0),
});

export const TimelineSchema = z.strictObject({
  schema_version: z.literal(1),
  fps: z.literal(30),
  width: z.literal(1920),
  height: z.literal(1080),
  total_frames: z.number().int().min(1),
  graphics: z.array(GraphicSlot),
  captions: z.array(CaptionCue),
});

export type LineData = z.infer<typeof LineDataSchema>;
export type Timeline = z.infer<typeof TimelineSchema>;
export type GraphicId = z.infer<typeof GraphicId>;
export type GraphicItem = z.infer<typeof GraphicItem>;
export type GraphicSlot = z.infer<typeof GraphicSlot>;
export type CaptionCue = z.infer<typeof CaptionCue>;

/** The text items of one graphic, in `lines.json` order. */
export function graphicItems(lines: LineData, id: GraphicId): GraphicItem[] {
  const graphic = lines.graphics.find((g) => g.id === id);
  if (!graphic) throw new Error(`lines.json has no graphic ${id}`);
  return graphic.items;
}

/** The timeline slot (length and cue frames) of one graphic beat. */
export function slot(timeline: Timeline, id: GraphicId): GraphicSlot {
  const found = timeline.graphics.find((g) => g.id === id);
  if (!found) throw new Error(`timeline.json has no slot for ${id}`);
  return found;
}

/** Text of the item `itemId` of graphic `id`; throws when absent so a missing line is loud. */
export function itemText(lines: LineData, id: GraphicId, itemId: string): string {
  const item = graphicItems(lines, id).find((i) => i.id === itemId);
  if (!item) throw new Error(`lines.json graphic ${id} has no item ${itemId}`);
  return item.text;
}

/** Frame of the cue `cueId` in a slot, or null when the timeline does not carry it. */
export function cueFrame(s: GraphicSlot, cueId: string): number | null {
  return s.cues.find((c) => c.id === cueId)?.frame ?? null;
}
