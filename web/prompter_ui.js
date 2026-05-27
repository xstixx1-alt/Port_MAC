/* 
* Stocky non Stop — AI Prompter UI
* Автор: Азат | Telegram: @inomix
*/
// === STOCK PROMPTER UI LOGIC ===

function _getPrompter() {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return null;
    let t = tabs[activeTabId];

    if (!t.prompter) {
        t.prompter = {
            apiKey: '',
            provider: '',
            model: '',
            docxPath: '',
            srtPath: '',
            saveDir: '',
            srtPreview: '',
            srtSubsCount: 0,
            srtDurationSec: 0,
            totalPrompts: 0,
            scenesCount: 0,
            scenes: [],
            resultFilePath: '',
            failedCount: 0,
            errorBanner: '',
            isGenerating: false,
            isStopping: false,
            wasStopped: false,
            status: 'Ожидание...',
            progressText: '0/0',
            progressPercent: 0,
            logs: '',
            logsCollapsed: false,
            settingsCollapsed: false,
            threads: 3,
            pauseEvery: 100,
            pauseSeconds: 5,
            aiPool: []
        };
    }
    return t.prompter;
}

function prompterNormalizeThreads(value) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return 3;
    return Math.max(1, Math.min(50, parsed));
}

function prompterNormalizePauseEvery(value) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return 100;
    return Math.max(1, Math.min(1000, parsed));
}

function prompterNormalizePauseSeconds(value) {
    const parsed = Number(String(value).replace(',', '.'));
    if (!Number.isFinite(parsed)) return 5;
    return Math.max(0, Math.min(120, parsed));
}

function prompterGetModelOptions(provider) {
    if (window.getAiProviderModels) return window.getAiProviderModels(provider || 'deepseek', null);
    if (provider === 'openrouter') return ['google/gemini-3.1-pro-preview', 'google/gemini-3.1-flash-lite-preview', 'openai/gpt-5.4-nano', 'deepseek/deepseek-v4-flash'];
    if (provider === 'gemini') return ['gemini-3.1-pro-preview', 'gemini-3.5-flash', 'gemini-3.1-flash-lite'];
    return ['deepseek-v4-flash', 'deepseek-v4-pro'];
}

function prompterDefaultModel(provider, conf = null) {
    if (conf && window.getAiModelByProvider) {
        return window.getAiModelByProvider(conf, provider || 'deepseek');
    }
    const options = prompterGetModelOptions(provider);
    return options[0] || '';
}

function prompterGetSavedKey(provider, conf = null) {
    if (conf && window.getAiKeyByProvider) {
        return window.getAiKeyByProvider(conf, provider || 'deepseek') || '';
    }
    return '';
}

function prompterNormalizeAiPool(pool) {
    return (Array.isArray(pool) ? pool : []).map((worker) => {
        const provider = worker.provider || 'deepseek';
        const options = prompterGetModelOptions(provider);
        const model = worker.model || options[0] || '';
        return {
            enabled: worker.enabled !== false,
            provider,
            model,
            apiKey: worker.apiKey || worker.api_key || '',
            showKey: !!worker.showKey
        };
    });
}

function prompterRenderAiPool() {
    const list = document.getElementById('prompter-ai-pool-list');
    const summary = document.getElementById('prompter-ai-pool-summary');
    const p = _getPrompter();
    if (!list || !p) return;

    p.aiPool = prompterNormalizeAiPool(p.aiPool);
    const activeCount = p.aiPool.filter(w => w.enabled && w.apiKey && w.model).length;
    if (summary) {
        const scenes = Array.isArray(p.scenes) ? p.scenes.length : 0;
        const approx = activeCount > 0 && scenes > 0 ? ` | ${scenes} сцен ≈ ${Math.ceil(scenes / activeCount)} на воркер` : '';
        summary.textContent = activeCount > 0 ? `Активно: ${activeCount}${approx}` : 'Если пул пустой, используется выбранный провайдер выше';
    }

    if (p.aiPool.length === 0) {
        list.innerHTML = `
            <div class="rounded-xl border border-white/5 bg-black/20 px-3 py-3 text-[11px] text-white/35">
                Пул пуст. Можно добавить текущего провайдера или создать воркер вручную.
            </div>
        `;
        return;
    }

    list.innerHTML = p.aiPool.map((worker, index) => {
        const providerOptions = ['gemini', 'openrouter', 'deepseek'].map(provider => (
            `<option value="${provider}" ${worker.provider === provider ? 'selected' : ''}>${provider === 'openrouter' ? 'OpenRouter' : provider === 'gemini' ? 'Gemini' : 'DeepSeek'}</option>`
        )).join('');
        const modelOptions = prompterGetModelOptions(worker.provider).map(model => (
            `<option value="${model}" ${worker.model === model ? 'selected' : ''}>${model}</option>`
        )).join('');
        return `
            <div class="rounded-xl border border-[#A855F7]/15 bg-black/25 p-3 space-y-2">
                <div class="grid grid-cols-[auto_1fr_1fr_auto] gap-2 items-center">
                    <input type="checkbox" ${worker.enabled ? 'checked' : ''} onchange="prompterUpdatePoolWorker(${index}, 'enabled', this.checked)"
                        class="rounded border-white/10 bg-black/40 text-[#A855F7] focus:ring-0 w-4 h-4">
                    <select onchange="prompterUpdatePoolWorker(${index}, 'provider', this.value)"
                        class="bg-black/40 border border-white/5 rounded-lg px-2 py-2 text-[11px] text-white focus:ring-1 focus:ring-[#A855F7]">
                        ${providerOptions}
                    </select>
                    <select onchange="prompterUpdatePoolWorker(${index}, 'model', this.value)"
                        class="bg-black/40 border border-white/5 rounded-lg px-2 py-2 text-[11px] text-white focus:ring-1 focus:ring-[#A855F7]">
                        ${modelOptions}
                    </select>
                    <button type="button" onclick="prompterRemovePoolWorker(${index})"
                        class="w-8 h-8 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-200 border border-red-400/20 flex items-center justify-center">
                        <span class="material-symbols-outlined !text-base">delete</span>
                    </button>
                </div>
                <div class="flex gap-2">
                    <input type="${worker.showKey ? 'text' : 'password'}" value="${escapeHtml(worker.apiKey)}"
                        oninput="prompterUpdatePoolWorker(${index}, 'apiKey', this.value)"
                        onkeydown="event.stopPropagation()"
                        class="w-full bg-black/40 border border-white/5 rounded-lg px-3 py-2 text-[11px] text-white focus:ring-1 focus:ring-[#A855F7]"
                        placeholder="API key для этого воркера">
                    <button type="button" onclick="prompterTogglePoolKey(${index})"
                        class="w-9 h-8 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 border border-white/5 flex items-center justify-center">
                        <span class="material-symbols-outlined !text-base">${worker.showKey ? 'visibility_off' : 'visibility'}</span>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

window.togglePrompterApiKeyVisibility = function () {
    const input = document.getElementById('prompter-api-key');
    const button = document.getElementById('prompter-api-key-toggle');
    if (!input) return;
    const shouldShow = input.type === 'password';
    input.type = shouldShow ? 'text' : 'password';
    if (button) {
        button.innerHTML = `<span class="material-symbols-outlined !text-base">${shouldShow ? 'visibility_off' : 'visibility'}</span>`;
    }
};

function prompterLogClass(type) {
    if (type === 'success') return 'text-emerald-400';
    if (type === 'error') return 'text-red-400';
    if (type === 'warning') return 'text-yellow-300';
    return 'text-[#d8b4fe]';
}

function prompterRenderLogs() {
    const p = _getPrompter();
    if (!p) return;

    const block = document.getElementById('prompter-log-block');
    const body = document.getElementById('prompter-log-body');
    const percent = document.getElementById('prompter-log-percent');
    const status = document.getElementById('prompter-log-status');
    const toggle = document.getElementById('prompter-log-toggle');
    if (!block || !body) return;

    block.classList.toggle('hidden', !!p.logsCollapsed);
    body.innerHTML = p.logs || '<div class="text-white/25">Ожидание запуска генерации...</div>';
    body.scrollTop = body.scrollHeight;
    if (percent) percent.textContent = `${p.progressPercent || 0}%`;
    if (status) status.innerHTML = p.status || 'Ожидание...';
    const fill = document.getElementById('prompter-log-progress-fill');
    if (fill) fill.style.width = `${p.progressPercent || 0}%`;
    if (toggle) toggle.textContent = p.logsCollapsed ? 'expand_more' : 'expand_less';
}

window.prompterAppendLog = function (tab_id, message, type = 'info', time = null) {
    if (!tabs[tab_id] || !tabs[tab_id].prompter) return;
    const p = tabs[tab_id].prompter;
    const now = time || new Date().toLocaleTimeString();
    const line = `[${now}] ${message}`;
    const cls = prompterLogClass(type);
    p.logs = (p.logs || '') + `<div class="${cls} whitespace-pre-wrap">${escapeHtml(line)}</div>`;
    if (activeTabId === tab_id) prompterRenderLogs();
};

window.prompterClearLogs = function () {
    const p = _getPrompter();
    if (!p) return;
    p.logs = '';
    prompterRenderLogs();
};

window.prompterCopyLogs = function () {
    const p = _getPrompter();
    if (!p || !p.logs) return;
    const temp = document.createElement('div');
    temp.innerHTML = p.logs;
    navigator.clipboard.writeText(temp.innerText || '');
};

window.prompterToggleLogs = function () {
    const p = _getPrompter();
    if (!p) return;
    p.logsCollapsed = !p.logsCollapsed;
    prompterRenderLogs();
};

function prompterSettingsSummary(p) {
    const activePool = prompterNormalizeAiPool(p.aiPool).filter(w => w.enabled && w.apiKey && w.model).length;
    const provider = p.provider || 'deepseek';
    const providerLabel = provider === 'openrouter' ? 'OpenRouter' : (provider === 'gemini' ? 'Gemini' : 'DeepSeek');
    const poolPart = activePool > 0 ? `pool ${activePool}` : 'без pool';
    const scenesPart = p.srtSubsCount ? `${p.srtSubsCount} сцен` : 'SRT не выбран';
    const savePart = p.saveDir ? 'Save ✓' : 'Save рядом';
    return `${providerLabel} · ${poolPart} · ${prompterNormalizeThreads(p.threads)} потоков · ${scenesPart} · ${savePart}`;
}

function prompterRenderSettingsShell() {
    const p = _getPrompter();
    if (!p) return;
    const body = document.getElementById('prompter-settings-body');
    const summary = document.getElementById('prompter-settings-summary');
    const toggle = document.getElementById('prompter-settings-toggle');
    if (body) body.classList.toggle('hidden', !!p.settingsCollapsed);
    if (summary) summary.textContent = prompterSettingsSummary(p);
    if (toggle) toggle.textContent = p.settingsCollapsed ? 'expand_more' : 'expand_less';
}

window.prompterToggleSettings = function () {
    const p = _getPrompter();
    if (!p) return;
    p.settingsCollapsed = !p.settingsCollapsed;
    prompterRenderSettingsShell();
};

function prompterGetClipRules() {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return [];
    return getClipRules();
}

function prompterSyncClipRulesValidation() {
    const box = document.getElementById('prompter-clip-rules-validation');
    if (!box || !activeTabId || !tabs[activeTabId]) return true;
    const validation = validateClipRules(prompterGetClipRules());
    box.textContent = validation.errors.join('\n');
    box.classList.toggle('hidden', validation.valid);
    return validation.valid;
}

function prompterRenderClipRules() {
    const list = document.getElementById('prompter-clip-rules-list');
    if (!list || !activeTabId || !tabs[activeTabId]) return;
    const rules = prompterGetClipRules();
    list.innerHTML = rules.map((rule, index) => `
        <div class="rounded-2xl border border-white/5 bg-black/20 p-3 space-y-3">
            <div class="grid grid-cols-[1fr_1fr_1.2fr_auto] gap-3 items-end">
                <div>
                    <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">От</label>
                    <input type="text" value="${formatClipTime(rule.from)}"
                        oninput="prompterUpdateClipRuleTime(${index}, 'from', this.value)"
                        onblur="prompterNormalizeClipRuleTimeInput(${index}, 'from')"
                        class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                </div>
                <div>
                    <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">До</label>
                    <input type="text" value="${rule.to === null ? 'конец' : formatClipTime(rule.to)}"
                        oninput="prompterUpdateClipRuleTime(${index}, 'to', this.value)"
                        onblur="prompterNormalizeClipRuleTimeInput(${index}, 'to')"
                        class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                </div>
                <div>
                    <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">Режим</label>
                    <select onchange="prompterUpdateClipRuleMode(${index}, this.value)"
                        class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                        <option value="fixed" ${rule.mode === 'fixed' ? 'selected' : ''}>Фиксированно</option>
                        <option value="random" ${rule.mode === 'random' ? 'selected' : ''}>Случайно</option>
                    </select>
                </div>
                <button onclick="prompterRemoveClipRule(${index})"
                    class="h-[38px] px-3 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-300 text-[10px] font-black uppercase tracking-widest transition-colors">
                    Удалить
                </button>
            </div>
            ${rule.mode === 'fixed' ? `
                <div>
                    <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">Длительность, сек</label>
                    <input type="number" min="0.1" max="6" step="0.001" value="${formatClipFloat(rule.duration ?? 3)}"
                        oninput="prompterUpdateClipRuleNumber(${index}, 'duration', this.value)"
                        class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                </div>
            ` : `
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">От, сек</label>
                        <input type="number" min="0.1" max="6" step="0.001" value="${formatClipFloat(rule.durationMin ?? 2)}"
                            oninput="prompterUpdateClipRuleNumber(${index}, 'durationMin', this.value)"
                            class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                    </div>
                    <div>
                        <label class="text-[9px] font-black uppercase tracking-widest text-white/35 block mb-1">До, сек</label>
                        <input type="number" min="0.1" max="6" step="0.001" value="${formatClipFloat(rule.durationMax ?? 4)}"
                            oninput="prompterUpdateClipRuleNumber(${index}, 'durationMax', this.value)"
                            class="w-full bg-[#1a1a2e] border border-white/5 rounded-xl px-3 py-2 text-xs text-white focus:ring-1 focus:ring-[#A855F7]/40">
                    </div>
                </div>
            `}
        </div>
    `).join('');
    prompterSyncClipRulesValidation();
}

window.prompterUpdateClipRuleTime = function (index, field, value) {
    const rules = prompterGetClipRules();
    if (!rules[index]) return;
    rules[index][field] = parseClipTimeInput(value);
    prompterSyncClipRulesValidation();
    prompterRecalcTotal();
};

window.prompterNormalizeClipRuleTimeInput = function (index, field) {
    const rules = prompterGetClipRules();
    if (!rules[index]) return;
    const value = rules[index][field];
    if (field === 'to' && value === null) {
        prompterRenderClipRules();
        return;
    }
    if (Number.isFinite(value)) {
        rules[index][field] = Number(value);
    }
    prompterRenderClipRules();
    prompterRecalcTotal();
};

window.prompterUpdateClipRuleNumber = function (index, field, value) {
    const rules = prompterGetClipRules();
    if (!rules[index]) return;
    const num = Number(String(value).replace(',', '.'));
    rules[index][field] = Number.isFinite(num) ? num : Number.NaN;
    prompterSyncClipRulesValidation();
    prompterRecalcTotal();
};

window.prompterUpdateClipRuleMode = function (index, mode) {
    const rules = prompterGetClipRules();
    if (!rules[index]) return;
    const current = rules[index];
    current.mode = mode;
    if (mode === 'fixed') {
        current.duration = Number.isFinite(current.duration) ? current.duration : (Number.isFinite(current.durationMin) ? current.durationMin : 3);
    } else {
        current.durationMin = Number.isFinite(current.durationMin) ? current.durationMin : (Number.isFinite(current.duration) ? current.duration : 2);
        current.durationMax = Number.isFinite(current.durationMax) ? current.durationMax : Math.max(current.durationMin, 4);
    }
    prompterRenderClipRules();
    prompterRecalcTotal();
};

window.prompterAddClipRule = function () {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    const rules = prompterGetClipRules();
    const last = rules[rules.length - 1];
    const nextFrom = last ? (last.to === null ? last.from + 60 : last.to) : 0;
    rules.push({ from: nextFrom, to: null, mode: 'random', durationMin: 3.0, durationMax: 6.0 });
    prompterRenderClipRules();
    prompterRecalcTotal();
};

window.prompterRemoveClipRule = function (index) {
    const rules = prompterGetClipRules();
    if (rules.length <= 1) return;
    rules.splice(index, 1);
    prompterRenderClipRules();
    prompterRecalcTotal();
};

function prompterBuildEstimatedClipPlan(duration, rules) {
    const normalizedRules = (rules || []).map(normalizeClipRuleForState);
    const validation = validateClipRules(normalizedRules);
    if (!validation.valid || !Number.isFinite(duration) || duration <= 0) {
        return { valid: validation.valid, errors: validation.errors, clips: [] };
    }

    const clips = [];
    let position = 0;

    while (position < duration) {
        const rule = normalizedRules.find((candidate) => position >= candidate.from && (candidate.to === null || position < candidate.to));
        if (!rule) break;

        const baseDuration = rule.mode === 'fixed'
            ? Number(rule.duration)
            : (Number(rule.durationMin) + Number(rule.durationMax)) / 2;

        const remaining = duration - position;
        const clipDuration = Math.min(baseDuration, remaining);
        if (!Number.isFinite(clipDuration) || clipDuration < 0.1) break;

        clips.push({
            start: Number(position.toFixed(3)),
            duration: Number(clipDuration.toFixed(3)),
            rule
        });
        position += clipDuration;
    }

    return { valid: true, errors: [], clips };
}

window.prompterSyncFromTab = function () {
    const p = _getPrompter();
    if (!p) return;

    const elSrt = document.getElementById('prompter-srt-path');
    const elDir = document.getElementById('prompter-save-dir');
    const elDocx = document.getElementById('prompter-docx-path');
    const elThreads = document.getElementById('prompter-threads');
    const elPauseEvery = document.getElementById('prompter-pause-every');
    const elPauseSeconds = document.getElementById('prompter-pause-seconds');
    if (elSrt) elSrt.value = p.srtPath || '';
    if (elDir) elDir.value = p.saveDir || '';
    if (elDocx) elDocx.value = p.docxPath || '';
    if (elThreads) elThreads.value = prompterNormalizeThreads(p.threads);
    if (elPauseEvery) elPauseEvery.value = prompterNormalizePauseEvery(p.pauseEvery);
    if (elPauseSeconds) elPauseSeconds.value = prompterNormalizePauseSeconds(p.pauseSeconds);
    prompterRenderAiPool();
    prompterRenderLogs();
    prompterRenderSettingsShell();
    prompterRenderClipRules();

    const srtPreviewEl = document.getElementById('prompter-srt-preview');
    if (srtPreviewEl) {
        if (p.srtSubsCount > 0) {
            srtPreviewEl.innerHTML = `Загружено <b class="text-[#A855F7]">${p.srtSubsCount}</b> субтитров<br><br><span class="opacity-50">${p.srtPreview}</span>`;
        } else {
            srtPreviewEl.innerHTML = 'Загружено 0 субтитров';
        }
    }

    const wList = document.getElementById('prompter-windows-list');
    if (wList) {
        if (p.scenes && p.scenes.length > 0) {
            let html = '';
            p.scenes.forEach((scene, i) => {
                const statusClass = scene.statusClass || 'text-white/30';
                const statusText = scene.status || 'ОЖИДАНИЕ';
                const promptValue = scene.prompt || '';
                const errorBlock = scene.error
                    ? `<div class="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-[11px] text-red-200">${scene.error}</div>`
                    : '';
                html += `
                    <div class="bg-[#11111a] border border-[#A855F7]/10 rounded-2xl p-4 flex flex-col gap-3 shrink-0">
                        <div class="flex justify-between items-center">
                            <div class="flex items-center gap-3">
                                <span class="inline-flex items-center justify-center min-w-[28px] h-7 px-2 rounded-lg bg-[#A855F7]/15 text-[#d8b4fe] text-[11px] font-black">${scene.scene_number || (i + 1)}</span>
                                <div class="flex flex-col">
                                    <span class="text-[10px] font-bold text-[#A855F7] uppercase tracking-widest">Сцена ${scene.scene_number || (i + 1)}</span>
                                    <span class="text-[10px] text-white/35">${(scene.duration_sec || 0).toFixed(1)}с</span>
                                </div>
                            </div>
                            <span id="prompter-scene-status-${i}" class="text-[10px] uppercase font-bold ${statusClass}">${statusText}</span>
                        </div>
                        <div class="rounded-xl border border-white/5 bg-black/30 px-3 py-3 text-[12px] leading-relaxed text-white/85">${escapeHtml(scene.text || '')}</div>
                        <div class="rounded-xl border border-[#0ea5e9]/20 bg-[#0b1220] p-3 flex flex-col gap-3">
                            <div class="flex items-center justify-between gap-3">
                                <span class="text-[10px] font-bold text-sky-300 uppercase tracking-widest">Prompt</span>
                                <button onclick="prompterRegenerateScene(${i})" class="px-3 py-1.5 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-200 text-[10px] font-black uppercase tracking-widest transition-colors">Перегенерировать</button>
                            </div>
                            <textarea id="prompter-scene-prompt-${i}" oninput="prompterSaveScenesToTab()" class="overlay-input w-full h-28 text-[11px] text-[#dbeafe] resize-none focus:ring-1 focus:ring-sky-500 custom-scrollbar bg-black/40 border-white/5 rounded-lg p-3">${promptValue}</textarea>
                            ${errorBlock}
                        </div>
                    </div>
                `;
            });
            wList.innerHTML = html;
        } else {
            wList.innerHTML = `
                <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div class="text-white/10 text-center font-bold uppercase tracking-widest text-sm flex flex-col items-center gap-2">
                        <span class="material-symbols-outlined text-4xl">inventory_2</span>
                        Сначала выберите SRT файл
                    </div>
                </div>
            `;
        }
    }

    const errorBanner = document.getElementById('prompter-error-banner');
    if (errorBanner) {
        if (p.errorBanner) {
            errorBanner.innerHTML = `
                <div class="flex items-center justify-between gap-3">
                    <span>${p.errorBanner}</span>
                    <button onclick="prompterRegenerateFailed()" class="px-3 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-100 text-[10px] font-black uppercase tracking-widest transition-colors">Перегенерировать ошибки</button>
                </div>
            `;
            errorBanner.classList.remove('hidden');
        } else {
            errorBanner.classList.add('hidden');
            errorBanner.innerHTML = '';
        }
    }

    const inp = document.getElementById('prompter-api-key');
    const providerEl = document.getElementById('prompter-provider');
    if (inp) {
        eel.get_config()(function (conf) {
            const provider = p.provider || (conf && conf.ai_provider) || "deepseek";
            const model = p.model || (window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : "");
            const aiKey = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : (p.apiKey || "");
            p.provider = provider;
            p.model = model;
            p.apiKey = aiKey;
            if (providerEl) providerEl.value = provider;
            inp.value = aiKey || "";
            if (window.renderAiModelOptions) window.renderAiModelOptions("prompter", provider, model, conf);
        });
    }

    prompterRecalcTotal();

    const btn = document.getElementById('btn-generate-prompts');
    const stopBtn = document.getElementById('btn-stop-prompts');
    const statusEl = document.getElementById('prompter-status');
    const progressBlock = document.getElementById('prompter-progress-block');
    const progressFill = document.getElementById('prompter-progress-fill');
    const progressText = document.getElementById('prompter-progress-text');

    if (statusEl) statusEl.innerHTML = p.status || 'Ожидание...';

    if (btn) {
        if (p.isGenerating) {
            btn.disabled = true;
            btn.innerHTML = '<span class="material-symbols-outlined animate-spin">sync</span> Генерация...';
            if (progressBlock) {
                progressBlock.classList.remove('hidden');
                if (progressFill) progressFill.style.width = `${p.progressPercent || 0}%`;
                if (progressText) progressText.innerText = p.progressText || '0/0';
            }
        } else {
            btn.disabled = false;
            btn.innerHTML = '<span class="material-symbols-outlined">auto_awesome</span> Сгенерировать';
            if (progressBlock) progressBlock.classList.add('hidden');
        }
    }

    if (stopBtn) {
        stopBtn.disabled = !p.isGenerating || p.isStopping;
        stopBtn.innerHTML = p.isStopping
            ? '<span class="material-symbols-outlined animate-spin !text-base">sync</span> Стоп...'
            : '<span class="material-symbols-outlined !text-base">stop_circle</span> Стоп';
    }
};

window.prompterSaveScenesToTab = function () {
    const p = _getPrompter();
    if (!p || !p.scenes) return;
    p.scenes.forEach((scene, i) => {
        const ta = document.getElementById(`prompter-scene-prompt-${i}`);
        if (ta) scene.prompt = ta.value;
    });
};

window.prompterSaveToTab = function () {
    const p = _getPrompter();
    if (!p) return;

    const inSrt = document.getElementById('prompter-srt-path');
    const inDocx = document.getElementById('prompter-docx-path');
    const inDir = document.getElementById('prompter-save-dir');
    const inKey = document.getElementById('prompter-api-key');
    const inProvider = document.getElementById('prompter-provider');
    const inModel = document.getElementById('prompter-model');
    const inThreads = document.getElementById('prompter-threads');
    const inPauseEvery = document.getElementById('prompter-pause-every');
    const inPauseSeconds = document.getElementById('prompter-pause-seconds');
    if (inSrt) p.srtPath = inSrt.value;
    if (inDocx) p.docxPath = inDocx.value;
    if (inDir) p.saveDir = inDir.value;
    if (inKey) p.apiKey = inKey.value;
    if (inProvider) p.provider = inProvider.value || 'deepseek';
    if (inModel) p.model = inModel.value || '';
    if (inThreads) {
        p.threads = prompterNormalizeThreads(inThreads.value);
        inThreads.value = p.threads;
    }
    if (inPauseEvery) {
        p.pauseEvery = prompterNormalizePauseEvery(inPauseEvery.value);
        inPauseEvery.value = p.pauseEvery;
    }
    if (inPauseSeconds) {
        p.pauseSeconds = prompterNormalizePauseSeconds(inPauseSeconds.value);
        inPauseSeconds.value = p.pauseSeconds;
    }
    p.aiPool = prompterNormalizeAiPool(p.aiPool);

    prompterSaveScenesToTab();

    const applyAllCb = document.getElementById('prompter-output-all');
    if (applyAllCb && applyAllCb.checked) {
        Object.keys(tabs).forEach(id => {
            if (id !== activeTabId && tabs[id].category === 'video') {
                if (!tabs[id].prompter) tabs[id].prompter = {};
                tabs[id].prompter.saveDir = p.saveDir;
            }
        });
    }

    const docxApplyCb = document.getElementById('prompter-docx-all');
    if (docxApplyCb && docxApplyCb.checked) {
        Object.keys(tabs).forEach(id => {
            if (id !== activeTabId && tabs[id].category === 'video') {
                if (!tabs[id].prompter) tabs[id].prompter = {};
                tabs[id].prompter.docxPath = p.docxPath;
            }
        });
    }
};

window.prompterSaveKey = function () {
    prompterSaveToTab();
    const key = document.getElementById('prompter-api-key').value;
    const provider = document.getElementById('prompter-provider').value || 'deepseek';
    const model = document.getElementById('prompter-model').value || '';
    eel.get_config()(function (conf) {
        if (conf) {
            conf.ai_provider = provider;
            if (window.setAiKeyByProvider) window.setAiKeyByProvider(conf, provider, key);
            if (window.setAiModelByProvider) window.setAiModelByProvider(conf, provider, model);
            eel.save_config(activeTabId, conf);
        }
    });
};

window.prompterProviderChanged = function () {
    const p = _getPrompter();
    if (!p) return;
    eel.get_config()(function (conf) {
        const previousProvider = p.provider || (conf && conf.ai_provider) || 'deepseek';
        const currentKeyInput = document.getElementById('prompter-api-key');
        const currentModelInput = document.getElementById('prompter-model');
        if (conf && previousProvider) {
            if (window.setAiKeyByProvider && currentKeyInput) window.setAiKeyByProvider(conf, previousProvider, currentKeyInput.value || '');
            if (window.setAiModelByProvider && currentModelInput) window.setAiModelByProvider(conf, previousProvider, currentModelInput.value || '');
        }
        const provider = document.getElementById('prompter-provider').value || 'deepseek';
        p.provider = provider;
        p.apiKey = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : '';
        p.model = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : '';
        if (conf) {
            conf.ai_provider = provider;
            eel.save_config(activeTabId, conf);
        }
        prompterSyncFromTab();
    });
};

window.prompterSaveModel = function () {
    prompterSaveToTab();
    prompterSaveKey();
};

window.prompterAddPoolWorker = function () {
    const p = _getPrompter();
    if (!p) return;
    eel.get_config()(function (conf) {
        const provider = (conf && conf.ai_provider) || p.provider || 'gemini';
        p.aiPool = prompterNormalizeAiPool(p.aiPool);
        p.aiPool.push({
            enabled: true,
            provider,
            model: prompterDefaultModel(provider, conf),
            apiKey: prompterGetSavedKey(provider, conf),
            showKey: false
        });
        prompterRenderAiPool();
    });
};

window.prompterAddCurrentToPool = function () {
    prompterSaveToTab();
    const p = _getPrompter();
    if (!p) return;
    eel.get_config()(function (conf) {
        const provider = p.provider || (conf && conf.ai_provider) || 'deepseek';
        p.aiPool = prompterNormalizeAiPool(p.aiPool);
        p.aiPool.push({
            enabled: true,
            provider,
            model: p.model || prompterDefaultModel(provider, conf),
            apiKey: p.apiKey || prompterGetSavedKey(provider, conf),
            showKey: false
        });
        prompterRenderAiPool();
    });
};

window.prompterUpdatePoolWorker = function (index, field, value) {
    const p = _getPrompter();
    if (!p) return;
    p.aiPool = prompterNormalizeAiPool(p.aiPool);
    const worker = p.aiPool[index];
    if (!worker) return;
    worker[field] = value;
    if (field === 'apiKey') {
        const summary = document.getElementById('prompter-ai-pool-summary');
        const activeCount = p.aiPool.filter(w => w.enabled && w.apiKey && w.model).length;
        if (summary) summary.textContent = activeCount > 0 ? `Активно: ${activeCount}` : 'Если пул пустой, используется выбранный провайдер выше';
        return;
    }
    if (field === 'provider') {
        eel.get_config()(function (conf) {
            worker.model = prompterDefaultModel(value, conf);
            worker.apiKey = prompterGetSavedKey(value, conf);
            prompterRenderAiPool();
        });
        return;
    }
    prompterRenderAiPool();
};

window.prompterRemovePoolWorker = function (index) {
    const p = _getPrompter();
    if (!p) return;
    p.aiPool = prompterNormalizeAiPool(p.aiPool);
    p.aiPool.splice(index, 1);
    prompterRenderAiPool();
};

window.prompterTogglePoolKey = function (index) {
    const p = _getPrompter();
    if (!p) return;
    p.aiPool = prompterNormalizeAiPool(p.aiPool);
    if (!p.aiPool[index]) return;
    p.aiPool[index].showKey = !p.aiPool[index].showKey;
    prompterRenderAiPool();
};

window.prompterRecalcTotal = function () {
    const p = _getPrompter();
    if (!p) return;

    const totalEl = document.getElementById('prompter-total-preview');
    const windowsEl = document.getElementById('prompter-windows-preview');
    const scenesCount = Array.isArray(p.scenes) && p.scenes.length > 0 ? p.scenes.length : (p.srtSubsCount || 0);

    if (scenesCount <= 0) {
        if (totalEl) totalEl.innerText = '0 промптов';
        if (windowsEl) windowsEl.innerText = 'Сначала выберите SRT';
        return;
    }

    p.totalPrompts = scenesCount;
    p.scenesCount = scenesCount;

    if (totalEl) totalEl.innerText = `${scenesCount} промптов`;
    if (windowsEl) windowsEl.innerText = `${scenesCount} сцен из SRT`;
};


function formatDuration(sec) {
    if (!sec) return '0 сек';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) return `${h}ч ${m}м ${s}с`;
    return `${m}м ${s}с`;
}

window.prompterBrowseDocx = async function () {
    const path = await eel.prompter_browse_docx()();
    if (path) {
        document.getElementById('prompter-docx-path').value = path;
        prompterSaveToTab();

        const applyAll = document.getElementById('prompter-docx-all').checked;
        if (applyAll) {
            Object.keys(tabs).forEach(id => {
                if (tabs[id].category === 'video') {
                    if (!tabs[id].prompter) tabs[id].prompter = {};
                    tabs[id].prompter.docxPath = path;
                }
            });
            if (typeof add_log_entry === 'function') {
                add_log_entry(activeTabId, "📄 Системный промпт применён ко всем проектам", "info");
            }
        }
    }
};

window.prompterBrowseSrt = async function () {
    const path = await eel.prompter_browse_srt()();
    if (path) {
        const p = _getPrompter();
        if (!p) return;

        p.srtPath = path;

        const elDir = document.getElementById('prompter-save-dir');
        if (elDir && !elDir.value) {
            const dir = path.substring(0, Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\')));
            elDir.value = dir;
            p.saveDir = dir;
        }

        try {
            const scenesRes = await eel.prompter_parse_srt_scenes(path)();
            if (scenesRes && scenesRes.success) {
                p.srtSubsCount = scenesRes.total_scenes || 0;
                p.srtDurationSec = scenesRes.duration_sec || 0;
                p.srtPreview = `Длительность: ${formatDuration(scenesRes.duration_sec)}`;
                p.scenes = (scenesRes.scenes || []).map(scene => ({
                    ...scene,
                    prompt: '',
                    status: 'ОЖИДАНИЕ',
                    statusClass: 'text-white/30',
                    error: ''
                }));
                p.failedCount = 0;
                p.errorBanner = '';
                prompterRecalcTotal();
            }
        } catch (e) {
            console.error("Error reading SRT preview:", e);
        }

        prompterSyncFromTab();
    }
};

window.prompterBrowseSaveDir = async function () {
    const res = await eel.prompter_browse_save_folder()();
    if (!res || !res.success || !res.path) return;

    const p = _getPrompter();
    if (!p) return;

    const dirEl = document.getElementById('prompter-save-dir');
    if (dirEl) dirEl.value = res.path;
    p.saveDir = res.path;

    const chk = document.getElementById('prompter-output-all');
    if (chk && chk.checked) {
        Object.keys(tabs).forEach(id => {
            if (tabs[id].category === 'video') {
                if (!tabs[id].prompter) tabs[id].prompter = {};
                tabs[id].prompter.saveDir = res.path;
            }
        });
        if (typeof add_log_entry === 'function') {
            add_log_entry(activeTabId, "📁 Папка сохранения применена ко всем проектам", "info");
        }
    }

    if (res.srt_file) {
        const srtEl = document.getElementById('prompter-srt-path');
        if (srtEl) srtEl.value = res.srt_file;
        p.srtPath = res.srt_file;

        try {
            const scenesRes = await eel.prompter_parse_srt_scenes(res.srt_file)();
            if (scenesRes && scenesRes.success) {
                p.srtSubsCount = scenesRes.total_scenes || 0;
                p.srtDurationSec = scenesRes.duration_sec || 0;
                p.srtPreview = `Длительность: ${formatDuration(scenesRes.duration_sec)}`;
                p.scenes = (scenesRes.scenes || []).map(scene => ({
                    ...scene,
                    prompt: '',
                    status: 'ОЖИДАНИЕ',
                    statusClass: 'text-white/30',
                    error: ''
                }));
                p.failedCount = 0;
                p.errorBanner = '';
                prompterRecalcTotal();
            }
        } catch (e) {
            console.error("Error reading SRT preview:", e);
        }
        prompterSyncFromTab();
    } else {
        prompterSaveToTab();
        if (typeof alert === 'function' && alert.toString().includes('custom')) {
            alert("В выбранной папке не найдено .srt файлов. Выберите SRT вручную.", "warning");
        } else {
            window.alert("В выбранной папке не найдено .srt файлов.\n\nВыберите SRT вручную через кнопку «Выбрать SRT».");
        }
    }
};

window.prompterLoadSrtFolder = async function () {
    const folder = await eel.select_folder()();
    if (!folder) return;

    let files = await eel.prompter_scan_srt_folder(folder)();
    if (!files || files.length === 0) {
        return alert("В выбранной папке не найдено .srt файлов!", "warning");
    }

    files.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));

    const outAllCb = document.getElementById('prompter-output-all');
    const isOutputAll = outAllCb ? outAllCb.checked : false;

    const currentP = _getPrompter();
    const baseApiKey = currentP ? currentP.apiKey : '';
    const baseProvider = currentP ? (currentP.provider || 'deepseek') : 'deepseek';
    const baseModel = currentP ? (currentP.model || '') : '';
    const baseDocx = currentP ? currentP.docxPath : '';
    const baseSaveDir = currentP ? currentP.saveDir : '';
    const baseThreads = currentP ? prompterNormalizeThreads(currentP.threads) : 3;
    const basePauseEvery = currentP ? prompterNormalizePauseEvery(currentP.pauseEvery) : 100;
    const basePauseSeconds = currentP ? prompterNormalizePauseSeconds(currentP.pauseSeconds) : 5;
    const baseAiPool = currentP ? prompterNormalizeAiPool(currentP.aiPool) : [];

    for (let i = 0; i < files.length; i++) {
        const srtFile = files[i];
        const fileName = srtFile.split(/[\\/]/).pop();
        const fileDir = srtFile.substring(0, Math.max(srtFile.lastIndexOf('/'), srtFile.lastIndexOf('\\')));

        let tabIdToUse;
        if (i === 0 && currentP && !currentP.srtPath) {
            tabIdToUse = activeTabId;
            tabs[activeTabId].name = fileName;
        } else {
            tabIdToUse = createTab(null, fileName, 'video');
        }

        if (!tabs[tabIdToUse].prompter) {
            tabs[tabIdToUse].prompter = {
                apiKey: baseApiKey, provider: baseProvider, model: baseModel, docxPath: baseDocx, srtPath: srtFile,
                saveDir: (isOutputAll && baseSaveDir) ? baseSaveDir : fileDir,
                srtPreview: '', srtSubsCount: 0, srtDurationSec: 0,
                totalPrompts: 0, scenesCount: 0,
                scenes: [], resultFilePath: '', failedCount: 0, errorBanner: '', isGenerating: false, status: 'Ожидание...',
                threads: baseThreads,
                pauseEvery: basePauseEvery,
                pauseSeconds: basePauseSeconds,
                aiPool: baseAiPool.map(worker => ({ ...worker }))
            };
        } else {
            tabs[tabIdToUse].prompter.srtPath = srtFile;
            tabs[tabIdToUse].prompter.saveDir = (isOutputAll && baseSaveDir) ? baseSaveDir : fileDir;
            tabs[tabIdToUse].prompter.threads = baseThreads;
            tabs[tabIdToUse].prompter.pauseEvery = basePauseEvery;
            tabs[tabIdToUse].prompter.pauseSeconds = basePauseSeconds;
            tabs[tabIdToUse].prompter.aiPool = baseAiPool.map(worker => ({ ...worker }));
        }

        try {
            const scenesRes = await eel.prompter_parse_srt_scenes(srtFile)();
            if (scenesRes && scenesRes.success) {
                tabs[tabIdToUse].prompter.srtSubsCount = scenesRes.total_scenes;
                tabs[tabIdToUse].prompter.srtDurationSec = scenesRes.duration_sec || 0;
                tabs[tabIdToUse].prompter.srtPreview = `Длительность: ${formatDuration(scenesRes.duration_sec)}`;
                tabs[tabIdToUse].prompter.scenes = (scenesRes.scenes || []).map(scene => ({
                    ...scene,
                    prompt: '',
                    status: 'ОЖИДАНИЕ',
                    statusClass: 'text-white/30',
                    error: ''
                }));
            }
        } catch (e) { console.error("Parse error for", srtFile, e); }
    }

    renderTabs();
    prompterSyncFromTab();
    alert(`Загружено ${files.length} SRT файлов. Созданы вкладки.`, "success");
};

window.startPrompterGeneration = function () {
    prompterSaveToTab();
    const p = _getPrompter();
    const apiKey = document.getElementById('prompter-api-key').value.trim();

    if (!apiKey) return alert("Введите API ключ выбранного AI-провайдера!", "error");
    if (!p.srtPath) return alert("Выберите SRT файл!", "warning");
    if (!p.scenes || p.scenes.length === 0) return alert("В SRT не найдены сцены!", "warning");

    p.isGenerating = true;
    p.isStopping = false;
    p.wasStopped = false;
    p.progressText = `0/${p.scenes.length}`;
    p.progressPercent = 0;
    p.failedCount = 0;
    p.errorBanner = '';
    p.status = '<span class="text-yellow-400">Генерация...</span>';
    prompterSyncFromTab();

    eel.generate_stock_prompts(
        activeTabId,
        apiKey,
        p.srtPath,
        p.docxPath || '',
        p.saveDir || '',
        [],
        p.provider || 'deepseek',
        p.model || '',
        [],
        p.scenes || [],
        prompterNormalizeThreads(p.threads),
        prompterNormalizePauseEvery(p.pauseEvery),
        prompterNormalizePauseSeconds(p.pauseSeconds),
        prompterNormalizeAiPool(p.aiPool)
    )();
};

window.stopPrompterGeneration = async function () {
    const p = _getPrompter();
    if (!p || !p.isGenerating) return;

    p.isStopping = true;
    p.status = '<span class="text-red-300">Остановка генерации...</span>';
    prompterSyncFromTab();

    try {
        await eel.prompter_stop_generation(activeTabId)();
    } catch (e) {
        p.isStopping = false;
        prompterSyncFromTab();
        if (typeof alert === 'function') alert("Не удалось отправить команду остановки: " + e, "error");
    }
};

eel.expose(prompter_set_scenes);
function prompter_set_scenes(tab_id, scenes) {
    if (!tabs[tab_id] || !tabs[tab_id].prompter) return;
    const p = tabs[tab_id].prompter;
    const existingPrompts = Array.isArray(p.scenes) ? p.scenes.map(scene => scene.prompt || '') : [];
    p.scenes = (Array.isArray(scenes) ? scenes : []).map((scene, idx) => ({
        ...scene,
        prompt: scene.prompt || existingPrompts[idx] || '',
        status: scene.status || 'ОЖИДАНИЕ',
        statusClass: scene.statusClass || 'text-white/30',
        error: scene.error || ''
    }));
    p.srtSubsCount = p.scenes.length;
    p.scenesCount = p.scenes.length;
    prompterRecalcTotal();
    if (activeTabId === tab_id) prompterSyncFromTab();
}

eel.expose(prompter_update_scene);
function prompter_update_scene(tab_id, idx, status, text, colorClass) {
    if (!tabs[tab_id] || !tabs[tab_id].prompter) return;
    const p = tabs[tab_id].prompter;
    if (!p.scenes[idx]) return;

    p.scenes[idx].status = status;
    if (colorClass) p.scenes[idx].statusClass = colorClass;

    if (status === 'ГОТОВО') {
        p.scenes[idx].prompt = text || '';
        p.scenes[idx].error = '';
    } else if (status === 'ОШИБКА') {
        p.scenes[idx].error = text || 'Ошибка генерации';
    }

    if (activeTabId === tab_id) {
        const sEl = document.getElementById(`prompter-scene-status-${idx}`);
        const tEl = document.getElementById(`prompter-scene-prompt-${idx}`);
        if (sEl) {
            sEl.innerText = status;
            if (colorClass) sEl.className = `text-[10px] uppercase font-bold ${colorClass}`;
        }
        if (tEl && status === 'ГОТОВО') tEl.value = text || '';
        prompterSyncFromTab();
    }
}

eel.expose(prompter_update_status);
function prompter_update_status(tab_id, msg, colorClass) {
    if (tabs[tab_id] && tabs[tab_id].prompter) {
        tabs[tab_id].prompter.status = `<span class="${colorClass}">${msg}</span>`;

        const match = msg.match(/Обработано: (\d+)\/(\d+)/);
        if (match) {
            const current = parseInt(match[1]);
            const total = parseInt(match[2]);
            tabs[tab_id].prompter.progressText = `${current}/${total}`;
            tabs[tab_id].prompter.progressPercent = total > 0 ? Math.round((current / total) * 100) : 0;
        }

        if (activeTabId === tab_id) {
            const s = document.getElementById('prompter-status');
            if (s) s.innerHTML = tabs[tab_id].prompter.status;
            const logStatus = document.getElementById('prompter-log-status');
            const logPercent = document.getElementById('prompter-log-percent');
            const logFill = document.getElementById('prompter-log-progress-fill');
            if (logStatus) logStatus.innerHTML = tabs[tab_id].prompter.status;
            if (logPercent) logPercent.textContent = `${tabs[tab_id].prompter.progressPercent || 0}%`;
            if (logFill) logFill.style.width = `${tabs[tab_id].prompter.progressPercent || 0}%`;
            const pFill = document.getElementById('prompter-progress-fill');
            const pText = document.getElementById('prompter-progress-text');
            if (pFill) pFill.style.width = tabs[tab_id].prompter.progressPercent + '%';
            if (pText) pText.innerText = tabs[tab_id].prompter.progressText;
        }
    }
}

eel.expose(prompter_done);
function prompter_done(tab_id, success, resultText, errorMsg, resultFilePath, failedCount = 0, stopped = false) {
    if (!tabs[tab_id] || !tabs[tab_id].prompter) return;
    const p = tabs[tab_id].prompter;

    p.isGenerating = false;
    p.isStopping = false;
    p.wasStopped = !!stopped;
    p.failedCount = failedCount || 0;

    if (stopped) {
        p.resultFilePath = resultFilePath || '';
        p.status = '<span class="text-red-300 font-bold">Генерация остановлена</span>';
        p.errorBanner = 'Генерация остановлена. Уже завершённые промпты остались в карточках, новые API-запросы не запускаются.';
        if (!window.prompterBatchRunning && typeof alert === 'function') alert("Генерация промптов остановлена.", "warning");
        if (activeTabId === tab_id) prompterSyncFromTab();
        return;
    }

    if (success) {
        p.resultFilePath = resultFilePath;
        p.errorBanner = p.failedCount > 0 ? `Ошибка: не сгенерировалось ${p.failedCount} промптов.` : '';

        if (resultFilePath) {
            const safePath = resultFilePath.replace(/\\/g, '/');
            p.status = `<span class="text-green-400 font-bold flex items-center gap-2">
                Успешно сгенерировано!
                <button onclick="eel.open_folder('${tab_id}', '${safePath}')" class="bg-white/10 hover:bg-white/20 text-white text-[10px] px-2 py-1 rounded transition-colors flex items-center gap-1 shadow-sm border border-white/10">
                    <span class="material-symbols-outlined !text-[14px]">folder_open</span> Открыть папку
                </button>
            </span>`;
            if (!window.prompterBatchRunning && typeof alert === 'function' && alert.toString().includes('custom')) {
                const suffix = p.failedCount > 0 ? `\n\nОшибок: ${p.failedCount}` : '';
                alert(`✅ Промпты успешно сгенерированы!\n\nФайл сохранён по пути:\n${resultFilePath}${suffix}`, p.failedCount > 0 ? "warning" : "success");
            }
        } else {
            p.status = `<span class="text-red-400 font-bold">Сгенерировано (Ошибка сохранения)</span>`;
            if (!window.prompterBatchRunning && typeof alert === 'function') alert("Промпты сгенерированы, но Питон не смог сохранить .txt файл! Проверь права доступа к папке.", "error");
        }
    } else {
        p.status = `<span class="text-red-400 font-bold">Ошибка</span>`;
        p.errorBanner = errorMsg || '';
        if (!window.prompterBatchRunning && typeof alert === 'function') alert("Ошибка генерации: " + errorMsg, "error");
    }

    if (activeTabId === tab_id) prompterSyncFromTab();
}

window.sendPromptsToDownloader = function () {
    prompterSaveToTab();
    prompterSaveScenesToTab();

    let allPrompts = [];
    let projectsCount = 0;

    Object.keys(tabs).forEach(id => {
        const t = tabs[id];
        if (t.category === 'video' && t.prompter && t.prompter.scenes && t.prompter.scenes.length > 0) {
            const projectText = t.prompter.scenes.map(scene => scene.prompt).filter(txt => txt && txt.trim() !== '').join('\n');
            if (projectText) {
                allPrompts.push(projectText);
                projectsCount++;
            }
        }
    });

    const finalText = allPrompts.join('\n');

    if (!finalText.trim()) {
        return alert("Нет сгенерированных промптов ни в одном проекте!", "warning");
    }

    const menuItem = document.getElementById('menu-item-download');
    if (menuItem) showPage('page-download', menuItem);

    const downloadInput = document.getElementById('prompt-input');
    const downloadTab = tabs[activeTabId];
    if (downloadInput) {
        if (downloadInput.value.trim() !== "") {
            downloadInput.value += "\n" + finalText;
        } else {
            downloadInput.value = finalText;
        }
    }

    if (downloadTab && Array.isArray(downloadTab.queue)) {
        finalText.split('\n').map(line => line.trim()).filter(Boolean).forEach(prompt => {
            downloadTab.queue.push({ prompt, status: 'Pending', progress: 0, path: '' });
        });
        if (downloadInput) downloadInput.value = '';
        if (downloadTab.inputs) downloadTab.inputs.prompt = '';
        if (typeof renderQueue === 'function') renderQueue();
        if (typeof updateButtonUI === 'function') updateButtonUI();
    }

    if (typeof saveCurrentTabToState === 'function') saveCurrentTabToState();
    alert(`Промпты со всех проектов (${projectsCount} шт.) успешно перенесены в Загрузчик и добавлены в очередь!`, "success");
};

// === БАТЧ-ЗАПУСК ГЕНЕРАЦИИ ===
window.prompterBatchRunning = false;

window.startPrompterGenerationAll = async function () {
    prompterSaveToTab();

    const readyTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        if (t.category !== 'video' || !t.prompter) return false;
        return t.prompter.srtPath && t.prompter.apiKey && !t.prompter.isGenerating;
    });

    if (readyTabs.length === 0) return alert("Нет проектов с выбранным SRT файлом для генерации!", "warning");

    const btnAll = document.getElementById('btn-generate-prompts-all');
    const btnSingle = document.getElementById('btn-generate-prompts');

    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-base">sync</span> Запуск...';
    }
    if (btnSingle) btnSingle.disabled = true;

    window.prompterBatchRunning = true;
    let successCount = 0;

    for (let i = 0; i < readyTabs.length; i++) {
        let tabId = readyTabs[i];
        const p = tabs[tabId].prompter;

        if (typeof add_log_entry === 'function') {
            add_log_entry(tabId, `🚀 Запуск генерации (${i + 1}/${readyTabs.length}): ${tabs[tabId].name}`, "info");
        }

        p.isGenerating = true;
        p.isStopping = false;
        p.wasStopped = false;
        p.progressText = `0/${(p.scenes || []).length}`;
        p.progressPercent = 0;
        p.failedCount = 0;
        p.errorBanner = '';
        p.status = '<span class="text-yellow-400">Генерация...</span>';
        if (activeTabId === tabId) prompterSyncFromTab();

        eel.generate_stock_prompts(
            tabId,
            p.apiKey,
            p.srtPath,
            p.docxPath || '',
            p.saveDir || '',
            [],
            p.provider || 'deepseek',
            p.model || '',
            [],
            p.scenes || [],
            prompterNormalizeThreads(p.threads),
            prompterNormalizePauseEvery(p.pauseEvery),
            prompterNormalizePauseSeconds(p.pauseSeconds),
            prompterNormalizeAiPool(p.aiPool)
        )();

        // Ожидаем завершения генерации для вкладки
        while (tabs[tabId] && tabs[tabId].prompter && tabs[tabId].prompter.isGenerating) {
            await new Promise(r => setTimeout(r, 1000));
        }
        if (tabs[tabId] && tabs[tabId].prompter && tabs[tabId].prompter.wasStopped) {
            break;
        }
        successCount++;
    }

    window.prompterBatchRunning = false;

    if (btnAll) {
        btnAll.disabled = false;
        btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">done_all</span> ВСЕ Проекты';
    }
    if (btnSingle) btnSingle.disabled = false;

    if (typeof add_log_entry === 'function') {
        add_log_entry(activeTabId, `✅ Пакетная генерация завершена!`, "success");
    }

    alert(`✅ Пакетная генерация завершена!\nОбработано проектов: ${successCount}.`, "success");
};

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function prompterGetFailedSceneIndices() {
    const p = _getPrompter();
    if (!p || !Array.isArray(p.scenes)) return [];
    return p.scenes
        .map((scene, index) => ({ scene, index }))
        .filter(({ scene }) => (scene.status || '').toUpperCase() === 'ОШИБКА')
        .map(({ index }) => index);
}

window.prompterRegenerateFailed = function () {
    const p = _getPrompter();
    if (!p) return;
    const failedIndices = prompterGetFailedSceneIndices();
    if (failedIndices.length === 0) return alert("Ошибочных сцен нет.", "info");
    prompterStartGenerationForIndices(failedIndices);
};

window.prompterRegenerateScene = function (sceneIndex) {
    prompterStartGenerationForIndices([sceneIndex]);
};

function prompterStartGenerationForIndices(indices) {
    prompterSaveToTab();
    prompterSaveScenesToTab();
    const p = _getPrompter();
    const apiKey = document.getElementById('prompter-api-key').value.trim();

    if (!apiKey) return alert("Введите API ключ выбранного AI-провайдера!", "error");
    if (!p.srtPath) return alert("Выберите SRT файл!", "warning");
    if (!Array.isArray(indices) || indices.length === 0) return alert("Нет сцен для перегенерации.", "warning");

    p.isGenerating = true;
    p.isStopping = false;
    p.wasStopped = false;
    p.progressText = `0/${indices.length}`;
    p.progressPercent = 0;
    p.errorBanner = '';
    p.status = '<span class="text-yellow-400">Перегенерация...</span>';
    indices.forEach(index => {
        if (p.scenes[index]) {
            p.scenes[index].status = 'ГЕНЕРАЦИЯ...';
            p.scenes[index].statusClass = 'text-yellow-400 animate-pulse';
            p.scenes[index].error = '';
        }
    });
    prompterSyncFromTab();

    eel.generate_stock_prompts(
        activeTabId,
        apiKey,
        p.srtPath,
        p.docxPath || '',
        p.saveDir || '',
        [],
        p.provider || 'deepseek',
        p.model || '',
        indices,
        p.scenes || [],
        prompterNormalizeThreads(p.threads),
        prompterNormalizePauseEvery(p.pauseEvery),
        prompterNormalizePauseSeconds(p.pauseSeconds),
        prompterNormalizeAiPool(p.aiPool)
    )();
}
