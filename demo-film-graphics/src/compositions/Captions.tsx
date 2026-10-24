import { AbsoluteFill, Sequence } from "remotion";
import type { FilmProps } from "../motion.ts";
import { s } from "../theme.ts";

const KIND_STYLE = {
  narrator: s.captionNarrator,
  caller: s.captionCaller,
  interrupted: s.captionInterrupted,
  reply: s.captionReply,
};

/** Full-length transparent overlay: one pill per `timeline.captions[]` entry, shown from
 *  `start_frame` to `end_frame` (exclusive). Text is rendered as plain text, never as HTML. */
export const Captions = ({ timeline }: FilmProps) => (
  <AbsoluteFill>
    {timeline.captions.map((cue) => (
      <Sequence
        key={cue.id}
        from={cue.start_frame}
        durationInFrames={Math.max(1, cue.end_frame - cue.start_frame)}
      >
        <div style={{ ...s.captionFill, ...s.captionBox }}>
          <div style={{ ...s.caption, ...KIND_STYLE[cue.kind] }}>{cue.text}</div>
        </div>
      </Sequence>
    ))}
  </AbsoluteFill>
);
