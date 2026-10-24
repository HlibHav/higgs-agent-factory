"""Line data for the demo film: the contract between the recorder (Python) and the graphics
(Remotion).

`docs/demo-film/lines.json` holds the screenplay in machine form. The claims gate reads it, the
timeline is computed from it, and the Remotion compositions draw their text and captions from
it. Pure data and validation: no I/O except `load_lines`.

Changes go source first (this file), then `docs/demo-film/film-data.schema.json`, then the
zod mirror in `demo-film-graphics/src/data.ts`.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LINES_PATH = Path(__file__).resolve().parents[2] / "docs" / "demo-film" / "lines.json"

GraphicId = Literal["hook", "market", "decision", "end-card"]
BeatId = Literal[
    "hook",
    "market",
    "decision",
    "skills",
    "gate-coach",
    "not-rubber-stamp",
    "talk",
    "for-boson",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NarratorLine(_Model):
    """One narrator sentence, one TTS stem, one caption. Ids are `b<n>-s<k>`, or `b7-intro`
    and `b7-outro` for beat 7."""

    id: str
    text: str


class BeatImage(_Model):
    """A still shown in a beat from `at_line` until the next image or the next change."""

    id: str
    path: str
    at_line: str


class Beat(_Model):
    number: int = Field(ge=1, le=8)
    id: BeatId
    target_s: float
    picture: Literal["graphic", "page", "take", "images+graphic"]
    narrator: list[NarratorLine]
    images: list[BeatImage] = Field(default_factory=list)


class DialogueLine(_Model):
    """A trainee line fed in as the microphone; also captioned while it plays (AC-40)."""

    id: Literal["T1", "T2"]
    text: str


class GraphicItem(_Model):
    """A piece of text a graphic shows. Its claims line id is `<graphic id>/<item id>`."""

    id: str
    text: str


class GraphicCue(_Model):
    """A graphic element that starts when the narrator sentence `at_line` starts."""

    id: str
    at_line: str


class Graphic(_Model):
    id: GraphicId
    beat: int = Field(ge=1, le=8)
    starts_at_line: str | None
    items: list[GraphicItem]
    cues: list[GraphicCue]


class ClaimMapping(_Model):
    """A number-bearing phrase of a line and the CLAIMS row (its exact "claim" cell) that backs
    it. `row` None means unmapped, and the claims gate fails the line."""

    line_id: str
    phrase: str
    row: str | None


class Exemption(_Model):
    """A rhetorical number word ("three layers") that is not a claim. The claims gate passes
    a number word only inside a listed exemption; each one carries its reason."""

    line_id: str
    phrase: str
    reason: str


class Highlight(_Model):
    """A beat 5 highlight on the recorded page, shown when `at_line` starts. `target` is a
    Playwright locator on the coach box."""

    id: str
    beat: Literal[5]
    at_line: str
    target: str


class LineData(_Model):
    schema_version: Literal[1]
    beats: list[Beat]
    dialogue: list[DialogueLine]
    graphics: list[Graphic]
    claims: list[ClaimMapping]
    exemptions: list[Exemption]
    highlights: list[Highlight]
    # Caption for the interrupted reply to T1 (AC-55): never text the agent did not speak (F27).
    interrupted_caption: str


class Cue(_Model):
    id: str
    frame: int


class GraphicSlot(_Model):
    id: GraphicId
    frames: int
    cues: list[Cue]


class CaptionCue(_Model):
    """One caption on the film's clock. `text` is complete, so the caption overlay needs no
    lookup: narrator sentences and caller lines copy `lines.json`, the interrupted reply to T1
    is `LineData.interrupted_caption`, and `reply` (the reply to T2) is the text the page
    received, shown as plain text. Frames are on the film's clock, `end_frame` exclusive."""

    id: str
    kind: Literal["narrator", "caller", "interrupted", "reply"]
    text: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)


class Timeline(_Model):
    """Written by `factory.film timeline` to `results/film/timeline.json`; read by Remotion."""

    schema_version: Literal[1]
    fps: Literal[30]
    width: Literal[1920]
    height: Literal[1080]
    total_frames: int = Field(ge=1)
    graphics: list[GraphicSlot]
    captions: list[CaptionCue]


def load_lines(path: Path = LINES_PATH) -> LineData:
    return LineData.model_validate_json(path.read_text(encoding="utf-8"))
