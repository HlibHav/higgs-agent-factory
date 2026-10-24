import { Composition } from "remotion";
import type { CalculateMetadataFunction } from "remotion";
import lineJson from "../../docs/demo-film/lines.json";
import timelineJson from "../fixtures/timeline.sample.json";
import { Captions } from "./compositions/Captions.tsx";
import { Decision } from "./compositions/Decision.tsx";
import { EndCard } from "./compositions/EndCard.tsx";
import { Hook } from "./compositions/Hook.tsx";
import { Market } from "./compositions/Market.tsx";
import { LineDataSchema, TimelineSchema, slot } from "./data.ts";
import type { GraphicId } from "./data.ts";
import type { FilmProps } from "./motion.ts";

// Studio defaults only: the sample timeline and the real lines.json. The render script passes
// both files as input props.
const defaultProps: FilmProps = {
  lines: LineDataSchema.parse(lineJson),
  timeline: TimelineSchema.parse(timelineJson),
};

const graphicMeta =
  (id: GraphicId): CalculateMetadataFunction<FilmProps> =>
  ({ props }) => ({
    durationInFrames: slot(TimelineSchema.parse(props.timeline), id).frames,
    fps: props.timeline.fps,
    width: props.timeline.width,
    height: props.timeline.height,
  });

const captionMeta: CalculateMetadataFunction<FilmProps> = ({ props }) => ({
  durationInFrames: props.timeline.total_frames,
  fps: props.timeline.fps,
  width: props.timeline.width,
  height: props.timeline.height,
  defaultCodec: "prores",
  defaultVideoImageFormat: "png",
  defaultPixelFormat: "yuva444p10le",
  defaultProResProfile: "4444",
});

const common = {
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 1,
  defaultProps,
} as const;

export const Root = () => (
  <>
    <Composition id="hook" component={Hook} calculateMetadata={graphicMeta("hook")} {...common} />
    <Composition id="market" component={Market} calculateMetadata={graphicMeta("market")} {...common} />
    <Composition id="decision" component={Decision} calculateMetadata={graphicMeta("decision")} {...common} />
    <Composition id="end-card" component={EndCard} calculateMetadata={graphicMeta("end-card")} {...common} />
    <Composition id="captions" component={Captions} calculateMetadata={captionMeta} {...common} />
  </>
);
