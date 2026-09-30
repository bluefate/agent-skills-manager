"""Pydantic models for the API and UI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A single skill stored in the central hub or a target/project."""

    name: str
    path: Path
    source: str = ""  # e.g. "Cursor", "Claude", project path, or "central"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    exists: bool = True
    is_symlink: bool = False


class SkillDir(BaseModel):
    """A skill directory found inside a project."""

    agent_name: str
    relative_path: Path
    absolute_path: Path
    skills: list[Skill] = Field(default_factory=list)


class Project(BaseModel):
    """A project directory containing possible skill directories."""

    path: Path
    skill_dirs: list[SkillDir] = Field(default_factory=list)


class MoveOperation(BaseModel):
    """A single move operation."""

    source: Path
    destination: Path
    action: Literal["move", "rename", "skip", "merge", "discard"]


class MovePlan(BaseModel):
    """Plan for moving existing skills into the central hub."""

    operations: list[MoveOperation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentTarget(BaseModel):
    """A directory that should be symlinked to the central skills hub."""

    id: str
    name: str
    path: Path
    is_default: bool = False
    state: Literal["missing", "directory", "symlink_ok", "symlink_broken", "file"] = "missing"
    resolved_path: Path | None = None
    skills: list[Skill] = Field(default_factory=list)
    can_undo: bool = False


class SkillLocationPresence(BaseModel):
    """Whether a skill folder exists at one managed location."""

    location_id: str
    name: str
    path: Path
    present: bool
    read_only: bool = False
    reason: str = ""


class SkillPresence(BaseModel):
    """A skill folder and its presence across the hub and agent locations."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    source_url: str = ""
    locations: list[SkillLocationPresence] = Field(default_factory=list)


class PreviewResult(BaseModel):
    """Result of previewing a target before symlinking."""

    target: AgentTarget
    existing_skills: list[Skill]
    conflicts: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    can_symlink: bool = True
    message: str = ""


class SymlinkRequest(BaseModel):
    """Request to create a symlink for a target."""

    target_id: str
    move_existing: bool = True
    conflict_strategy: Literal["rename", "skip", "merge", "discard"] = "rename"


class SkillPresenceRequest(BaseModel):
    """Request to add or remove a skill folder at one location."""

    skill_name: str
    location_id: str
    present: bool


class RemoveSymlinkRequest(BaseModel):
    """Request to remove a symlink and optionally restore the original directory."""

    target_id: str
    restore: bool = False


class ImportRequest(BaseModel):
    """Request to import skills from a project or target into the hub."""

    source_path: Path
    skill_names: list[str]
    conflict_strategy: Literal["rename", "skip", "overwrite"] = "rename"


class SkillUrlImportRequest(BaseModel):
    """Request to import a Markdown skill from a URL."""

    url: str


class SymlinkHistory(BaseModel):
    """Record of skills moved during a symlink operation so it can be undone."""

    timestamp: str
    target_id: str
    target_path: Path
    hub_path: Path
    operations: list[MoveOperation]


class UndoRequest(BaseModel):
    """Request to undo a symlink operation."""

    target_id: str
