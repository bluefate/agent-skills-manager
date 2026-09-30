"""Skill reading and management utilities."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from agent_skills_manager.models import MoveOperation, MovePlan, Skill


SKILL_FILE_NAME = "SKILL.md"


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from a markdown file."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _build_skill_from_dir(skill_dir: Path, source: str = "") -> Skill:
    """Read a skill directory and return a Skill model."""
    skill_file = skill_dir / SKILL_FILE_NAME
    name = skill_dir.name
    description = ""
    tags: list[str] = []

    if skill_file.is_file():
        try:
            content = skill_file.read_text(encoding="utf-8")
            meta = _parse_frontmatter(content)
            name = meta.get("name", name)
            description = meta.get("description", "")
            raw_tags = meta.get("tags", [])
            tags = [str(t) for t in raw_tags] if isinstance(raw_tags, (list, tuple)) else []
        except OSError:
            pass

    return Skill(
        name=name,
        path=skill_dir,
        source=source,
        description=description,
        tags=tags,
        exists=True,
        is_symlink=skill_dir.is_symlink(),
    )


def list_skills(directory: Path, source: str = "") -> list[Skill]:
    """List all skill directories under a path."""
    if not directory.exists():
        return []
    skills: list[Skill] = []
    for entry in sorted(directory.iterdir()):
        if entry.name == ".system":
            continue
        if entry.is_dir() or entry.is_symlink():
            skills.append(_build_skill_from_dir(entry, source=source))
    return skills


def read_skill(path: Path) -> Skill | None:
    """Read a single skill by directory path."""
    if not path.exists() or not (path.is_dir() or path.is_symlink()):
        return None
    return _build_skill_from_dir(path)


def read_skill_content(path: Path) -> str | None:
    """Return a skill's source text when its SKILL.md file is available."""
    skill_file = path / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None
    try:
        return skill_file.read_text(encoding="utf-8")
    except OSError:
        return None


def write_skill_content(path: Path, content: str) -> Skill:
    """Create or update a skill directory from complete SKILL.md content."""
    path.mkdir(parents=True, exist_ok=True)
    skill_file = path / SKILL_FILE_NAME
    skill_file.write_text(content, encoding="utf-8")
    return _build_skill_from_dir(path)


def write_skill_metadata(path: Path, name: str, description: str, tags: list[str]) -> Skill:
    """Create or update a skill directory and its SKILL.md metadata."""
    path.mkdir(parents=True, exist_ok=True)
    skill_file = path / SKILL_FILE_NAME

    existing = ""
    if skill_file.exists():
        existing = skill_file.read_text(encoding="utf-8")

    meta = _parse_frontmatter(existing)
    meta.update({"name": name, "description": description, "tags": tags})
    body = "\n".join(existing.split("---", 2)[2:]).strip() if existing.startswith("---") else existing.strip()

    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    content = f"---\n{frontmatter}---\n\n{body}\n".strip() + "\n"
    skill_file.write_text(content, encoding="utf-8")

    return _build_skill_from_dir(path)


def rename_skill(path: Path, new_name: str) -> Path:
    """Rename a skill directory."""
    new_path = path.parent / new_name
    if new_path.exists():
        raise FileExistsError(f"A skill named '{new_name}' already exists.")
    shutil.move(str(path), str(new_path))
    return new_path


def delete_skill(path: Path) -> None:
    """Delete a skill directory."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def copy_skill(source: Path, destination: Path) -> None:
    """Copy a skill directory to a destination that does not exist yet."""
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, symlinks=True)


def plan_move_to_hub(
    source_dir: Path,
    hub_dir: Path,
    conflict_strategy: str = "rename",
) -> MovePlan:
    """Plan moving skills from a source directory into the central hub."""
    plan = MovePlan()
    if not source_dir.exists():
        plan.warnings.append(f"Source directory does not exist: {source_dir}")
        return plan

    hub_dir.mkdir(parents=True, exist_ok=True)
    existing_hub_names = {child.name for child in hub_dir.iterdir() if child.is_dir() or child.is_symlink()}

    for entry in sorted(source_dir.iterdir()):
        if not (entry.is_dir() or entry.is_symlink()):
            continue

        dest = hub_dir / entry.name
        if entry.name in existing_hub_names:
            if conflict_strategy == "skip":
                plan.operations.append(
                    MoveOperation(source=entry, destination=dest, action="skip")
                )
                continue
            if conflict_strategy == "discard":
                plan.operations.append(
                    MoveOperation(source=entry, destination=dest, action="discard")
                )
                continue
            if conflict_strategy == "merge":
                plan.operations.append(
                    MoveOperation(source=entry, destination=dest, action="merge")
                )
                continue
            # rename strategy
            base = entry.name
            counter = 1
            new_name = f"{base}_{counter}"
            while new_name in existing_hub_names:
                counter += 1
                new_name = f"{base}_{counter}"
            dest = hub_dir / new_name
            plan.operations.append(
                MoveOperation(source=entry, destination=dest, action="rename")
            )
        else:
            plan.operations.append(
                MoveOperation(source=entry, destination=dest, action="move")
            )

    return plan


def execute_move_plan(plan: MovePlan) -> list[Path]:
    """Execute a move plan and return the final destination paths."""
    moved: list[Path] = []
    for op in plan.operations:
        if op.action == "skip":
            continue
        if op.action == "discard":
            if op.source.is_dir() and not op.source.is_symlink():
                shutil.rmtree(op.source)
            else:
                op.source.unlink(missing_ok=True)
            continue
        if op.action in ("move", "rename"):
            shutil.move(str(op.source), str(op.destination))
            moved.append(op.destination)
        elif op.action == "merge":
            if not op.destination.exists():
                shutil.move(str(op.source), str(op.destination))
                moved.append(op.destination)
            else:
                for child in op.source.iterdir():
                    dest_child = op.destination / child.name
                    if dest_child.exists():
                        continue
                    if child.is_dir():
                        shutil.move(str(child), str(dest_child))
                    else:
                        shutil.copy2(str(child), str(dest_child))
                if op.source.is_dir():
                    shutil.rmtree(op.source)
                moved.append(op.destination)
    return moved
