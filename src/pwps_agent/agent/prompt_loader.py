from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPT_DIR = Path("configs/prompts")


@lru_cache(maxsize=32)
def load_prompt(name: str, prompt_dir: Path = PROMPT_DIR) -> str:
    if "/" in name or "\\" in name:
        raise ValueError("Prompt name must not include path separators")
    path = prompt_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
