#!/usr/bin/env python3
"""Lint a skill folder against the Claude Code and Codex authoring rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_PATTERN = re.compile(r"\]\(([^)\s]+)\)")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the flat YAML subset skills use: scalars, quoted scalars and block scalars."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must open with a --- frontmatter block")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as error:
        raise ValueError("frontmatter block is not closed") from error
    fields: dict[str, str] = {}
    key = None
    block: list[str] | None = None
    folded = False
    for line in lines[1:end]:
        if block is not None and (line.startswith(" ") or not line.strip()):
            block.append(line.strip())
            continue
        if block is not None:
            fields[key] = (" " if folded else "\n").join(part for part in block if part)
            block = None
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            raise ValueError(f"unparseable frontmatter line: {line!r}")
        key, value = match.group(1), match.group(2).strip()
        if value[:1] in (">", "|"):
            block, folded = [], value.startswith(">")
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            fields[key] = value[1:-1]
        else:
            fields[key] = value
    if block is not None:
        fields[key] = (" " if folded else "\n").join(part for part in block if part)
    return fields, "\n".join(lines[end + 1:])


def lint(skill_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return [f"missing {skill_file}"], warnings
    try:
        fields, body = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
    except ValueError as error:
        return [str(error)], warnings

    name = fields.get("name", "")
    description = fields.get("description", "")
    extra = sorted(set(fields) - {"name", "description"})
    if extra:
        warnings.append(f"frontmatter keys beyond name and description: {', '.join(extra)}")
    if not name:
        errors.append("frontmatter needs name")
    elif not NAME_PATTERN.match(name) or len(name) > MAX_NAME:
        errors.append(f"name must be lowercase letters, digits and hyphens, at most {MAX_NAME} chars")
    elif name != skill_dir.resolve().name:
        errors.append(f"name {name!r} does not match folder {skill_dir.resolve().name!r}")
    if not description:
        errors.append("frontmatter needs description")
    else:
        if len(description) > MAX_DESCRIPTION:
            errors.append(f"description is {len(description)} chars; limit is {MAX_DESCRIPTION}")
        if "<" in description or ">" in description:
            errors.append("description must not contain angle brackets")
        if not re.search(r"\b(use|when|for)\b", description, re.IGNORECASE):
            warnings.append("description reads as a summary; name the requests that should trigger it")
        if not re.search(r"\bnot\b", description, re.IGNORECASE):
            warnings.append("description names no near-miss; add a 'not for ...' clause")

    body_lines = len(body.splitlines())
    if body_lines > MAX_BODY_LINES:
        errors.append(f"body is {body_lines} lines; split into references past {MAX_BODY_LINES}")

    for target in LINK_PATTERN.findall(body):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        relative = target.split("#", 1)[0]
        path = (skill_dir / relative).resolve()
        if not path.exists():
            errors.append(f"broken link: {target}")
        elif skill_dir.resolve() not in path.parents and path != skill_dir.resolve():
            warnings.append(f"link leaves the skill folder: {target}")
        elif len(Path(relative).parts) > 2:
            warnings.append(f"reference nested more than one level deep: {target}")

    policy = skill_dir / "agents" / "openai.yaml"
    if policy.is_file():
        explicit = re.search(r"allow_implicit_invocation:\s*false", policy.read_text(encoding="utf-8"))
        if explicit and "explicit" not in description.lower():
            warnings.append("Codex policy is explicit-only; say explicit-only in the description too")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--json", action="store_true", help="print a machine-readable result")
    args = parser.parse_args()
    errors, warnings = lint(args.skill_dir)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2))
    else:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        for message in warnings:
            print(f"warning: {message}", file=sys.stderr)
        if not errors:
            print(f"lint passed: {args.skill_dir}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
