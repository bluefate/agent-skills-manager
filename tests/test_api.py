"""Tests for the FastAPI application."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent_skills_manager.main as app_main
from agent_skills_manager.config import Settings
from agent_skills_manager.main import create_app
from agent_skills_manager.services.skills import write_skill_metadata


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(skills_dir=tmp_path / "hub", config_dir=tmp_path / "config")
    app = create_app(settings)
    return TestClient(app)


def test_home(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Agent Skills Manager" in response.text
    assert "One place for all your agent skills" in response.text


def test_dashboard(client: TestClient) -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert "Agent Skills Manager" in response.text
    assert "Skill Library" in response.text
    assert "Central hub location" in response.text
    assert "custom path" in response.text
    assert "/hub" in response.text


@pytest.mark.parametrize("path", ["/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"])
def test_apple_touch_icon(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_skills_crud(client: TestClient) -> None:
    response = client.post("/api/skills", json={
        "name": "test-skill",
        "description": "A test skill",
        "tags": ["test"],
        "path": "/",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "test-skill"

    response = client.get("/api/skills")
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"

    response = client.get("/api/skills/test-skill")
    assert response.status_code == 200
    assert response.json()["description"] == "A test skill"

    response = client.get("/api/skills/test-skill/content")
    assert response.status_code == 200
    assert "name: test-skill" in response.json()["content"]

    response = client.delete("/api/skills/test-skill")
    assert response.status_code == 200

    response = client.get("/api/skills")
    assert response.json() == []


def test_upload_skill_markdown(client: TestClient) -> None:
    content = b"""---
name: uploaded-skill
description: Imported from Markdown
tags:
  - upload
---

# Uploaded Skill

Use this to test imports.
"""
    response = client.post(
        "/api/skills/upload",
        files={"file": ("SKILL.md", content, "text/markdown")},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "uploaded-skill"
    assert response.json()["description"] == "Imported from Markdown"

    response = client.get("/api/skills/uploaded-skill/content")
    assert response.status_code == 200
    assert "# Uploaded Skill" in response.json()["content"]


def test_upload_skill_markdown_uses_filename_without_frontmatter_name(client: TestClient) -> None:
    response = client.post(
        "/api/skills/upload",
        files={"file": ("filename-skill.md", b"# Filename Skill\n", "text/markdown")},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "filename-skill"


def test_import_skill_from_github_link(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return b"""---
name: github-skill
description: Imported from GitHub
---

# GitHub Skill
"""

    requested_urls: list[str] = []

    def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
        requested_urls.append(request.full_url)  # type: ignore[attr-defined]
        return FakeResponse()

    monkeypatch.setattr(app_main, "urlopen", fake_urlopen)

    response = client.post(
        "/api/skills/import-url",
        json={"url": "https://github.com/example/repo/blob/main/skills/github-skill/SKILL.md"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "github-skill"
    assert response.json()["description"] == "Imported from GitHub"
    assert requested_urls == [
        "https://raw.githubusercontent.com/example/repo/main/skills/github-skill/SKILL.md"
    ]

    presence = client.get("/api/skills/presence")
    assert presence.status_code == 200
    skill = next(item for item in presence.json() if item["name"] == "github-skill")
    assert skill["source_url"] == "https://github.com/example/repo/blob/main/skills/github-skill/SKILL.md"
    assert skill["added_via"] == "github"
    source_file = tmp_path / "hub" / "github-skill" / ".asm-source.json"
    assert source_file.exists()
    assert "github.com/example/repo" in source_file.read_text(encoding="utf-8")
    assert '"origin": "github"' in source_file.read_text(encoding="utf-8")


def test_refresh_skill_from_github(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return b"""---
name: github-skill
description: Updated from GitHub
---

# Updated GitHub Skill
"""

    requested_urls: list[str] = []

    def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
        requested_urls.append(request.full_url)  # type: ignore[attr-defined]
        return FakeResponse()

    monkeypatch.setattr(app_main, "urlopen", fake_urlopen)

    import_response = client.post(
        "/api/skills/import-url",
        json={"url": "https://github.com/example/repo/blob/main/skills/github-skill/SKILL.md"},
    )
    assert import_response.status_code == 200

    refresh_response = client.post("/api/skills/github-skill/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["description"] == "Updated from GitHub"
    assert requested_urls == [
        "https://raw.githubusercontent.com/example/repo/main/skills/github-skill/SKILL.md",
        "https://raw.githubusercontent.com/example/repo/main/skills/github-skill/SKILL.md",
    ]

    content = client.get("/api/skills/github-skill/content")
    assert content.status_code == 200
    assert "# Updated GitHub Skill" in content.json()["content"]


def test_refresh_skill_without_github_source(client: TestClient, tmp_path: Path) -> None:
    write_skill_metadata(tmp_path / "hub" / "local-skill", "local-skill", "Local only", [])
    response = client.post("/api/skills/local-skill/refresh")
    assert response.status_code == 400
    assert "no saved GitHub source" in response.json()["detail"]


def test_import_skill_from_github_rejects_non_github_url(client: TestClient) -> None:
    response = client.post(
        "/api/skills/import-url",
        json={"url": "https://example.com/SKILL.md"},
    )
    assert response.status_code == 400


def test_skill_presence_includes_hub_and_agent_only_skills(tmp_path: Path) -> None:
    settings = Settings(skills_dir=tmp_path / "hub", config_dir=tmp_path / "config")
    client = TestClient(create_app(settings))
    target_path = tmp_path / "cursor-skills"

    client.post("/api/targets/defaults", json=[])
    target_path.mkdir(parents=True)
    target = client.post(
        "/api/targets",
        json={"name": "Cursor Test", "path": str(target_path), "id": str(target_path), "state": "missing"},
    ).json()
    client.post(
        "/api/skills",
        json={"name": "hub-skill", "description": "From hub", "tags": [], "path": "/"},
    )
    write_skill_metadata(target_path / "target-only", "target-only", "Only in target", [])

    response = client.get("/api/skills/presence")
    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()}

    assert set(rows) == {"hub-skill", "target-only"}
    hub_skill_locations = {location["location_id"]: location for location in rows["hub-skill"]["locations"]}
    target_only_locations = {location["location_id"]: location for location in rows["target-only"]["locations"]}
    assert hub_skill_locations["central"]["present"] is True
    assert hub_skill_locations[target["id"]]["present"] is False
    assert target_only_locations["central"]["present"] is False
    assert target_only_locations[target["id"]]["present"] is True


def test_skill_presence_toggle_copies_and_removes_skills(tmp_path: Path) -> None:
    settings = Settings(skills_dir=tmp_path / "hub", config_dir=tmp_path / "config")
    client = TestClient(create_app(settings))
    target_path = tmp_path / "cursor-skills"

    client.post("/api/targets/defaults", json=[])
    target_path.mkdir(parents=True)
    target = client.post(
        "/api/targets",
        json={"name": "Cursor Test", "path": str(target_path), "id": str(target_path), "state": "missing"},
    ).json()
    client.post(
        "/api/skills",
        json={"name": "copy-me", "description": "Copy me", "tags": [], "path": "/"},
    )

    response = client.post(
        "/api/skills/presence",
        json={"skill_name": "copy-me", "location_id": target["id"], "present": True},
    )
    assert response.status_code == 200
    assert (target_path / "copy-me" / "SKILL.md").exists()

    response = client.post(
        "/api/skills/presence",
        json={"skill_name": "copy-me", "location_id": target["id"], "present": False},
    )
    assert response.status_code == 200
    assert not (target_path / "copy-me").exists()


def test_skill_presence_symlink_locations_are_read_only(tmp_path: Path) -> None:
    settings = Settings(skills_dir=tmp_path / "hub", config_dir=tmp_path / "config")
    client = TestClient(create_app(settings))
    target_path = tmp_path / "codex-skills"

    client.post("/api/targets/defaults", json=[])
    client.post(
        "/api/skills",
        json={"name": "linked-skill", "description": "Linked", "tags": [], "path": "/"},
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.symlink_to(settings.skills_dir, target_is_directory=True)
    target = client.post(
        "/api/targets",
        json={"name": "Codex Test", "path": str(target_path), "id": str(target_path), "state": "missing"},
    ).json()

    response = client.get("/api/skills/presence")
    assert response.status_code == 200
    row = next(item for item in response.json() if item["name"] == "linked-skill")
    location = next(item for item in row["locations"] if item["location_id"] == target["id"])
    assert location["present"] is True
    assert location["read_only"] is True

    response = client.post(
        "/api/skills/presence",
        json={"skill_name": "linked-skill", "location_id": target["id"], "present": False},
    )
    assert response.status_code == 400


def test_targets_list(client: TestClient) -> None:
    response = client.get("/api/targets")
    assert response.status_code == 200
    targets = response.json()
    assert len(targets) >= 4
    assert any(t["name"] == "Cursor" for t in targets)


def test_default_targets(client: TestClient) -> None:
    response = client.get("/api/targets/defaults")
    assert response.status_code == 200
    targets = response.json()
    assert len(targets) >= 4
    ids = [t["id"] for t in targets]
    assert len(set(ids)) == len(ids)

    response = client.post("/api/targets/defaults", json=ids[:2])
    assert response.status_code == 200

    response = client.get("/api/targets")
    assert response.status_code == 200
    active = response.json()
    assert len(active) == 2


def test_remove_default_target_from_known_locations(client: TestClient) -> None:
    targets = client.get("/api/targets/defaults").json()
    removed = targets[0]

    response = client.delete("/api/targets", params={"target_id": removed["id"]})
    assert response.status_code == 200
    assert response.json()["message"] == "Known agent location removed"

    response = client.get("/api/targets/defaults")
    assert response.status_code == 200
    known_ids = [target["id"] for target in response.json()]
    assert removed["id"] not in known_ids

    response = client.get("/api/targets")
    assert response.status_code == 200
    managed_ids = [target["id"] for target in response.json()]
    assert removed["id"] not in managed_ids

    response = client.post("/api/targets/defaults", json=[removed["id"]])
    assert response.status_code == 400


def test_target_preview(client: TestClient) -> None:
    targets = client.get("/api/targets").json()
    target = next(t for t in targets if t["name"] == "Codex")
    response = client.get(
        "/api/targets/preview",
        params={"target_id": target["id"], "move_existing": True, "conflict_strategy": "rename"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "target" in data
    assert "can_symlink" in data
