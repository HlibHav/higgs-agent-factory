import { AbsoluteFill, useCurrentFrame } from "remotion";
import { graphicItems } from "../data.ts";
import { endCard } from "../ids.ts";
import { ramp } from "../motion.ts";
import type { FilmProps } from "../motion.ts";
import { s } from "../theme.ts";

const STAGGER = 6;

/** Beat 8: every end-card item from `lines.json`, in order, as the card's footnotes. The last
 *  item (the pitch attribution) takes the sans, bold style. */
export const EndCard = ({ lines }: FilmProps) => {
  const frame = useCurrentFrame();
  const items = graphicItems(lines, endCard);
  return (
    <AbsoluteFill style={s.fill}>
      <div style={s.notes}>
        {items.map((item, i) => (
          <div
            key={item.id}
            style={{
              ...s.note,
              ...(i === items.length - 1 ? s.notePitch : {}),
              opacity: ramp(frame, i * STAGGER, 14),
            }}
          >
            {item.text}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
