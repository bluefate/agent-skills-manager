# Agent Skills Manager

A small, open-source web application that helps you maintain **one canonical directory** for your AI agent skills and keep every editor/project in sync using symlinks.

## Why?

Different agents and editors expect skills in different places:

- `~/.agents/skills/` (the global, canonical hub used by this app)
- `~/.cursor/skills/`
- `~/.claude/skills/`
- `~/.codex/skills/`
- `~/.config/opencode/skills/`

This tool keeps all your skills in `~/.agents/skills/` and lets you safely preview, move, and symlink those other locations so every editor reads from the same source.

Devin currently discovers skills from repositories rather than a global user directory. Its recommended path is `<repository>/.agents/skills/<skill-name>/SKILL.md`; global and organization-level skills are not currently supported. See the [Devin Skills documentation](https://docs.devin.ai/product-guides/skills) for its complete list of supported repository paths.

## Features

- **Central Skills Hub:** Manage everything from `~/.agents/skills/`.
- **Agent Location Management:** Built-in locations for Cursor, Claude, Codex, and OpenCode; add custom locations dynamically.
- **Safe Symlink Workflow:** Preview agent skill locations, move existing skills into the hub, then create or remove symlinks with clear conflict handling. Undo a symlink later to restore the original directory.
- **Project Skill Reviewer:** Scan any project for `.agents/skills/`, `.cursor/skills/`, `.claude/skills/`, `.codex/skills/`, and `.opencode/skills/`; review and import skills into the central hub.
- **Web Admin UI:** Fully self-contained dashboard; no manual CLI steps needed after launching the server.

## Future Work

### Temporarily disable skills

Add controls to disable skills without deleting them. A global disable would move a skill from the central hub into a manager-owned disabled area so every agent stops seeing it after restart. A per-agent-location disable would replace that location's full-hub symlink with an override directory containing links only to enabled skills. The interface should make overrides clear and provide a one-click return to the full central hub.

## Quick Start

### Install

```bash
pip install agent-skills-manager
```

Or from source:

```bash
git clone https://github.com/bluefate/skill-manager.git
cd skill-manager
pip install -e ".[dev]"
```

### Run

```bash
agent-skills-manager run
```

Open <http://127.0.0.1:8000> for the home page, then click **Open Dashboard** or go directly to <http://127.0.0.1:8000/app> to manage skills and agent locations.

### Update or Refresh the App

If the app is already running, stop the server with `Ctrl+C`, start it again, and hard-refresh the dashboard in your browser (`Cmd+Shift+R` on macOS or `Ctrl+Shift+R` on Windows and Linux).

Example update flow when you launched the app from a source checkout:

```bash
# In the terminal running the app:
# press Ctrl+C

cd /path/to/skill-manager
git pull
.venv/bin/pip install -e ".[dev]"
.venv/bin/agent-skills-manager run
```

For an editable installation from this repository, update the checkout and refresh the installation before restarting the server:

```bash
cd /path/to/skill-manager
git switch main
git pull
.venv/bin/pip install -e ".[dev]"
.venv/bin/agent-skills-manager run
```

When you are testing changes from another branch, switch to that branch instead of `main`. Editable installs usually pick up source and UI changes immediately, but restarting the server ensures the running process reloads them.

For an installation from PyPI, upgrade the package and restart the app:

```bash
pip install --upgrade agent-skills-manager
agent-skills-manager run
```

### Port 8000 Is Already in Use

This applies whether you installed from source or PyPI. Another copy of the app is usually still running. Reuse the app already available at <http://127.0.0.1:8000>, or stop the earlier server with `Ctrl+C` in the terminal where it was started before running the command again.

To run a second copy instead, choose a different port and open that address in your browser:

```bash
agent-skills-manager run --port 8001
```

### Custom Options

```bash
agent-skills-manager run --host 127.0.0.1 --port 8080 --skills-dir ~/.agents/skills
```

## Project Layout

```
skill-manager/
├── src/
│   └── agent_skills_manager/
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── services/
│       │   ├── skills.py
│       │   ├── targets.py
│       │   └── projects.py
│       └── web/
│           ├── static/
│           └── templates/
├── tests/
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## Windows Note

Creating symlinks on Windows typically requires **Developer Mode** or an elevated terminal. The application will warn you if symlinks cannot be created.

## License

Copyright &copy; 2026 BlueFate Labs. Agent Skills Manager is released under the **MIT License**, a permissive, free/open-source license. See [LICENSE](LICENSE) for the full text.

The bundled Markdown preview uses [Marked](src/agent_skills_manager/web/static/MARKED-LICENSE.txt), licensed under MIT, and [DOMPurify](src/agent_skills_manager/web/static/DOMPURIFY-LICENSE.txt), licensed under Apache-2.0 or MPL-2.0.

## Logo / Assets

A simple vector placeholder logo and favicon are provided at `src/agent_skills_manager/web/static/logo.svg`. Replace it with your own SVG or PNG if you want a custom logo.

If you generate or add external assets later, make sure you have the right to use and distribute them under the project license.

### Preparing assets from source images

1. Save the generated source images to the project root or `assets/`:
   - `assets/logo-dark.png`
   - `assets/logo-light.png`
   - `assets/banner-dark.png`
   - `assets/banner-light.png`
2. Install the asset tools:
   ```bash
   pip install -e ".[assets]"
   ```
3. Run the preparation script:
   ```bash
   python scripts/prepare_assets.py assets/logo-dark.png assets/logo-light.png \
       assets/banner-dark.png assets/banner-light.png
   ```
   The script crops the logo to a centered square, outputs 32x32 and 192x192 sizes, and resizes banners to a web-friendly width (1200px max).

If the logo source includes extra text or padding, crop it first with the environment variables, e.g.:

```bash
ASM_LOGO_CROP_LEFT=0.1 ASM_LOGO_CROP_TOP=0.05 ASM_LOGO_CROP_RIGHT=0.9 ASM_LOGO_CROP_BOTTOM=0.55 \
    python scripts/prepare_assets.py assets/logo-dark.png assets/logo-light.png \
        assets/banner-dark.png assets/banner-light.png
```

### AI-generated asset attribution

If the logo or banner was generated by an AI image tool (e.g. ChatGPT / DALL-E), include a short attribution note and, if required by the tool's terms, retain any copyright or usage notice it mandates. The web footer already displays:

> Logo and banner generated with ChatGPT / DALL-E.

Because AI-generated artwork does not have clear universal copyright ownership, we do **not** claim exclusive copyright over these assets; they are provided as project assets under the same permissive terms as the rest of the repository unless otherwise noted.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
