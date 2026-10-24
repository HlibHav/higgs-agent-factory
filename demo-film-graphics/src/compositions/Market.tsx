import { AbsoluteFill, useCurrentFrame } from "remotion";
import { itemText } from "../data.ts";
import { cue, item, market } from "../ids.ts";
import { bumpTransform, cueAt, ramp } from "../motion.ts";
import type { FilmProps } from "../motion.ts";
import { s } from "../theme.ts";

const STAGGER = 8;

/** Beat 2: three layers on top; below them Boson's row lights across the three capabilities
 *  from the `boson-row` cue. */
export const Market = ({ lines, timeline }: FilmProps) => {
  const frame = useCurrentFrame();
  const lit = cueAt(timeline, market, cue.bosonRow);
  const text = (id: string) => itemText(lines, market, id);
  return (
    <AbsoluteFill style={s.fill}>
      <div style={s.layers}>
        {item.layers.map((id, i) => (
          <div key={id} style={{ ...s.layer, opacity: ramp(frame, i * STAGGER, 14) }}>
            {text(id)}
          </div>
        ))}
      </div>
      <div style={{ ...s.grid, opacity: ramp(frame, item.layers.length * STAGGER, 14) }}>
        <div />
        {item.caps.map((id) => (
          <div key={id} style={s.gridHead}>
            {text(id)}
          </div>
        ))}
        <div style={s.rowLabel}>{text(item.marketRow)}</div>
        {item.caps.map((id, i) => {
          const on = ramp(frame, lit + i * STAGGER, 10);
          return (
            <div
              key={id}
              style={{ ...s.cell, ...(on > 0 ? s.cellLit : {}), transform: bumpTransform(on) }}
            >
              <div style={{ ...s.dot, opacity: on }} />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
