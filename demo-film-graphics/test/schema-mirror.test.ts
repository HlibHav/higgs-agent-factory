import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { z } from "zod";
import { LineDataSchema, TimelineSchema } from "../src/data.ts";

type Json = Record<string, any>;

const schemaFile: Json = JSON.parse(
  readFileSync(new URL("../../docs/demo-film/film-data.schema.json", import.meta.url), "utf8"),
);

// Reduce a JSON Schema node to the parts the mirror must agree on: type, enum/const, bounds,
// nullability, object property names and the required list. Titles and descriptions are free.
function norm(node: Json, defs: Json): unknown {
  if (node.$ref) return norm(defs[String(node.$ref).split("/").pop()!], defs);
  // nullable: pydantic writes anyOf [X, null], zod writes type [X, "null"]
  if (Array.isArray(node.type) && node.type.includes("null")) {
    const rest = node.type.filter((x: string) => x !== "null");
    return { nullable: norm({ ...node, type: rest.length === 1 ? rest[0] : rest }, defs) };
  }
  if (node.anyOf?.some((n: Json) => n.type === "null")) {
    const rest = node.anyOf.filter((n: Json) => n.type !== "null");
    return { nullable: norm(rest.length === 1 ? rest[0] : { anyOf: rest }, defs) };
  }
  if (node.anyOf) {
    return { anyOf: node.anyOf.map((n: Json) => norm(n, defs)).sort((a: unknown, b: unknown) => JSON.stringify(a).localeCompare(JSON.stringify(b))) };
  }
  const out: Json = {};
  if (node.const !== undefined) out.const = node.const;
  if (node.enum) out.enum = [...node.enum].sort();
  // a const fixes the value; pydantic says integer, zod says number for the same literal
  if (node.type && node.const === undefined) out.type = node.type;
  // zod adds safe-integer bounds to .int(); the pydantic schema has none
  for (const k of ["minimum", "maximum"]) {
    if (node[k] !== undefined && Math.abs(node[k]) < 1e9) out[k] = node[k];
  }
  if (node.properties) {
    out.properties = Object.fromEntries(
      Object.keys(node.properties)
        .sort()
        .map((k) => [k, norm(node.properties[k], defs)]),
    );
    out.required = [...(node.required ?? [])].sort();
    out.additionalProperties = node.additionalProperties ?? true;
  }
  if (node.items) out.items = norm(node.items, defs);
  return out;
}

for (const [name, zodSchema] of [
  ["LineData", LineDataSchema],
  ["Timeline", TimelineSchema],
] as const) {
  test(`zod ${name} matches film-data.schema.json`, () => {
    const mine = z.toJSONSchema(zodSchema, { io: "input", unrepresentable: "any" }) as Json;
    const theirs = schemaFile[name] as Json;
    assert.deepEqual(norm(mine, {}), norm(theirs, theirs.$defs ?? {}));
  });
}
