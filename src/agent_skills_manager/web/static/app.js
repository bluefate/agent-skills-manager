const API = {
    async get(path) {
        const res = await fetch(path);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
    async post(path, body) {
        const res = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
    async delete(path) {
        const res = await fetch(path, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
    async upload(path, formData) {
        const res = await fetch(path, {
            method: 'POST',
            body: formData,
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    }
};

const qs = (sel, el = document) => el.querySelector(sel);
const qsa = (sel, el = document) => [...el.querySelectorAll(sel)];

const modal = qs('#modal');
const modalTitle = qs('#modal-title');
const modalBody = qs('#modal-body');
const modalActions = qs('#modal-actions');
const toast = qs('#toast');

let state = {
    skills: [],
    skillPresence: [],
    targets: [],
    defaultTargets: [],
    enabledDefaults: [],
    project: null,
};

// Theme toggle
function applyTheme(light) {
    document.body.classList.toggle('light-mode', light);
    document.documentElement.classList.toggle('light-active', light);
    const label = qs('#theme-label');
    if (label) label.textContent = light ? 'Dark' : 'Light';
    localStorage.setItem('asm-theme', light ? 'light' : 'dark');
}

function isLightTheme() {
    return document.body.classList.contains('light-mode') ||
        document.documentElement.classList.contains('light-active');
}

qs('#theme-toggle').addEventListener('click', () => {
    applyTheme(!isLightTheme());
});

// Restore saved theme on load
applyTheme(localStorage.getItem('asm-theme') === 'light');

async function checkForUpdate() {
    const version = qs('.version');
    if (!version) return;
    try {
        const update = await API.get('/api/updates/latest');
        if (!update.available) return;
        const link = document.createElement('a');
        link.href = update.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.className = 'update-link';
        link.textContent = `Update available: ${update.version}`;
        version.append(' ');
        version.appendChild(link);
    } catch (_) {
        // The app remains fully local when GitHub is unavailable.
    }
}

checkForUpdate();

function showToast(message, type = 'success') {
    toast.textContent = message;
    toast.className = `toast ${type}`;
    setTimeout(() => toast.classList.add('hidden'), 4000);
}

function openModal(title, body, actions = []) {
    modalTitle.textContent = title;
    modalBody.innerHTML = '';
    if (typeof body === 'string') {
        modalBody.innerHTML = body;
    } else {
        modalBody.appendChild(body);
    }
    modalActions.innerHTML = '';
    actions.forEach(btn => modalActions.appendChild(btn));
    modal.classList.remove('hidden');
}

function closeModal() {
    modal.classList.add('hidden');
}

qs('#modal-close').addEventListener('click', closeModal);
modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
});

function makeButton(label, cls, onClick) {
    const btn = document.createElement('button');
    btn.className = `btn ${cls}`;
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
}

// Tabs
qsa('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        qsa('.tab').forEach(t => t.classList.remove('active'));
        qsa('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        qs(`#${tab.dataset.tab}`).classList.add('active');
    });
});

// Skills
async function loadSkills() {
    const [skills, skillPresence] = await Promise.all([
        API.get('/api/skills'),
        API.get('/api/skills/presence'),
    ]);
    state.skills = skills;
    state.skillPresence = skillPresence;
    renderSkills();
}

function renderSkills() {
    const filter = qs('#skill-filter').value.toLowerCase();
    const list = qs('#skills-list');
    const rows = state.skillPresence.filter(s =>
        s.name.toLowerCase().includes(filter) ||
        (s.description || '').toLowerCase().includes(filter) ||
        s.tags.some(t => t.toLowerCase().includes(filter))
    );

    if (!rows.length) {
        list.innerHTML = '<div class="empty">No skills found.</div>';
        return;
    }

    const locations = rows[0].locations;
    list.innerHTML = `
        <div class="table-wrap">
            <table class="skills-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Description</th>
                        ${locations.map(location => `<th class="presence-col">${escapeHtml(location.name)}</th>`).join('')}
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows.map(skill => {
                        const central = skill.locations.find(location => location.location_id === 'central');
                        const hasCentral = central?.present;
                        return `
                            <tr data-skill="${escapeHtml(skill.name)}">
                                <td>
                                    <strong>${escapeHtml(skill.name)}</strong>
                                    ${skill.tags.length ? `<div class="card-tags">${skill.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                                </td>
                                <td>${skill.description ? escapeHtml(skill.description) : '<span class="muted">No description</span>'}</td>
                                ${skill.locations.map(location => `
                                    <td class="presence-col">
                                        <input
                                            type="checkbox"
                                            data-skill-presence="${escapeHtml(skill.name)}"
                                            data-location-id="${escapeHtml(location.location_id)}"
                                            ${location.present ? 'checked' : ''}
                                            ${location.read_only ? 'disabled' : ''}
                                            title="${escapeHtml(location.reason || (location.present ? 'Skill is present' : 'Skill is not present'))}"
                                        >
                                    </td>
                                `).join('')}
                                <td>
                                    <div class="actions table-actions">
                                        <button class="btn small" data-edit="${escapeHtml(skill.name)}" ${hasCentral ? '' : 'disabled'}>Edit</button>
                                        <button class="btn small" data-preview-skill="${escapeHtml(skill.name)}" ${hasCentral ? '' : 'disabled'}>Preview</button>
                                        <button class="btn small danger" data-delete="${escapeHtml(skill.name)}" ${hasCentral ? '' : 'disabled'}>Delete</button>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;

    qsa('[data-edit]', list).forEach(btn => {
        btn.addEventListener('click', () => editSkill(btn.dataset.edit));
    });
    qsa('[data-preview-skill]', list).forEach(btn => {
        btn.addEventListener('click', () => previewSkill(btn.dataset.previewSkill));
    });
    qsa('[data-delete]', list).forEach(btn => {
        btn.addEventListener('click', () => deleteSkill(btn.dataset.delete));
    });
    qsa('[data-skill-presence]', list).forEach(input => {
        input.addEventListener('change', () => setSkillPresence(input));
    });
}

async function setSkillPresence(input) {
    const skillName = input.dataset.skillPresence;
    const locationId = input.dataset.locationId;
    const present = input.checked;
    const location = state.skillPresence
        .find(skill => skill.name === skillName)
        ?.locations.find(item => item.location_id === locationId);
    const locationName = location?.name || 'this location';

    if (!present && !confirm(`Remove "${skillName}" from ${locationName}?`)) {
        input.checked = true;
        return;
    }

    input.disabled = true;
    try {
        const result = await API.post('/api/skills/presence', {
            skill_name: skillName,
            location_id: locationId,
            present,
        });
        await loadSkills();
        showToast(result.message);
    } catch (err) {
        input.checked = !present;
        input.disabled = false;
        showToast(err.message, 'error');
    }
}

async function previewSkill(name) {
    try {
        const { content } = await API.get(`/api/skills/${encodeURIComponent(name)}/content`);
        const body = document.createElement('div');
        body.innerHTML = `<p class="skill-preview-path"><code>~/.agents/skills/${escapeHtml(name)}/SKILL.md</code></p>`;
        const frontmatterEnd = content.startsWith('---\n') ? content.indexOf('\n---', 4) : -1;
        const markdown = frontmatterEnd >= 0 ? content.slice(frontmatterEnd + 4).trim() : content;
        const preview = document.createElement('div');
        preview.className = 'markdown-preview';
        if (window.marked && window.DOMPurify) {
            preview.innerHTML = DOMPurify.sanitize(marked.parse(markdown, { gfm: true }));
        } else {
            preview.textContent = markdown;
        }
        body.appendChild(preview);
        openModal(`Preview: ${name}`, body, [makeButton('Close', 'primary', closeModal)]);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

qs('#skill-filter').addEventListener('input', renderSkills);

function skillForm(skill = null) {
    const form = document.createElement('form');
    form.innerHTML = `
        <div class="form-group">
            <label>Name</label>
            <input type="text" name="name" value="${skill ? escapeHtml(skill.name) : ''}" required>
        </div>
        <div class="form-group">
            <label>Description</label>
            <textarea name="description">${skill ? escapeHtml(skill.description) : ''}</textarea>
        </div>
        <div class="form-group">
            <label>Tags (comma separated)</label>
            <input type="text" name="tags" value="${skill ? escapeHtml(skill.tags.join(', ')) : ''}">
        </div>
    `;
    return form;
}

qs('#btn-add-skill').addEventListener('click', () => {
    const form = skillForm();
    openModal('Add Skill', form, [
        makeButton('Cancel', '', closeModal),
        makeButton('Save', 'primary', async () => {
            const data = Object.fromEntries(new FormData(form));
            const tags = data.tags.split(',').map(t => t.trim()).filter(Boolean);
            await API.post('/api/skills', { name: data.name, description: data.description, tags, path: '/' });
            closeModal();
            await loadSkills();
            showSkillUsage(data.name);
        }),
    ]);
});

qs('#btn-upload-skill').addEventListener('click', () => {
    qs('#skill-upload-input').click();
});

qs('#skill-upload-input').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const skill = await API.upload('/api/skills/upload', formData);
        await loadSkills();
        showSkillUsage(skill.name);
    } catch (err) {
        showToast(err.message, 'error');
    }
});

qs('#btn-import-skill-url').addEventListener('click', () => {
    const form = document.createElement('form');
    form.innerHTML = `
        <div class="form-group">
            <label>GitHub skill link</label>
            <input type="text" name="url" placeholder="https://github.com/owner/repo/blob/main/path/SKILL.md" required>
        </div>
        <p class="modal-help">Paste a GitHub Markdown file link or raw GitHub URL. The skill name comes from frontmatter, or from the filename when possible.</p>
    `;

    openModal('Import Skill from GitHub', form, [
        makeButton('Cancel', '', closeModal),
        makeButton('Import', 'primary', async () => {
            const data = Object.fromEntries(new FormData(form));
            try {
                const skill = await API.post('/api/skills/import-url', { url: data.url });
                closeModal();
                await loadSkills();
                showSkillUsage(skill.name);
            } catch (err) {
                showToast(err.message, 'error');
            }
        }),
    ]);
});

function showSkillUsage(skillName) {
    const body = document.createElement('div');
    body.innerHTML = `
        <p>Your skill is saved at <code>~/.agents/skills/${escapeHtml(skillName)}/SKILL.md</code>.</p>
        <p>Two simple ways to use it:</p>
        <ol>
            <li>
                <strong>Via a symlinked agent directory.</strong>
                Make sure <code>~/.cursor/skills/</code> (or <code>~/.claude/skills/</code>, <code>~/.codex/skills/</code>, <code>~/.config/opencode/skills/</code>) is symlinked to <code>~/.agents/skills/</code>. The agent will see the skill automatically.
            </li>
            <li>
                <strong>Inside a project.</strong>
                Copy the skill folder into your project’s <code>.agents/skills/</code> or <code>.cursor/skills/</code> directory.
            </li>
        </ol>
        <p class="hint">Remember to restart the agent/editor after adding or changing a skill.</p>
    `;
    openModal(`Skill saved: ${skillName}`, body, [
        makeButton('Got it', 'primary', closeModal),
    ]);
    showToast('Skill saved. Restart your agent/editor to pick it up.');
}

async function editSkill(name) {
    const skill = state.skills.find(s => s.name === name);
    if (!skill) return;
    const form = skillForm(skill);
    openModal('Edit Skill', form, [
        makeButton('Cancel', '', closeModal),
        makeButton('Save', 'primary', async () => {
            const data = Object.fromEntries(new FormData(form));
            const tags = data.tags.split(',').map(t => t.trim()).filter(Boolean);
            await API.post('/api/skills', { name: data.name, description: data.description, tags, path: '/' });
            if (data.name !== name) {
                await API.post(`/api/skills/${encodeURIComponent(name)}/rename?new_name=${encodeURIComponent(data.name)}`, {});
            }
            closeModal();
            await loadSkills();
            showSkillUsage(data.name);
        }),
    ]);
}

async function deleteSkill(name) {
    if (!confirm(`Delete skill "${name}"?`)) return;
    await API.delete(`/api/skills/${encodeURIComponent(name)}`);
    await loadSkills();
    showToast('Skill deleted. Restart your agent/editor if it was loaded.');
}

// Targets
async function loadTargets() {
    const [targets, defaults] = await Promise.all([
        API.get('/api/targets'),
        API.get('/api/targets/defaults'),
    ]);
    state.targets = targets;
    state.defaultTargets = defaults;
    state.enabledDefaults = defaults
        .filter(d => targets.some(t => t.id === d.id))
        .map(d => d.id);
    renderTargets();
    renderDefaultTargets();
}

async function saveDefaultTargets(enabledIds) {
    await API.post('/api/targets/defaults', enabledIds);
    await loadTargets();
    showToast('Known agent locations updated');
}

function renderTargets() {
    const list = qs('#targets-list');
    if (!state.targets.length) {
        list.innerHTML = '<div class="empty">No agent locations configured.</div>';
        return;
    }

    const statusDescriptions = {
        missing: 'This agent skills directory has not been created yet.',
        directory: 'An independent skills directory exists at this location.',
        symlink_ok: 'This location is linked to the central hub.',
        symlink_broken: 'This symlink points to a location that is no longer available.',
        file: 'A file exists where the agent skills directory should be.',
    };

    list.innerHTML = state.targets.map(t => {
        const stateClass = t.state.replace('_', '-');
        return `
        <div class="card" data-target="${escapeHtml(t.id)}">
            <div class="card-title">
                ${escapeHtml(t.name)}
                <span class="badge ${stateClass}">${t.state.replace('_', ' ')}</span>
            </div>
            <div class="card-meta">${escapeHtml(t.path)}</div>
            ${t.resolved_path ? `<div class="card-meta">-> ${escapeHtml(t.resolved_path)}</div>` : ''}
            <p class="target-status">${escapeHtml(statusDescriptions[t.state] || '')}</p>
            <p>${t.skills.length} skill(s) visible here</p>
            <div class="actions">
                ${t.state === 'directory' || t.state === 'missing' ? `<button class="btn small primary" data-preview="${escapeHtml(t.id)}">${t.state === 'missing' ? 'Preview & Create Link' : 'Preview & Symlink'}</button>` : ''}
                ${t.state === 'symlink_ok' ? `<button class="btn small danger" data-remove="${escapeHtml(t.id)}">Remove Link</button>` : ''}
                ${t.can_undo ? `<button class="btn small warning" data-undo="${escapeHtml(t.id)}">Restore Original</button>` : ''}
                ${isDefaultTarget(t) ? `<button class="btn small" data-remove-default-target="${escapeHtml(t.id)}">Remove Location</button>` : ''}
                ${!isDefaultTarget(t) ? `<button class="btn small danger" data-delete-target="${escapeHtml(t.id)}">Remove Location</button>` : ''}
            </div>
        </div>
    `}).join('');

    qsa('[data-preview]', list).forEach(btn => {
        btn.addEventListener('click', () => previewTarget(btn.dataset.preview));
    });
    qsa('[data-remove]', list).forEach(btn => {
        btn.addEventListener('click', () => removeSymlink(btn.dataset.remove));
    });
    qsa('[data-undo]', list).forEach(btn => {
        btn.addEventListener('click', () => undoSymlink(btn.dataset.undo));
    });
    qsa('[data-delete-target]', list).forEach(btn => {
        btn.addEventListener('click', () => deleteTarget(btn.dataset.deleteTarget));
    });
    qsa('[data-remove-default-target]', list).forEach(btn => {
        btn.addEventListener('click', () => removeDefaultTarget(btn.dataset.removeDefaultTarget));
    });
}

function isDefaultTarget(target) {
    return target.is_default;
}

function renderDefaultTargets() {
    let container = qs('#default-targets');
    if (!container) {
        container = document.createElement('div');
        container.id = 'default-targets';
        container.className = 'default-targets';
        qs('#targets').insertBefore(container, qs('#targets-list-header'));
    }

    if (!state.defaultTargets.length) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div class="info-box">
            <strong>Known agent locations:</strong> check the ones you want to manage. Unchecked locations stay hidden from the dashboard.
            <div class="default-targets-list">
                ${state.defaultTargets.map(t => `
                    <div class="default-target-row">
                        <label class="checkbox-row">
                            <input type="checkbox" value="${escapeHtml(t.id)}" ${state.enabledDefaults.includes(t.id) ? 'checked' : ''}>
                            <span class="default-target-name">${escapeHtml(t.name)}</span>
                            <code class="default-target-path">${escapeHtml(t.path)}</code>
                        </label>
                        <button class="btn small danger" data-remove-default="${escapeHtml(t.id)}">Remove</button>
                    </div>
                `).join('')}
            </div>
            <button class="btn small" id="btn-save-defaults">Save</button>
        </div>
    `;

    qs('#btn-save-defaults', container).addEventListener('click', () => {
        const checked = qsa('input[type="checkbox"]:checked', container).map(cb => cb.value);
        saveDefaultTargets(checked);
    });
    qsa('[data-remove-default]', container).forEach(btn => {
        btn.addEventListener('click', () => removeDefaultTarget(btn.dataset.removeDefault));
    });
}

async function removeDefaultTarget(id) {
    const target = state.defaultTargets.find(t => t.id === id);
    if (!target) return;
    if (!confirm(`Remove ${target.name} from known agent locations?\n\nThis removes the path from the app. It does not delete files or remove symlinks on your computer.`)) {
        return;
    }
    await API.delete(`/api/targets?target_id=${encodeURIComponent(id)}`);
    await loadTargets();
    showToast('Known agent location removed');
}

async function previewTarget(id, conflictStrategy = 'rename') {
    try {
        const preview = await API.get(`/api/targets/preview?target_id=${encodeURIComponent(id)}&move_existing=true&conflict_strategy=${encodeURIComponent(conflictStrategy)}`);
        const target = preview.target;
        const listItems = preview.existing_skills.map(s =>
            `<li>${escapeHtml(s.name)}${s.description ? ` - ${escapeHtml(s.description)}` : ''}</li>`
        ).join('');
        const conflicts = preview.conflicts.map(c => `<li class="conflict">${escapeHtml(c)}</li>`).join('');

        const operations = preview.operations.map(escapeHtml).join('\n');

        const body = document.createElement('div');
        body.innerHTML = `
            <p>${escapeHtml(preview.message)}</p>
            ${operations ? `<h4>Execution plan</h4><pre class="execution-plan"><code>${operations}</code></pre>` : ''}
            ${listItems ? `<h4>Existing skills (${preview.existing_skills.length})</h4><ul class="preview-list">${listItems}</ul>` : ''}
            ${conflicts ? `<h4>Conflicts</h4><p class="modal-help">A conflict means a skill with the same name already exists in the central hub. Choose how to keep both versions below.</p><ul class="preview-list">${conflicts}</ul>` : ''}
            ${preview.existing_skills.length ? `
                <div class="checkbox-row">
                    <input type="checkbox" id="move-existing" checked>
                    <label for="move-existing">Move existing skills into central hub</label>
                </div>
                <div class="form-group">
                    <label>Conflict strategy</label>
                    <div class="modal-help conflict-strategy-help">
                        <p><strong>Rename</strong> keeps both complete skills by giving the incoming one a new name.</p>
                        <p><strong>Merge</strong> keeps the global skill and adds only agent-location files that are missing from it.</p>
                        <p><strong>Delete duplicate</strong> keeps the global skill unchanged and permanently deletes the duplicate from the agent location.</p>
                    </div>
                    <select id="conflict-strategy" class="preset-select">
                        <option value="rename" ${conflictStrategy === 'rename' ? 'selected' : ''}>Rename (e.g. skill -> skill_1)</option>
                        <option value="merge" ${conflictStrategy === 'merge' ? 'selected' : ''}>Merge directories</option>
                        <option value="discard" ${conflictStrategy === 'discard' ? 'selected' : ''}>Delete duplicate from agent location</option>
                    </select>
                </div>
                ${conflictStrategy === 'discard' ? `<div class="checkbox-row"><input type="checkbox" id="confirm-discard"><label for="confirm-discard">I understand the duplicate in the agent location will be permanently deleted.</label></div>` : ''}
            ` : ''}
        `;

        const conflictSelect = qs('#conflict-strategy', body);
        if (conflictSelect) {
            conflictSelect.addEventListener('change', (event) => {
                previewTarget(id, event.target.value);
            });
        }

        const actions = [
            makeButton('Cancel', '', closeModal),
        ];
        if (preview.can_symlink) {
            actions.push(makeButton('Create Symlink', 'primary', async () => {
                const moveExisting = qs('#move-existing', body)?.checked ?? false;
                const conflictStrategy = qs('#conflict-strategy', body)?.value ?? 'rename';
                if (conflictStrategy === 'discard' && !qs('#confirm-discard', body)?.checked) {
                    showToast('Confirm that the duplicate in the agent location can be deleted.', 'error');
                    return;
                }
                const result = await API.post('/api/targets/symlink', {
                    target_id: id,
                    move_existing: moveExisting,
                    conflict_strategy: conflictStrategy,
                });
                closeModal();
                await loadTargets();
                showToast(
                    result.status === 'ok'
                        ? `${result.message} Restart that agent/editor to use the hub.`
                        : result.message,
                    result.status === 'ok' ? 'success' : 'error'
                );
            }));
        }

        openModal(`Preview: ${target.name}`, body, actions);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function removeSymlink(id) {
    const target = state.targets.find(t => t.id === id);
    if (!target) return;
    const body = document.createElement('div');
    body.innerHTML = `
        <p>Remove symlink at <code>${escapeHtml(target.path)}</code>?</p>
        <div class="checkbox-row">
            <input type="checkbox" id="restore-dir">
            <label for="restore-dir">Recreate an empty directory afterward</label>
        </div>
    `;
    openModal('Remove Link', body, [
        makeButton('Cancel', '', closeModal),
        makeButton('Remove', 'danger', async () => {
            const restore = qs('#restore-dir', body).checked;
            const result = await API.post('/api/targets/remove-symlink', {
                target_id: id,
                restore,
            });
            closeModal();
            await loadTargets();
            showToast(
                result.status === 'ok'
                    ? `${result.message} Restart that agent/editor so it reloads its own directory.`
                    : result.message,
                result.status === 'ok' ? 'success' : 'error'
            );
        }),
    ]);
}

async function undoSymlink(id) {
    const target = state.targets.find(t => t.id === id);
    if (!target) return;
    if (!confirm(`Restore original skills for ${target.name}?\n\nThis will restore the original directory and move skills back from the central hub.`)) {
        return;
    }
    const result = await API.post('/api/targets/undo-symlink', { target_id: id });
    await loadTargets();
    showToast(
        result.status === 'ok'
            ? `${result.message} Restart that agent/editor to use its own directory again.`
            : result.message,
        result.status === 'ok' ? 'success' : 'error'
    );
}

qs('#btn-add-target').addEventListener('click', () => {
    const presets = [
        { label: 'Custom', name: '', path: '' },
        ...state.defaultTargets.map(t => ({ label: t.name, name: t.name, path: t.path })),
    ];
    const presetOptions = presets.map((p, i) =>
        `<option value="${i}">${escapeHtml(p.label)}</option>`
    ).join('');

    const form = document.createElement('form');
    form.innerHTML = `
        <div class="form-group">
            <label>Known agent location</label>
            <select name="preset" class="preset-select">
                ${presetOptions}
            </select>
        </div>
        <div class="form-group">
            <label>Agent Name</label>
            <input type="text" name="name" placeholder="My Editor" required>
        </div>
        <div class="form-group">
            <label>Path</label>
            <input type="text" name="path" placeholder="~/.myeditor/skills" required>
        </div>
    `;

    const nameInput = qs('input[name="name"]', form);
    const pathInput = qs('input[name="path"]', form);
    qs('select[name="preset"]', form).addEventListener('change', () => {
        const idx = Number(qs('select[name="preset"]', form).value);
        const p = presets[idx];
        nameInput.value = p.name;
        pathInput.value = p.path;
    });

    openModal('Add Agent Location', form, [
        makeButton('Cancel', '', closeModal),
        makeButton('Add', 'primary', async () => {
            const data = Object.fromEntries(new FormData(form));
            await API.post('/api/targets', { name: data.name, path: data.path, id: data.path, state: 'missing' });
            closeModal();
            await loadTargets();
            showToast('Agent location added');
        }),
    ]);
});

async function deleteTarget(id) {
    if (!confirm('Remove this custom agent location from the app?\n\nThis does not delete files or remove symlinks on your computer.')) return;
    await API.delete(`/api/targets?target_id=${encodeURIComponent(id)}`);
    await loadTargets();
    showToast('Agent location deleted');
}

// Projects
qs('#btn-scan-project').addEventListener('click', async () => {
    const path = qs('#project-path').value.trim();
    if (!path) {
        showToast('Enter a project path', 'error');
        return;
    }
    try {
        state.project = await API.get(`/api/projects/scan?path=${encodeURIComponent(path)}`);
        renderProject();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

function renderProject() {
    const list = qs('#projects-list');
    if (!state.project || !state.project.skill_dirs.length) {
        list.innerHTML = '<div class="empty">No skill directories found in this project.</div>';
        return;
    }

    list.innerHTML = state.project.skill_dirs.map(dir => {
        const skills = dir.skills.map(s => `
            <div class="skill-select checkbox-row">
                <input type="checkbox" id="skill-${escapeHtml(dir.agent_name)}-${escapeHtml(s.name)}" value="${escapeHtml(s.name)}">
                <label for="skill-${escapeHtml(dir.agent_name)}-${escapeHtml(s.name)}">${escapeHtml(s.name)}</label>
            </div>
        `).join('');
        return `
        <div class="card" data-agent="${escapeHtml(dir.agent_name)}">
            <div class="card-title">${escapeHtml(dir.agent_name)}</div>
            <div class="card-meta">${escapeHtml(dir.relative_path)}</div>
            ${skills ? `<div class="skills-to-import">${skills}</div>` : '<p>No skills in this directory.</p>'}
            <div class="actions">
                <button class="btn small primary" data-import-dir="${escapeHtml(dir.agent_name)}">Import Selected</button>
            </div>
        </div>
    `}).join('');

    qsa('[data-import-dir]', list).forEach(btn => {
        btn.addEventListener('click', () => importFromDir(btn.dataset.importDir));
    });
}

async function importFromDir(agentName) {
    const dir = state.project.skill_dirs.find(d => d.agent_name === agentName);
    if (!dir) return;
    const checked = qsa(`input[type="checkbox"]:checked`, qs(`[data-agent="${CSS.escape(agentName)}"]`));
    const names = checked.map(cb => cb.value);
    if (!names.length) {
        showToast('Select at least one skill to import', 'error');
        return;
    }
    const result = await API.post('/api/projects/import', {
        source_path: dir.absolute_path,
        skill_names: names,
        conflict_strategy: 'rename',
    });
    await loadSkills();
    showToast(
        result.status === 'ok'
            ? `${result.message} Restart any agents/editors that should use them.`
            : result.message,
        result.status === 'ok' ? 'success' : 'error'
    );
}

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Init dashboard data only when the dashboard is present
if (qs('#skills-list')) {
    (async function init() {
        await loadSkills();
        await loadTargets();
    })();
}
