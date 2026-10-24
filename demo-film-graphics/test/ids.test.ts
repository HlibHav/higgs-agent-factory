import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { LineDataSchema, TimelineSchema, graphicItems, slot } from "../src/data.ts";
import { cue, decision, endCard, hook, item, market } from "../src/ids.ts";

const read = (rel: string) => JSON.parse(readFileSync(new URL(rel, import.meta.url), "utf8"));
const lines = LineDataSchema.parse(read("../../docs/demo-film/lines.json"));
const timeline = TimelineSchema.parse(read("../fixtures/timeline.sample.json"));

test("every item id the compositions use exists in lines.json", () => {
  const has = (g: typeof hook, ids: readonly string[]) => {
    const present = graphicItems(lines, g).map((i) => i.id);
    for (const id of ids) assert.ok(present.includes(id), `${g}/${id}`);
  };
  has(hook, [item.hookCard, item.hookVerdict, item.hookRunId]);
  has(market, [...item.layers, ...item.caps, item.marketRow]);
  has(decision, [item.quote, item.attribution, ...item.decisionLines]);
  assert.ok(graphicItems(lines, endCard).length > 0);
});

test("every cue id the compositions use exists in the sample timeline", () => {
  assert.ok(slot(timeline, hook).cues.some((c) => c.id === cue.verdictStamp));
  assert.ok(slot(timeline, market).cues.some((c) => c.id === cue.bosonRow));
  assert.ok(slot(timeline, decision).cues.some((c) => c.id === cue.twoLines));
});
