"""Normalize blank lines in rendered configs so CI diffs stay stable."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "rendered"


def tidy(text: str) -> str:
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def main() -> None:
    for path in sorted(ROOT.rglob("*.cfg")):
        path.write_text(tidy(path.read_text()))


if __name__ == "__main__":
    main()
