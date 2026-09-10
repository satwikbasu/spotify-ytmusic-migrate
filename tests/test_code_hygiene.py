"""Guards against debugging leftovers reaching production code."""

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _offending_lines(needle: str):
    hits = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line:
                rel = path.relative_to(SRC.parent)
                hits.append(f"{rel}:{lineno}: {line.strip()[:80]}")
    return hits


def test_no_debug_print_statements_in_src():
    """Debug output must go through logging, not print().

    The migrator's per-track loop and the progress callback both printed
    directly to stdout, which produced one line per track on a real run.
    """
    hits = _offending_lines('print(f"DEBUG')
    hits += _offending_lines('print("DEBUG')
    assert hits == [], "raw DEBUG print() left in src/:\n" + "\n".join(hits)
