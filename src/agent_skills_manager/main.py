"""FastAPI application and CLI entrypoint."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request as UrlRequest, urlopen

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from agent_skills_manager.config import Settings, get_settings
from agent_skills_manager.models import (
    AgentTarget,
    ImportRequest,
    Project,
    RemoveSymlinkRequest,
    Skill,
    SkillLocationPresence,
    SkillPresence,
    SkillPresenceRequest,
    SkillUrlImportRequest,
    SymlinkRequest,
    UndoRequest,
)
from agent_skills_manager.services.projects import scan_project
from agent_skills_manager.services.skills import (
    clear_skill_origin,
    copy_skill,
    delete_skill,
    list_skills,
    read_skill,
    read_skill_content,
    read_skill_origin,
    rename_skill,
    write_skill_content,
    write_skill_metadata,
    write_skill_origin,
)
from agent_skills_manager.services.targets import (
    add_custom_target,
    create_symlink,
    find_target_by_id,
    get_default_targets,
    inspect_target,
    load_symlink_history,
    preview_symlink_target,
    remove_symlink,
    undo_symlink,
)


def _targets_file(settings: Settings) -> Path:
    return settings.config_dir / "targets.json"


def _load_custom_targets(settings: Settings) -> list[AgentTarget]:
    targets_file = _targets_file(settings)
    if not targets_file.exists():
        return []
    try:
        data = json.loads(targets_file.read_text(encoding="utf-8"))
        return [AgentTarget(**item) for item in data]
    except (json.JSONDecodeError, TypeError):
        return []


def _save_custom_targets(targets: list[AgentTarget], settings: Settings) -> None:
    targets_file = _targets_file(settings)
    settings.ensure_dirs()
    targets_file.write_text(
        json.dumps([target.model_dump(mode="json") for target in targets], indent=2),
        encoding="utf-8",
    )


def _skill_name_from_upload(filename: str, content: str) -> str:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            match = re.search(r"(?m)^name:\s*[\"']?([^\"'\n#]+)", parts[1])
            if match:
                return match.group(1).strip()

    stem = Path(filename).stem
    if stem.upper() == "SKILL":
        raise HTTPException(
            status_code=400,
            detail="Uploaded SKILL.md must include a frontmatter name.",
        )
    return stem


def _validate_skill_name(name: str) -> str:
    value = name.strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid skill name")
    return value


def _github_raw_skill_url(url: str) -> tuple[str, str]:
    cleaned = url.strip()
    if cleaned.startswith("github.com/") or cleaned.startswith("www.github.com/"):
        cleaned = f"https://{cleaned}"
    if cleaned.startswith("http://"):
        cleaned = "https://" + cleaned[len("http://") :]

    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="Paste a full HTTPS GitHub link to a Markdown file (SKILL.md).",
        )

    host = parsed.netloc.lower()
    if host == "raw.githubusercontent.com":
        filename = Path(parsed.path).name
        if not filename.lower().endswith(".md"):
            raise HTTPException(
                status_code=400,
                detail="That GitHub link must point to a Markdown file ending in .md.",
            )
        return cleaned.split("?", 1)[0], filename

    if host not in {"github.com", "www.github.com"}:
        raise HTTPException(
            status_code=400,
            detail="Only github.com links are supported. Open the skill file on GitHub and copy its address.",
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] not in {"blob", "raw"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "That doesn't look like a link to a specific file. "
                "Open SKILL.md on GitHub, then copy the browser address. "
                "It should look like https://github.com/owner/repo/blob/main/path/SKILL.md"
            ),
        )

    owner, repo, _, ref, *path_parts = parts
    if not path_parts:
        raise HTTPException(
            status_code=400,
            detail="That GitHub link is missing the path to the Markdown file.",
        )
    filename = path_parts[-1]
    if not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="That GitHub link must point to a Markdown file ending in .md.",
        )
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{'/'.join(path_parts)}"
    return raw_url, filename


def _fetch_skill_markdown(url: str) -> str:
    request = UrlRequest(url, headers={"Accept": "text/plain"})
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - URL is validated as GitHub-only.
            raw = response.read(512 * 1024 + 1)
    except (OSError, URLError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Couldn't download that skill from GitHub. Check the link and try again.",
        ) from exc

    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=400, detail="That skill file is too large to import (max 512 KB).")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="That skill file isn't valid UTF-8 text. Import a Markdown .md file instead.",
        ) from exc


def _default_targets_file(settings: Settings) -> Path:
    return settings.config_dir / "default-targets.json"


def _github_sources_file(settings: Settings) -> Path:
    return settings.config_dir / "github-sources.json"


def _load_github_sources(settings: Settings) -> dict[str, str]:
    sources_file = _github_sources_file(settings)
    if not sources_file.exists():
        return {}
    try:
        data = json.loads(sources_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                str(name): str(url)
                for name, url in data.items()
                if isinstance(name, str) and isinstance(url, str) and name and url
            }
    except (json.JSONDecodeError, TypeError, OSError):
        pass
    return {}


def _save_github_sources(settings: Settings, sources: dict[str, str]) -> None:
    sources_file = _github_sources_file(settings)
    settings.ensure_dirs()
    sources_file.write_text(json.dumps(sources, indent=2, sort_keys=True), encoding="utf-8")


def _set_skill_origin(settings: Settings, skill_name: str, origin: str, url: str = "") -> None:
    write_skill_origin(settings.skills_dir / skill_name, origin, url=url)
    sources = _load_github_sources(settings)
    if origin == "github" and url.strip():
        sources[skill_name] = url.strip()
        _save_github_sources(settings, sources)
        return
    if skill_name in sources:
        del sources[skill_name]
        _save_github_sources(settings, sources)


def _rename_skill_origin(settings: Settings, old_name: str, new_name: str) -> None:
    # Sidecar file moves with the skill directory on rename; keep the registry in sync.
    sources = _load_github_sources(settings)
    url = sources.pop(old_name, None)
    if url is None:
        url = read_skill_origin(settings.skills_dir / new_name).get("url", "")
    if url:
        sources[new_name] = url
    _save_github_sources(settings, sources)


def _clear_skill_origin(settings: Settings, skill_name: str) -> None:
    clear_skill_origin(settings.skills_dir / skill_name)
    sources = _load_github_sources(settings)
    if skill_name not in sources:
        return
    del sources[skill_name]
    _save_github_sources(settings, sources)


def _origin_for_skill(settings: Settings, skill_name: str) -> tuple[str, str]:
    origin_info = read_skill_origin(settings.skills_dir / skill_name)
    added_via = origin_info.get("origin", "")
    source_url = origin_info.get("url", "")
    if not source_url:
        source_url = _load_github_sources(settings).get(skill_name, "")
    if source_url and not added_via:
        added_via = "github"
    return added_via, source_url


def _github_source_for_skill(settings: Settings, skill_name: str) -> str:
    return _origin_for_skill(settings, skill_name)[1]


def _removed_default_targets_file(settings: Settings) -> Path:
    return settings.config_dir / "removed-default-targets.json"


def _load_removed_default_targets(settings: Settings) -> set[str]:
    removed_file = _removed_default_targets_file(settings)
    if not removed_file.exists():
        return set()
    try:
        data = json.loads(removed_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data)
    except (json.JSONDecodeError, TypeError):
        pass
    return set()


def _save_removed_default_targets(settings: Settings, removed_ids: set[str]) -> None:
    removed_file = _removed_default_targets_file(settings)
    settings.ensure_dirs()
    removed_file.write_text(
        json.dumps(sorted(removed_ids), indent=2),
        encoding="utf-8",
    )


def _get_available_default_targets(settings: Settings) -> list[AgentTarget]:
    removed_ids = _load_removed_default_targets(settings)
    return [target for target in get_default_targets() if target.id not in removed_ids]


def _load_enabled_default_targets(settings: Settings) -> set[str]:
    defaults_file = _default_targets_file(settings)
    available_ids = {t.id for t in _get_available_default_targets(settings)}
    if not defaults_file.exists():
        return available_ids
    try:
        data = json.loads(defaults_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data) & available_ids
    except (json.JSONDecodeError, TypeError):
        pass
    return available_ids


def _save_enabled_default_targets(settings: Settings, enabled_ids: set[str]) -> None:
    defaults_file = _default_targets_file(settings)
    settings.ensure_dirs()
    defaults_file.write_text(
        json.dumps(sorted(enabled_ids), indent=2),
        encoding="utf-8",
    )


def _get_all_targets(settings: Settings) -> list[AgentTarget]:
    defaults = _get_available_default_targets(settings)
    custom = _load_custom_targets(settings)
    enabled_defaults = _load_enabled_default_targets(settings)
    default_ids = {t.id for t in defaults}
    merged = [t for t in defaults if t.id in enabled_defaults] + [
        t for t in custom if t.id not in default_ids
    ]
    targets = [inspect_target(t, settings.skills_dir) for t in merged]
    for target in targets:
        target.can_undo = load_symlink_history(settings.config_dir, target.id) is not None
    return targets


def _skill_key(skill: Skill) -> str:
    return skill.path.name


def _skill_summary(skills_by_location: dict[str, Skill]) -> tuple[str, list[str]]:
    central = skills_by_location.get("central")
    source = central or next(iter(skills_by_location.values()))
    return source.description, source.tags


def _target_presence_read_only(target: AgentTarget) -> tuple[bool, str]:
    if target.state == "symlink_ok":
        return True, "Linked to central hub"
    if target.state == "directory":
        return False, ""
    if target.state == "missing":
        return True, "Location does not exist"
    if target.state == "symlink_broken":
        return True, "Broken symlink"
    if target.state == "file":
        return True, "Path is a file"
    return True, "Unavailable"


def _get_skill_presence(settings: Settings) -> list[SkillPresence]:
    hub_skills = list_skills(settings.skills_dir, source="Universal")
    targets = _get_all_targets(settings)
    skill_map: dict[str, dict[str, Skill]] = {}

    for skill in hub_skills:
        skill_map.setdefault(_skill_key(skill), {})["central"] = skill

    for target in targets:
        for skill in target.skills:
            skill_map.setdefault(_skill_key(skill), {})[target.id] = skill

    rows: list[SkillPresence] = []
    for skill_name in sorted(skill_map):
        description, tags = _skill_summary(skill_map[skill_name])
        locations = [
            SkillLocationPresence(
                location_id="central",
                name="Universal",
                path=settings.skills_dir / skill_name,
                present="central" in skill_map[skill_name],
            )
        ]

        for target in targets:
            read_only, reason = _target_presence_read_only(target)
            locations.append(
                SkillLocationPresence(
                    location_id=target.id,
                    name=target.name,
                    path=target.path / skill_name,
                    present=target.id in skill_map[skill_name],
                    read_only=read_only,
                    reason=reason,
                )
            )

        added_via = ""
        source_url = ""
        if "central" in skill_map[skill_name]:
            added_via, source_url = _origin_for_skill(settings, skill_name)

        rows.append(
            SkillPresence(
                name=skill_name,
                description=description,
                tags=tags,
                added_via=added_via,
                source_url=source_url,
                locations=locations,
            )
        )
    return rows


def _find_skill_source(settings: Settings, skill_name: str, excluded_location_id: str) -> Path | None:
    candidates: list[Path] = []
    if excluded_location_id != "central":
        candidates.append(settings.skills_dir / skill_name)
    for target in _get_all_targets(settings):
        if target.id == excluded_location_id or target.state == "symlink_ok":
            continue
        candidates.append(target.path / skill_name)
    for candidate in candidates:
        if candidate.exists() and (candidate.is_dir() or candidate.is_symlink()):
            return candidate
    return None


def _set_skill_presence(settings: Settings, request: SkillPresenceRequest) -> dict[str, str]:
    if "/" in request.skill_name or "\\" in request.skill_name or request.skill_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    if request.location_id == "central":
        destination = settings.skills_dir / request.skill_name
    else:
        target = find_target_by_id(_get_all_targets(settings), request.location_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Location not found")
        read_only, reason = _target_presence_read_only(target)
        if read_only:
            raise HTTPException(status_code=400, detail=reason or "Location cannot be changed")
        destination = target.path / request.skill_name

    if not request.present:
        delete_skill(destination)
        return {"status": "ok", "message": "Skill removed from location"}

    if destination.exists():
        return {"status": "ok", "message": "Skill already exists at location"}

    source = _find_skill_source(settings, request.skill_name, request.location_id)
    if source is None:
        raise HTTPException(status_code=404, detail="No source copy found for this skill")

    copy_skill(source, destination)
    return {"status": "ok", "message": "Skill copied to location"}


GITHUB_RELEASE_URL = "https://api.github.com/repos/bluefate/skill-manager/releases/latest"
UPDATE_CACHE_SECONDS = 3600


def _version_key(value: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _fetch_latest_release() -> dict[str, str] | None:
    request = UrlRequest(GITHUB_RELEASE_URL, headers={"Accept": "application/vnd.github+json"})
    try:
        with urlopen(request, timeout=2) as response:  # noqa: S310 - fixed GitHub API URL
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError):
        return None
    tag_name = payload.get("tag_name")
    html_url = payload.get("html_url")
    if not isinstance(tag_name, str) or not isinstance(html_url, str):
        return None
    return {"version": tag_name, "url": html_url}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
    )

    static_dir = Path(__file__).parent / "web" / "static"
    templates_dir = Path(__file__).parent / "web" / "templates"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    templates = Jinja2Templates(directory=templates_dir)
    update_cache: dict[str, Any] = {"checked_at": 0.0, "release": None}

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    @app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
    async def apple_touch_icon() -> FileResponse:
        return FileResponse(static_dir / "apple-touch-icon.png", media_type="image/png")

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "app_title": settings.app_title,
                "app_version": settings.app_version,
            },
        )

    @app.get("/app", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        hub_path = settings.skills_dir.expanduser().resolve()
        default_hub_path = (Path.home() / ".agents" / "skills").resolve()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "app_title": settings.app_title,
                "app_version": settings.app_version,
                "hub_path": str(hub_path),
                "hub_is_custom": hub_path != default_hub_path,
            },
        )

    @app.get("/api/updates/latest")
    async def get_latest_update() -> dict[str, str | bool]:
        now = time.monotonic()
        if now - update_cache["checked_at"] >= UPDATE_CACHE_SECONDS:
            update_cache["release"] = await asyncio.to_thread(_fetch_latest_release)
            update_cache["checked_at"] = now

        release = update_cache["release"]
        if release is None:
            return {"available": False}

        current_key = _version_key(settings.app_version)
        latest_key = _version_key(release["version"])
        available = current_key is not None and latest_key is not None and latest_key > current_key
        return {"available": available, "version": release["version"], "url": release["url"]}

    @app.get("/api/skills", response_model=list[Skill])
    async def get_skills() -> list[Skill]:
        return list_skills(settings.skills_dir, source="central")

    @app.get("/api/skills/presence", response_model=list[SkillPresence])
    async def get_skills_presence() -> list[SkillPresence]:
        return _get_skill_presence(settings)

    @app.post("/api/skills/presence")
    async def set_skills_presence(request: SkillPresenceRequest) -> dict[str, str]:
        return _set_skill_presence(settings, request)

    @app.get("/api/skills/{skill_name}", response_model=Skill)
    async def get_skill(skill_name: str) -> Skill:
        skill_path = settings.skills_dir / skill_name
        skill = read_skill(skill_path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        return skill

    @app.get("/api/skills/{skill_name}/content")
    async def get_skill_content(skill_name: str) -> dict[str, str]:
        skill_path = settings.skills_dir / skill_name
        content = read_skill_content(skill_path)
        if content is None:
            raise HTTPException(status_code=404, detail="Skill text not found")
        return {"content": content}

    @app.post("/api/skills", response_model=Skill)
    async def create_or_update_skill(skill: Skill) -> Skill:
        skill_name = _validate_skill_name(skill.name)
        skill_path = settings.skills_dir / skill_name
        is_new = not skill_path.exists()
        result = write_skill_metadata(
            skill_path,
            name=skill_name,
            description=skill.description,
            tags=skill.tags,
        )
        if is_new:
            _set_skill_origin(settings, skill_name, "created")
        return result

    @app.post("/api/skills/upload", response_model=Skill)
    async def upload_skill(file: UploadFile = File(...)) -> Skill:
        filename = file.filename or ""
        if not filename.lower().endswith(".md"):
            raise HTTPException(status_code=400, detail="Upload a Markdown .md file")

        raw = await file.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Skill file must be UTF-8 text") from exc

        skill_name = _validate_skill_name(_skill_name_from_upload(filename, content))
        skill_path = settings.skills_dir / skill_name
        skill = write_skill_content(skill_path, content)
        _set_skill_origin(settings, skill_name, "upload")
        return skill

    @app.post("/api/skills/import-url", response_model=Skill)
    async def import_skill_url(request: SkillUrlImportRequest) -> Skill:
        raw_url, filename = _github_raw_skill_url(request.url)
        if not filename.lower().endswith(".md"):
            raise HTTPException(
                status_code=400,
                detail="That GitHub link must point to a Markdown file ending in .md.",
            )

        content = await asyncio.to_thread(_fetch_skill_markdown, raw_url)
        skill_name = _validate_skill_name(_skill_name_from_upload(filename, content))
        skill_path = settings.skills_dir / skill_name
        skill = write_skill_content(skill_path, content)
        _set_skill_origin(settings, skill_name, "github", url=request.url.strip())
        return skill

    @app.post("/api/skills/{skill_name}/refresh", response_model=Skill)
    async def refresh_skill_from_github(skill_name: str) -> Skill:
        skill_name = _validate_skill_name(skill_name)
        skill_path = settings.skills_dir / skill_name
        if not skill_path.exists():
            raise HTTPException(status_code=404, detail="Skill not found")

        source_url = _github_source_for_skill(settings, skill_name)
        if not source_url:
            raise HTTPException(
                status_code=400,
                detail="This skill doesn't have a saved GitHub link to refresh from. Import it from GitHub once to enable Refresh.",
            )

        raw_url, filename = _github_raw_skill_url(source_url)
        if not filename.lower().endswith(".md"):
            raise HTTPException(
                status_code=400,
                detail="That GitHub link must point to a Markdown file ending in .md.",
            )

        content = await asyncio.to_thread(_fetch_skill_markdown, raw_url)
        refreshed_name = _validate_skill_name(_skill_name_from_upload(filename, content))
        if refreshed_name != skill_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"GitHub skill name is now '{refreshed_name}', which differs from '{skill_name}'. "
                    "Import it as a new skill instead."
                ),
            )

        skill = write_skill_content(skill_path, content)
        _set_skill_origin(settings, skill_name, "github", url=source_url)
        return skill

    @app.post("/api/skills/{skill_name}/rename", response_model=Skill)
    async def rename_existing_skill(skill_name: str, new_name: str) -> Skill:
        old_path = settings.skills_dir / skill_name
        if not old_path.exists():
            raise HTTPException(status_code=404, detail="Skill not found")
        new_path = rename_skill(old_path, new_name)
        _rename_skill_origin(settings, skill_name, new_name)
        return read_skill(new_path) or Skill(name=new_name, path=new_path, source="central")

    @app.delete("/api/skills/{skill_name}")
    async def delete_existing_skill(skill_name: str) -> dict[str, str]:
        skill_path = settings.skills_dir / skill_name
        if not skill_path.exists():
            raise HTTPException(status_code=404, detail="Skill not found")
        delete_skill(skill_path)
        _clear_skill_origin(settings, skill_name)
        return {"status": "ok", "message": f"Skill '{skill_name}' deleted"}

    @app.get("/api/targets", response_model=list[AgentTarget])
    async def get_targets() -> list[AgentTarget]:
        return _get_all_targets(settings)

    @app.get("/api/targets/defaults", response_model=list[AgentTarget])
    async def get_default_targets_list() -> list[AgentTarget]:
        enabled = _load_enabled_default_targets(settings)
        targets = _get_available_default_targets(settings)
        for target in targets:
            target.can_undo = load_symlink_history(settings.config_dir, target.id) is not None
        return targets

    @app.post("/api/targets/defaults")
    async def set_default_targets(enabled_ids: list[str]) -> dict[str, str]:
        valid_ids = {t.id for t in _get_available_default_targets(settings)}
        if not set(enabled_ids).issubset(valid_ids):
            raise HTTPException(status_code=400, detail="Invalid default target ID")
        _save_enabled_default_targets(settings, set(enabled_ids))
        return {"status": "ok", "message": "Default targets updated"}

    @app.post("/api/targets", response_model=AgentTarget)
    async def add_target(target: AgentTarget) -> AgentTarget:
        custom = _load_custom_targets(settings)
        existing = find_target_by_id(custom, target.id) or find_target_by_id(
            _get_available_default_targets(settings), target.id
        )
        if existing:
            raise HTTPException(status_code=409, detail="Target already exists")
        new_target = add_custom_target(target.path, target.name)
        custom.append(new_target)
        _save_custom_targets(custom, settings)
        return inspect_target(new_target, settings.skills_dir)

    @app.delete("/api/targets")
    async def delete_target(target_id: str = Query(..., description="Target ID")) -> dict[str, str]:
        custom = _load_custom_targets(settings)
        filtered = [t for t in custom if t.id != target_id]
        if len(filtered) != len(custom):
            _save_custom_targets(filtered, settings)
            return {"status": "ok", "message": "Target removed"}

        default_ids = {t.id for t in _get_available_default_targets(settings)}
        if target_id in default_ids:
            removed_ids = _load_removed_default_targets(settings)
            removed_ids.add(target_id)
            _save_removed_default_targets(settings, removed_ids)
            enabled_ids = _load_enabled_default_targets(settings)
            enabled_ids.discard(target_id)
            _save_enabled_default_targets(settings, enabled_ids)
            return {"status": "ok", "message": "Known agent location removed"}

        raise HTTPException(status_code=404, detail="Target not found")

    @app.get("/api/targets/preview")
    async def preview_target(
        target_id: str = Query(..., description="Target ID"),
        move_existing: bool = True,
        conflict_strategy: str = "rename",
    ) -> dict:
        targets = _get_all_targets(settings)
        target = find_target_by_id(targets, target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target not found")
        preview = preview_symlink_target(
            target,
            settings.skills_dir,
            move_existing=move_existing,
            conflict_strategy=conflict_strategy,
        )
        return preview.model_dump(mode="json")

    @app.post("/api/targets/symlink")
    async def symlink_target(request: SymlinkRequest) -> dict[str, str]:
        targets = _get_all_targets(settings)
        target = find_target_by_id(targets, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target not found")
        return create_symlink(
            target,
            settings.skills_dir,
            move_existing=request.move_existing,
            conflict_strategy=request.conflict_strategy,
            history_dir=settings.config_dir,
        )

    @app.post("/api/targets/remove-symlink")
    async def unlink_target(request: RemoveSymlinkRequest) -> dict[str, str]:
        targets = _get_all_targets(settings)
        target = find_target_by_id(targets, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target not found")
        return remove_symlink(target, restore=request.restore)

    @app.post("/api/targets/undo-symlink")
    async def undo_symlink_target(request: UndoRequest) -> dict[str, str]:
        targets = _get_all_targets(settings)
        target = find_target_by_id(targets, request.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target not found")
        return undo_symlink(target, settings.config_dir)

    @app.get("/api/projects/scan", response_model=Project)
    async def scan_project_path(path: str = Query(..., description="Project path to scan")) -> Project:
        project_path = Path(path).expanduser()
        return scan_project(project_path)

    @app.post("/api/projects/import")
    async def import_skills(request: ImportRequest) -> dict[str, str]:
        from agent_skills_manager.services.skills import execute_move_plan, plan_move_to_hub

        source_dir = Path(request.source_path).expanduser()
        if not source_dir.exists():
            raise HTTPException(status_code=404, detail="Source path not found")

        imported = 0
        skipped = 0
        for skill_name in request.skill_names:
            skill_source = source_dir / skill_name
            if not skill_source.exists():
                skipped += 1
                continue
            temp_dir = source_dir.parent / f"_{source_dir.name}_import"
            temp_dir.mkdir(parents=True, exist_ok=True)
            move_dir = temp_dir / skill_name
            if move_dir.exists():
                move_dir = temp_dir / f"{skill_name}_tmp"
            shutil.move(str(skill_source), str(move_dir))
            plan = plan_move_to_hub(move_dir, settings.skills_dir, conflict_strategy=request.conflict_strategy)
            execute_move_plan(plan)
            imported += 1
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()

        return {"status": "ok", "message": f"Imported {imported} skill(s), skipped {skipped}."}

    return app


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Agent Skills Manager")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the web server")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    run_parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    run_parser.add_argument(
        "--skills-dir",
        default=None,
        help="Central skills directory (default: ~/.agents/skills)",
    )

    args = parser.parse_args()

    if args.command == "run":
        settings_kwargs: dict[str, object] = {"host": args.host, "port": args.port}
        if args.skills_dir:
            settings_kwargs["skills_dir"] = Path(args.skills_dir).expanduser()
        settings = Settings(**settings_kwargs)
        app = create_app(settings)
        uvicorn.run(app, host=settings.host, port=settings.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
