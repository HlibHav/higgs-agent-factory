"""Voices and presets for the film's stems (F22). Domain: stdlib and the line data only."""

from dataclasses import dataclass
from typing import Literal

from factory.film.line_data import LineData

F22_PRESETS = ("chloe", "eleanor", "jake", "marcus", "nora", "oliver")  # F22
NARRATOR_CANDIDATES = ("eleanor", "nora", "oliver", "marcus")  # screenplay


class PresetError(ValueError):
    """A preset is missing, repeated or not in F22. The message names the preset or the role."""


@dataclass(frozen=True)
class StemRequest:
    role: Literal["narrator", "caller", "audition"]
    line_id: str
    text: str
    voice: str


def _check_one(role: str, preset: str | None) -> str:
    if preset is None or not preset.strip():
        raise PresetError(f"the {role} preset is missing: name one of {', '.join(F22_PRESETS)}")
    if preset not in F22_PRESETS:
        raise PresetError(
            f"{preset!r} is not a Higgs TTS preset (F22): use one of {', '.join(F22_PRESETS)}"
        )
    return preset


def check_presets(narrator: str | None, caller: str | None) -> tuple[str, str]:
    """AC-9 (missing), AC-10 (same twice), AC-7 (outside F22). Raises before any TTS call."""
    n = _check_one("narrator", narrator)
    c = _check_one("caller", caller)
    if n == c:
        raise PresetError(f"narrator and caller both use {n!r}: name two different presets")
    return n, c


def stem_requests(lines: LineData, narrator: str, caller: str) -> list[StemRequest]:
    out = [
        StemRequest("narrator", line.id, line.text, narrator)
        for beat in lines.beats
        for line in beat.narrator
    ]
    out += [StemRequest("caller", d.id, d.text, caller) for d in lines.dialogue]
    return out


def audition_requests(lines: LineData) -> list[StemRequest]:
    """AC-8: narrator candidates speak beat 1; every F22 preset speaks T1 as a caller."""
    beat1 = " ".join(n.text for n in lines.beats[0].narrator)
    t1 = next(d.text for d in lines.dialogue if d.id == "T1")
    out = [
        StemRequest("audition", f"narrator-{preset}", beat1, preset)
        for preset in NARRATOR_CANDIDATES
    ]
    out += [StemRequest("audition", f"caller-{preset}", t1, preset) for preset in F22_PRESETS]
    return out
