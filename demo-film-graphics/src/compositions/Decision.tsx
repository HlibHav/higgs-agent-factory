import { AbsoluteFill, useCurrentFrame } from "remotion";
import { itemText } from "../data.ts";
import { cue, decision, item } from "../ids.ts";
import { cueAt, ramp, riseTransform } from "../motion.ts";
import type { FilmProps } from "../motion.ts";
import { s } from "../theme.ts";

const STAGGER = 10;

/** Beat 3: Boson's line with its attribution; the two decision lines enter on `two-lines`. */
export const Decision = ({ lines, timeline }: FilmProps) => {
  const frame = useCurrentFrame();
  const at = cueAt(timeline, decision, cue.twoLines);
  const text = (id: string) => itemText(lines, decision, id);
  return (
    <AbsoluteFill style={s.fill}>
      <div style={{ ...s.quoteWrap, opacity: ramp(frame, 0, 18) }}>
        <div style={s.quote}>{text(item.quote)}</div>
        <div style={s.attribution}>{text(item.attribution)}</div>
      </div>
      <div style={s.lines}>
        {item.decisionLines.map((id, i) => {
          const t = ramp(frame, at + i * STAGGER, 12);
          return (
            <div key={id} style={{ ...s.lineItem, opacity: t, transform: riseTransform(t) }}>
              {text(id)}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
