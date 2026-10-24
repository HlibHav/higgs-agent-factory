# demo-film-graphics

Remotion compositions for the Higgs Agent Factory demo film (ADR
`docs/architecture-decisions/2026-10-24-remotion-for-demo-film-graphics.md`). The Python side
only consumes the rendered files. Everything shown comes from two data files:

- `docs/demo-film/lines.json` (text, read by the claims gate too)
- `results/film/timeline.json` (frames; `fixtures/timeline.sample.json` for development)

`src/data.ts` is the zod mirror of `factory/film/line_data.py`; `test/schema-mirror.test.ts`
holds it to `docs/demo-film/film-data.schema.json`. Compositions hold no literal text
(`test/no-literal-text.test.ts`); styling is in `src/theme.ts` (the demo page palette), element
ids in `src/ids.ts`.

Compositions (1920x1080, 30 fps, length from the timeline): `hook`, `market`, `decision`,
`end-card`, and `captions` (full film length, transparent, from `timeline.captions[]`).

## Setup and checks

Node 24 is needed (type stripping for `node --test`). Anaconda's node 20 shadows it, so put
Homebrew first:

```bash
export PATH=/opt/homebrew/bin:$PATH
npm --prefix demo-film-graphics ci
npm --prefix demo-film-graphics run typecheck
npm --prefix demo-film-graphics test
```

## Render (headless)

The first render downloads a headless Chrome (about 94 MB). Paths are relative to
`demo-film-graphics/` (npm runs the script there) or absolute.

```bash
# the film (real timeline); from the repo root
npm --prefix demo-film-graphics run render -- \
  --lines ../docs/demo-film/lines.json --timeline ../results/film/timeline.json \
  --out ../results/film/graphics

# development, from the sample timeline
npm --prefix demo-film-graphics run render -- \
  --lines ../docs/demo-film/lines.json --timeline fixtures/timeline.sample.json --out out
```

Output: `hook.mp4`, `market.mp4`, `decision.mp4`, `end-card.mp4` (h264, muted) and
`captions.mov` (ProRes 4444 with alpha, `yuva444p10le`, full film length). Add
`--captions-format webm` for `captions.webm` (VP9 with alpha), `--only hook,captions` to
render a subset.

Overlay in the mux (the local ffmpeg has no `subtitles` or `drawtext`):

```bash
ffmpeg -i film-no-captions.mp4 -i captions.mov -filter_complex "[0:v][1:v]overlay=shortest=1" ...
```

A WebM alpha input needs the libvpx decoder: put `-c:v libvpx-vp9` before `-i captions.webm`.

## Studio

```bash
npm --prefix demo-film-graphics run studio
```

Studio defaults to `lines.json` and the sample timeline.
