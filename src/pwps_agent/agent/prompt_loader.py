from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROMPT_DIR = Path("configs/prompts")
DOMAIN_SKILL_DIR = Path("src/pwps_agent/domain_skills")


@dataclass(frozen=True)
class DomainSkill:
    name: str
    content: str


@lru_cache(maxsize=32)
def load_prompt(name: str, prompt_dir: Path = PROMPT_DIR) -> str:
    if "/" in name or "\\" in name:
        raise ValueError("Prompt name must not include path separators")
    path = prompt_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=32)
def load_domain_skill(
    name: str,
    skill_dir: Path = DOMAIN_SKILL_DIR,
) -> DomainSkill:
    if "/" in name or "\\" in name:
        raise ValueError("Domain skill name must not include path separators")
    path = skill_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Domain skill file not found: {path}")
    return DomainSkill(name=name, content=path.read_text(encoding="utf-8").strip())


def load_domain_skill_bundle(
    names: list[str],
    skill_dir: Path = DOMAIN_SKILL_DIR,
) -> str:
    sections = ["# Domain Skill Context"]
    for name in names:
        skill = load_domain_skill(name, skill_dir)
        sections.extend(["", f"## Domain Skill: {skill.name}", "", skill.content])
    return "\n".join(sections).strip()
