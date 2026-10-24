import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { itemText } from "../data.ts";
import { cue, hook, item } from "../ids.ts";
import { cueAt, pop, ramp, stampTransform } from "../motion.ts";
import type { FilmProps } from "../motion.ts";
import { s } from "../theme.ts";

/** Beat 1: the v1 Eval Card; the REJECTED stamp lands on the `verdict-stamp` cue. */
export const Hook = ({ lines, timeline }: FilmProps) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scale = pop(frame, fps, cueAt(timeline, hook, cue.verdictStamp));
  const text = (id: string) => itemText(lines, hook, id);
  return (
    <AbsoluteFill style={s.fill}>
      <div style={{ ...s.card, opacity: ramp(frame, 0, 15) }}>
        <div style={s.cardTitle}>{text(item.hookCard)}</div>
        <div style={s.verdictSlot}>
          <div
            style={{
              ...s.verdict,
              ...s.stampOrigin,
              opacity: scale > 0 ? 1 : 0,
              transform: stampTransform(scale),
            }}
          >
            {text(item.hookVerdict)}
          </div>
        </div>
        <div style={s.runId}>{text(item.hookRunId)}</div>
      </div>
    </AbsoluteFill>
  );
};
