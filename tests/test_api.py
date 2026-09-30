"""Tests for the FastAPI application."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent_skills_manager.main as app_main
from agent_skills_manager.config import Settings
from agent_skills_manager.main import create_app


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


def test_import_skill_from_github_link(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_import_skill_from_github_rejects_non_github_url(client: TestClient) -> None:
    response = client.post(
        "/api/skills/import-url",
        json={"url": "https://example.com/SKILL.md"},
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
