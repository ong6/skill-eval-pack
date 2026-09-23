#!/usr/bin/env python3
"""List the skills and agent manuals a repository already has, ranked against a proposed skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_skill import parse_frontmatter  # noqa: E402


REPO_SKILL_ROOTS = (".claude/skills", ".agents/skills", ".codex/skills")
GLOBAL_SKILL_GLOBS = (
    ".claude/skills/*/SKILL.md",
    ".agents/skills/*/SKILL.md",
    ".codex/skills/*/SKILL.md",
    ".claude/plugins/cache/**/skills/*/SKILL.md",
    ".codex/plugins/**/skills/*/SKILL.md",
)
MANUALS = ("AGENTS.md", "CLAUDE.md", ".claude/CLAUDE.md")
SKIP_DIRS = frozenset({"node_modules", "dist", "build", "vendor", "venv", "__pycache__"})
STEM = 5
STOPWORDS = frozenset(
    "a an and or the of to for in on with use when not this that it is are be as by from any "
    "skill skills agent agents claude codex".split()
)


def tokens(text: str) -> set[str]:
    """Crude prefix stems, so evaluate and evaluation or create and creation still match."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word[:STEM] for word in words if word not in STOPWORDS and len(word) > 2}


def nested_manuals(repo: Path) -> list[str]:
    found = []
    for path in repo.glob("*/**/AGENTS.md"):
        parts = path.relative_to(repo).parts[:-1]
        if not any(part.startswith(".") or part in SKIP_DIRS for part in parts):
            found.append(str(path.relative_to(repo)))
    return sorted(found)


def read_skill(skill_file: Path, scope: str) -> dict[str, str]:
    try:
        fields, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fields = {"description": f"unreadable: {error}"}
    return {
        "name": fields.get("name") or skill_file.parent.name,
        "description": fields.get("description", ""),
        "path": str(skill_file.parent),
        "scope": scope,
    }


def collect(repo: Path, include_global: bool, home: Path) -> tuple[list[dict[str, str]], list[str]]:
    seen: set[Path] = set()
    skills = []
    candidates = [(path, "repo") for root in REPO_SKILL_ROOTS for path in sorted((repo / root).glob("*/SKILL.md"))]
    if include_global:
        candidates += [(path, "global") for pattern in GLOBAL_SKILL_GLOBS for path in sorted(home.glob(pattern))]
    for skill_file, scope in candidates:
        resolved = skill_file.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        skills.append(read_skill(skill_file, scope))
    manuals = sorted(str(path.relative_to(repo)) for pattern in MANUALS for path in [repo / pattern] if path.is_file())
    manuals += nested_manuals(repo)
    return skills, manuals


def rank(skills: list[dict[str, str]], query: str) -> list[dict[str, object]]:
    wanted = tokens(query)
    ranked = []
    for skill in skills:
        have = tokens(f"{skill['name']} {skill['description']}")
        score = round(len(wanted & have) / len(wanted), 3) if wanted else 0.0
        ranked.append({**skill, "overlap": score, "shared_terms": sorted(wanted & have)})
    return sorted(ranked, key=lambda item: (-item["overlap"], item["name"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--query", help="what the proposed skill should do; ranks skills by the share of its terms they cover")
    parser.add_argument("--global", dest="include_global", action="store_true", help="also scan user-level skills and plugin caches")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"repository does not exist: {repo}", file=sys.stderr)
        return 2
    skills, manuals = collect(repo, args.include_global, Path.home())
    rows = rank(skills, args.query) if args.query else skills
    if args.json:
        print(json.dumps({"repo": str(repo), "manuals": manuals, "skills": rows}, indent=2))
        return 0
    print(f"manuals: {', '.join(manuals) or 'none'}")
    print(f"skills: {len(rows)}")
    for row in rows:
        overlap = f"{row['overlap']:.2f}  " if "overlap" in row else ""
        description = " ".join(str(row["description"]).split())
        print(f"  {overlap}{row['name']} [{row['scope']}] {description[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
