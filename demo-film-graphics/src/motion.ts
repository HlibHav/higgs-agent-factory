import { interpolate, spring } from "remotion";
import { cueFrame, slot } from "./data.ts";
import type { GraphicId, Timeline } from "./data.ts";

export type FilmProps = {
  lines: import("./data.ts").LineData;
  timeline: Timeline;
};

/** 0 → 1 over `span` frames starting at `start`. */
export function ramp(frame: number, start: number, span = 12): number {
  return interpolate(frame, [start, start + span], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

/** Spring pop from `start`, 0 before it. */
export function pop(frame: number, fps: number, start: number): number {
  if (frame < start) return 0;
  return spring({ frame: frame - start, fps, config: { damping: 14, stiffness: 160 } });
}

/** The cue's frame in a graphic's slot; a cue the timeline lacks counts as frame 0. */
export function cueAt(timeline: Timeline, id: GraphicId, cueId: string): number {
  return cueFrame(slot(timeline, id), cueId) ?? 0;
}

/** Style helpers: transform strings live here, not in the compositions. */
export const stampTransform = (scale: number): string =>
  `scale(${1.6 - 0.6 * scale}) rotate(${-4 * scale}deg)`;
export const riseTransform = (t: number): string => `translateY(${(1 - t) * 24}px)`;
export const bumpTransform = (t: number): string => `scale(${1 + 0.2 * t * (1 - t)})`;
