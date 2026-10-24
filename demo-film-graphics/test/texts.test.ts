import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { LineDataSchema, graphicItems } from "../src/data.ts";
import type { GraphicId } from "../src/data.ts";

const raw = JSON.parse(
  readFileSync(new URL("../../docs/demo-film/lines.json", import.meta.url), "utf8"),
);
const lines = LineDataSchema.parse(raw);

for (const id of ["hook", "market", "decision", "end-card"] as GraphicId[]) {
  test(`graphicItems(${id}) is exactly the lines.json items`, () => {
    const expected = raw.graphics.find((g: { id: string }) => g.id === id).items;
    assert.deepEqual(graphicItems(lines, id), expected);
  });
}

test("hook, decision and end card carry the verdict, run ids and boson.ai attribution", () => {
  const texts = (id: GraphicId) => graphicItems(lines, id).map((i) => i.text);
  assert.ok(texts("hook").includes("REJECTED · 4 / 6"));
  assert.ok(texts("hook").includes("20261024T174839Z-6f4ab3b5"));
  assert.ok(texts("decision").includes("boson.ai"));
  const runs = texts("end-card").find((t) => t.includes("20261024T180110Z-b501e4a3"));
  assert.ok(runs?.includes("20261024T174839Z-6f4ab3b5"));
});
