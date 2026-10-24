import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { LineDataSchema, TimelineSchema, graphicItems, slot } from "../src/data.ts";

const read = (rel: string) => JSON.parse(readFileSync(new URL(rel, import.meta.url), "utf8"));

test("docs/demo-film/lines.json parses", () => {
  const lines = LineDataSchema.parse(read("../../docs/demo-film/lines.json"));
  assert.equal(lines.graphics.length, 4);
});

test("fixtures/timeline.sample.json parses", () => {
  const timeline = TimelineSchema.parse(read("../fixtures/timeline.sample.json"));
  assert.equal(timeline.fps, 30);
  assert.equal(slot(timeline, "market").frames, 300);
});

test("unknown keys and wrong constants are rejected", () => {
  const timeline = read("../fixtures/timeline.sample.json");
  assert.throws(() => TimelineSchema.parse({ ...timeline, extra: 1 }));
  assert.throws(() => TimelineSchema.parse({ ...timeline, fps: 25 }));
});

test("sample timeline covers every graphic and its cues exist in lines.json", () => {
  const lines = LineDataSchema.parse(read("../../docs/demo-film/lines.json"));
  const timeline = TimelineSchema.parse(read("../fixtures/timeline.sample.json"));
  for (const g of lines.graphics) {
    const cueIds = slot(timeline, g.id).cues.map((c) => c.id);
    assert.deepEqual(cueIds, g.cues.map((c) => c.id), g.id);
  }
});

test("graphicItems and slot throw on an unknown graphic", () => {
  const lines = LineDataSchema.parse(read("../../docs/demo-film/lines.json"));
  assert.throws(() => graphicItems({ ...lines, graphics: [] }, "hook"));
  assert.throws(() => slot({ ...read("../fixtures/timeline.sample.json"), graphics: [] }, "hook"));
});
