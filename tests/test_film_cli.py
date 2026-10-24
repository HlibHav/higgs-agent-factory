"""The `factory.film` CLI over doubles: exit codes, key hygiene, the timeline command
(AC-53, plus the refusals each command maps to exit 2)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.film import cli
from factory.film.app import FilmApp
from factory.film.ffmpeg import Ffmpeg
from factory.film.line_data import Timeline, load_lines
from factory.film.take_log import TakeLog
from tests.film_doubles import CountingTts, FakeServer, Scenario, Sim

LINES = load_lines()
FAKE_KEY = "sk-fake-key-must-never-appear-0123456789"
NOW = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
SNAPSHOT = Path(__file__).parent / "fixtures" / "film" / "claims-2026-10-24.md"
RUN_LINE = re.compile(r"^run (\d{8}T\d{6}Z-[0-9a-f]{6})$", re.MULTILINE)


class Harness:
    def __init__(self, tmp_path: Path, scenarios: list[Scenario] | None = None) -> None:
        self.out = tmp_path / "film"
        self.results = tmp_path / "results"
        (self.results / "cards").mkdir(parents=True)
        (self.results / "cards" / "c.json").write_text("{}")
        self.sim = Sim(scenarios)
        self.tts = CountingTts(0.3)
        self.envs: list[object] = []

    def factory(self, env: object, out_dir: Path) -> FilmApp:
        self.envs.append(env)
        return FilmApp(
            tts=self.tts,
            model="higgs-tts-3",
            page_factory=self.sim.factory,
            server_factory=lambda url: FakeServer(),
            ffmpeg=Ffmpeg(),
            clock=lambda: NOW,
            sleep=self.sim.sleep,
        )

    def main(self, *argv: str, env: dict[str, str] | None = None) -> int:
        return cli.main(
            list(argv),
            env=env or {"BOSON_API_KEY": FAKE_KEY},
            out_dir=self.out,
            app_factory=self.factory,
        )

    def stems(self) -> int:
        return self.main("stems", "--narrator", "nora", "--caller", "jake")

    def run(self, takes: int = 3) -> int:
        return self.main(
            "run",
            "--takes",
            str(takes),
            "--base-url",
            "http://127.0.0.1:8000",
            "--results-dir",
            str(self.results),
        )


def _run_id(text: str) -> str:
    m = RUN_LINE.search(text)
    assert m, text
    return m.group(1)


def test_render_exit_2_lists_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    h = Harness(tmp_path)
    assert h.stems() == 0
    monkeypatch.setattr(cli, "CLAIMS_PATH", SNAPSHOT)
    code = h.main("render", "--run", "20261024T180000Z-abcdef", "--graphics", str(tmp_path))
    err = capsys.readouterr().err
    assert code == 2
    assert "b2-s2" in err and "end-card/market" in err and "render refused" in err


def test_render_without_keeper_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    h = Harness(tmp_path)
    assert h.stems() == 0
    code = h.main("render", "--run", "20261024T180000Z-abcdef", "--graphics", str(tmp_path))
    assert code == 2 and "keeper" in capsys.readouterr().err


def test_claims_command_current_register_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["claims"]) == 0
    assert "claims gate ok" in capsys.readouterr().out


def test_claims_command_snapshot_fails_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "CLAIMS_PATH", SNAPSHOT)
    assert cli.main(["claims"]) == 2
    assert "b2-s2" in capsys.readouterr().err


def test_timeline_command_writes_timeline_json_and_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    h = Harness(tmp_path)
    assert h.main("timeline") == 2  # no stems yet
    assert "stems" in capsys.readouterr().err
    assert h.stems() == 0
    capsys.readouterr()
    assert h.main("timeline") == 0
    out = capsys.readouterr().out
    assert "beat 1:" in out and "beat 7: no take window" in out and "provisional" in out
    provisional = Timeline.model_validate_json((h.out / "timeline.json").read_text())
    assert [s.id for s in provisional.graphics] == ["hook", "market", "decision", "end-card"]

    assert h.run(3) == 0
    run_id = _run_id(capsys.readouterr().out)
    assert h.main("timeline", "--run", run_id) == 2  # no keeper yet
    capsys.readouterr()
    assert h.main("keeper", "--run", run_id, "--take", "1") == 0
    assert h.main("timeline", "--run", run_id) == 0
    out = capsys.readouterr().out
    assert "total:" in out and "final" in out
    final = Timeline.model_validate_json((h.out / "timeline.json").read_text())
    assert final.graphics == provisional.graphics  # slots do not depend on the take
    kinds = {c.kind for c in final.captions}
    assert kinds == {"narrator", "caller", "interrupted", "reply"}
    assert final.total_frames > provisional.total_frames
    assert max(c.end_frame for c in final.captions) <= final.total_frames


def test_fake_key_absent_from_every_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    h = Harness(tmp_path)
    assert h.main("auditions") == 0
    assert h.stems() == 0
    assert h.main("timeline") == 0
    assert h.run(3) == 0
    run_id = _run_id(capsys.readouterr().out)
    assert h.main("keeper", "--run", run_id, "--take", "1") == 0
    assert h.main("timeline", "--run", run_id) == 0
    assert h.main("claims") == 0
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out and FAKE_KEY not in captured.err
    files = [p for p in h.out.rglob("*") if p.is_file()]
    assert len(files) > 20
    for path in files:
        assert FAKE_KEY.encode() not in path.read_bytes(), path
    assert h.envs and all(isinstance(e, dict) for e in h.envs)  # env only went to the factory


def test_config_error_names_the_variable_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class ConfigError(Exception):
        pass

    def broken(env: object, out_dir: Path) -> FilmApp:
        raise ConfigError("BOSON_API_KEY is not set")

    code = cli.main(
        ["auditions"], env={"BOSON_API_KEY": FAKE_KEY}, out_dir=tmp_path, app_factory=broken
    )
    err = capsys.readouterr().err
    assert code == 2 and "BOSON_API_KEY" in err and FAKE_KEY not in err


def test_refusals_map_to_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    h = Harness(tmp_path)
    assert h.main("stems") == 2
    assert "narrator" in capsys.readouterr().err
    assert h.main("stems", "--narrator", "nora", "--caller", "nora") == 2
    assert "different" in capsys.readouterr().err
    assert h.main("stems", "--narrator", "nora", "--caller", "alloy") == 2
    assert h.tts.requests == []  # refused before any TTS request
    assert h.stems() == 0
    assert h.run(2) == 2 and "take count" in capsys.readouterr().err
    assert h.main("keeper", "--run", "../etc", "--take", "1") == 2
    assert h.main("render", "--run", "bad", "--graphics", ".") == 2
    assert cli.main(["claims"], app_factory=None) == 0
    assert cli.main(["stems"], out_dir=tmp_path) == 2  # no app: says how to start
    assert cli.main([]) == 2


def test_keeper_refuses_a_dropped_take(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    h = Harness(tmp_path, [Scenario(reply_after_s=None)])
    assert h.stems() == 0
    assert h.run(3) == 0
    run_id = _run_id(capsys.readouterr().out)
    assert h.main("keeper", "--run", run_id, "--take", "1") == 2
    assert "no reply to T1" in capsys.readouterr().err
    assert TakeLog(h.out / "runs" / run_id / "takes.jsonl").keeper() is None


def test_run_ended_early_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    h = Harness(tmp_path, [Scenario(blocked="gate run")])
    assert h.stems() == 0
    assert h.run(3) == 1
    captured = capsys.readouterr()
    assert "blocked: gate run" in captured.err and "take 1" in captured.out
    json.loads((h.out / "stems" / "manifest.json").read_text())
