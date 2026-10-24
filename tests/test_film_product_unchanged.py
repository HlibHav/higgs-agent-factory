"""AC-6: the demo film recorder changes nothing in the product the film shows."""

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# sha256 of the files on `main` at the start of the demo-film plan (commit 9e69a68).
PINNED = {
    "factory/web/static/index.html": (
        "66cb9edcba385237eb2e6412e15273da4585cc806f36080be45415f891909701"
    ),
    "factory/web/app.py": "3760ea5d66e922b43b256d8458c07f14ee505947aa3072ab4637691e5222da9f",
    "factory/live/session.py": "14c274c6134515713412aea4df37902cab22f9ee9ec1641341bbfedb645e15ef",
}
FORBIDDEN = ("factory.web", "factory.live")


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_page_and_server_files_match_plan_start() -> None:
    actual = {path: _sha256(path) for path in PINNED}
    assert actual == PINNED


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_film_never_imports_web() -> None:
    offenders: list[str] = []
    for source in sorted((ROOT / "factory" / "film").glob("**/*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for name in _imported_modules(tree):
            if any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN):
                offenders.append(f"{source.relative_to(ROOT)} imports {name}")
    assert offenders == []
