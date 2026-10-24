import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const dir = new URL("../src/compositions/", import.meta.url);
const files = readdirSync(dir).filter((f) => f.endsWith(".tsx"));

// Module specifiers ("react", "../data.ts") are code, not display text.
function offenders(file: string): string[] {
  const src = ts.createSourceFile(file, readFileSync(new URL(file, dir), "utf8"), ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const hasLetterOrDigit = (t: string) => /[\p{L}\p{N}]/u.test(t);
  const visit = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) return;
    if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node) ||
        ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) &&
      hasLetterOrDigit(node.text)
    ) {
      found.push(`${file}: ${JSON.stringify(node.text)}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(src);
  return found;
}

test("there are compositions to check", () => {
  assert.ok(files.length >= 5);
});

test("no JSX text or string literal with a letter or digit in src/compositions", () => {
  assert.deepEqual(files.flatMap(offenders), []);
});
