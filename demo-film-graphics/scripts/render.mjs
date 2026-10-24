// Headless render: node scripts/render.mjs --lines <path> --timeline <path> --out <dir>
//   [--only hook,market,decision,end-card,captions] [--captions-format prores|webm]
// Bundles once, then renders hook/market/decision/end-card as muted h264 mp4 and the caption
// overlay as a transparent file (default ProRes 4444 .mov; --captions-format webm = VP9 alpha).
// Relative paths resolve against the current directory.
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key?.startsWith("--") || argv[i + 1] === undefined) {
      throw new Error(`bad arguments near ${key ?? "end"}`);
    }
    out[key.slice(2)] = argv[i + 1];
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
for (const required of ["lines", "timeline", "out"]) {
  if (!args[required]) {
    console.error("usage: render.mjs --lines <path> --timeline <path> --out <dir> [--only a,b] [--captions-format prores|webm]");
    process.exit(2);
  }
}
const readJson = (p) => JSON.parse(readFileSync(path.resolve(p), "utf8"));
const inputProps = { lines: readJson(args.lines), timeline: readJson(args.timeline) };
const outDir = path.resolve(args.out);
mkdirSync(outDir, { recursive: true });

const captionsFormat = args["captions-format"] ?? "prores";
if (!["prores", "webm"].includes(captionsFormat)) {
  console.error("--captions-format must be prores or webm");
  process.exit(2);
}
const graphics = ["hook", "market", "decision", "end-card"];
const wanted = args.only ? args.only.split(",") : [...graphics, "captions"];

const here = path.dirname(fileURLToPath(import.meta.url));
const serveUrl = await bundle({ entryPoint: path.join(here, "..", "src", "index.ts") });

for (const id of wanted) {
  const composition = await selectComposition({ serveUrl, id, inputProps });
  let file;
  let options;
  if (id === "captions") {
    if (captionsFormat === "webm") {
      file = "captions.webm";
      options = { codec: "vp9", pixelFormat: "yuva420p", imageFormat: "png" };
    } else {
      file = "captions.mov";
      options = { codec: "prores", proResProfile: "4444", pixelFormat: "yuva444p10le", imageFormat: "png" };
    }
  } else {
    file = `${id}.mp4`;
    options = { codec: "h264", muted: true };
  }
  const outputLocation = path.join(outDir, file);
  await renderMedia({ composition, serveUrl, inputProps, outputLocation, ...options });
  console.log(`rendered ${outputLocation} (${composition.durationInFrames} frames)`);
}
