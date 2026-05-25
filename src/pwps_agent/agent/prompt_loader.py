from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _PACKAGE_DIR.parents[1]

PROMPT_DIR = _PROJECT_DIR / "configs" / "prompts"
DOMAIN_SKILL_DIR = _PACKAGE_DIR / "domain_skills"


@dataclass(frozen=True)
class DomainSkill:
    name: str
    content: str


def _load_markdown_file(name: str, base_dir: Path, kind: str) -> str:
    if "/" in name or "\\" in name:
        raise ValueError(f"{kind} name must not include path separators")

    path = base_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"{kind} file not found: {path}")

    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=32)
def load_prompt(name: str, prompt_dir: Path = PROMPT_DIR) -> str:
    return _load_markdown_file(name, prompt_dir, "Prompt")


@lru_cache(maxsize=32)
def load_domain_skill(
    name: str,
    skill_dir: Path = DOMAIN_SKILL_DIR,
) -> DomainSkill:
    content = _load_markdown_file(name, skill_dir, "Domain skill")
    return DomainSkill(name=name, content=content)


def load_domain_skill_bundle(
    names: list[str],
    skill_dir: Path = DOMAIN_SKILL_DIR,
) -> str:
    sections = ["# Domain Skill Context"]
    for name in names:
        skill = load_domain_skill(name, skill_dir)
        sections.extend(["", f"## Domain Skill: {skill.name}", "", skill.content])
    return "\n".join(sections).strip()
