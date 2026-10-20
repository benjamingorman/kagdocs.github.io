"""Read public text interfaces and lex scripts without executing game code."""

from __future__ import annotations

import re
from pathlib import Path

from kagdocs.syntax import ParsedSource

_MANUAL_LISTS = (
    "Functions.txt",
    "Objects.txt",
    "Hooks.txt",
    "Enums.txt",
    "Variables.txt",
    "TypeDefs.txt",
)


def lex(text: str) -> list:
    """Lossless syntax tokens, also used to highlight Manual declarations."""
    return ParsedSource.parse(text).tokens()


def _missing_inputs(directory: Path) -> list[str]:
    manual = directory / "Manual/interface"
    base = directory / "Base"
    missing = [str(manual / name) for name in _MANUAL_LISTS if not (manual / name).is_file()]
    if not base.is_dir():
        missing.append(str(base))
    if not (manual / "Objects").is_dir():
        missing.append(str(manual / "Objects"))
    return missing


def read_installation(directory: Path) -> dict:
    """Read Manual text and Base scripts. Nothing from the install is executed."""
    directory = Path(directory)
    missing = _missing_inputs(directory)
    if missing:
        raise ValueError("Invalid KAG_DIR; missing required inputs:\n" + "\n".join(missing))
    manual, base = directory / "Manual/interface", directory / "Base"
    paths = sorted(manual.rglob("*.txt")) + sorted(base.rglob("*.as"))
    files, builds = [], set()
    for path in paths:
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        relative = path.relative_to(directory).as_posix()
        if relative.startswith("Manual/"):
            match = re.search(r"SCRIPT INTERFACE FOR BUILD\s+(\d+)", text)
            if not match:
                raise ValueError(f"Missing build header in {relative}")
            builds.add(int(match[1]))
        parsed = ParsedSource.parse(text)
        files.append(
            {
                "path": relative,
                "tokens": parsed.tokens(),
                **({"syntax": parsed} if relative.startswith("Base/") else {}),
            }
        )
    if len(builds) != 1:
        raise ValueError(f"Manual files have inconsistent build numbers: {sorted(builds)}")
    return {"build": builds.pop(), "files": files}
