/* 
* Stocky non Stop — Voicer UI (TTS + Whisper)
* Автор: Азат | @inomix
*/ 
// === VOICER UI LOGIC (Tab Isolated) ===

let voicerUserPresets = [];

function voicerGetPresetById(presetId) {
    return voicerUserPresets.find(preset => preset.id === presetId) || null;
}

function voicerCurrentPresetPayload() {
    const v = _getVoicer();
    if (!v) return null;
    const presetName = (document.getElementById('voicer-user-preset-name')?.value || v.tts.userPresetName || '').trim();
    const engine = v.tts.engine === 'mateo' ? 'mateo' : 'standard';
    return {
        id: v.tts.voicePresetId || '',
        name: presetName,
        engine,
        standardTemplateUuid: engine === 'standard' ? (v.tts.template || '') : '',
        standardTemplateTitle: engine === 'standard' ? (document.getElementById('voicer-template-selected-text')?.textContent || '') : '',
        mateoVoiceId: engine === 'mateo' ? (v.tts.mateoVoiceId || '') : '',
        mateoVoiceLabel: engine === 'mateo' ? (document.getElementById('voicer-mateo-voice-selected-text')?.textContent || '') : ''
    };
}

function voicerRenderUserPresets() {
    const ul = document.getElementById('voicer-user-preset-options');
    const label = document.getElementById('voicer-user-preset-selected-text');
    if (!ul || !label) return;

    const currentId = (_getVoicer()?.tts?.voicePresetId) || '';
    if (!voicerUserPresets.length) {
        ul.innerHTML = '<li data-value="" onclick="voicerSelectUserPresetOption(this)" class="selected">Нет сохранённых шаблонов</li>';
        label.textContent = 'Выберите сохранённый шаблон...';
        return;
    }

    ul.innerHTML = voicerUserPresets.map(preset => `
        <li data-value="${preset.id}" onclick="voicerSelectUserPresetOption(this)" class="${preset.id === currentId ? 'selected' : ''}">
            ${preset.name} (${preset.engine === 'mateo' ? 'Mateo' : 'ElevenLabs'})
        </li>
    `).join('');

    const current = voicerGetPresetById(currentId);
    label.textContent = current ? `${current.name} (${current.engine === 'mateo' ? 'Mateo' : 'ElevenLabs'})` : 'Выберите сохранённый шаблон...';
}

async function voicerLoadUserPresets() {
    try {
        const res = await eel.voicer_get_voice_presets()();
        voicerUserPresets = res && res.success && Array.isArray(res.presets) ? res.presets : [];
        voicerRenderUserPresets();
    } catch (e) {
        console.error('Failed to load voicer presets', e);
    }
}

// Ensure state object exists for current tab
function _getVoicer() {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return null;
    let t = tabs[activeTabId];

    // 🔥 Страховка: если по какой-то причине voicer отсутствует — создаём
    // (теоретически не нужно, т.к. createTab теперь всегда создаёт voicer,
    //  но оставляем как защиту от багов в других местах кода)
    if (!t.voicer) {
        t.voicer = {
            tts: {
                apiKey: '', template: '', outFolder: '', text: '',
                autoStt: true,
                templateApplyAll: true,
                autoSttApplyAll: true,
                voicePresetId: '',
                userPresetName: '',
                logs: '', status: 'Ожидание...', progress: 0, isRunning: false
            },
            stt: {
                filePath: '', model: 'small', prompt: '', saveDir: '',
                saveDirApplyAll: false, useGlobalSaveDir: false, resultPath: '',
                logs: '', status: 'Ожидание...', progress: 0, isRunning: false
            }
        };
    }

    // 🔥 Бекап для очень старых вкладок, где этих полей могло вообще не быть
    if (t.voicer.tts.autoStt === undefined) t.voicer.tts.autoStt = true;
    if (t.voicer.tts.templateApplyAll === undefined) t.voicer.tts.templateApplyAll = true;
    if (t.voicer.tts.autoSttApplyAll === undefined) t.voicer.tts.autoSttApplyAll = true;
    if (t.voicer.tts.voicePresetId === undefined) t.voicer.tts.voicePresetId = '';
    if (t.voicer.tts.userPresetName === undefined) t.voicer.tts.userPresetName = '';
    if (t.voicer.tts.speedUp === undefined) t.voicer.tts.speedUp = 10;
    if (t.voicer.tts.speedUpApplyAll === undefined) t.voicer.tts.speedUpApplyAll = true;
    if (t.voicer.stt.saveDir === undefined) t.voicer.stt.saveDir = '';
    if (t.voicer.stt.saveDirApplyAll === undefined) t.voicer.stt.saveDirApplyAll = false;
    if (t.voicer.stt.useGlobalSaveDir === undefined) t.voicer.stt.useGlobalSaveDir = false;
    if (t.voicer.stt.resultPath === undefined) t.voicer.stt.resultPath = '';

    return t.voicer;
}

// 1. SYNC TO UI
window.voicerSyncFromTab = function () {
    const v = _getVoicer();
    if (!v) return;

    // Если у вкладки нет своего ключа — подтягиваем из глобального config.json
    if (!v.tts.apiKey) {
        eel.get_config()(function (conf) {
            if (conf && conf.elevenlabs_api_key) {
                v.tts.apiKey = conf.elevenlabs_api_key;
                const inp = document.getElementById('voicer-tts-api-key');
                if (inp && activeTabId && tabs[activeTabId] && tabs[activeTabId].voicer === v) {
                    inp.value = conf.elevenlabs_api_key;
                    // Тихо подгружаем шаблоны, раз ключ найден
                    voicerFetchTemplates(true);
                }
            }
        });
    }

    // TTS
    document.getElementById('voicer-tts-api-key').value = v.tts.apiKey || '';
    document.getElementById('voicer-tts-output').value = v.tts.outFolder || '';
    const presetNameInput = document.getElementById('voicer-user-preset-name');
    if (presetNameInput) presetNameInput.value = v.tts.userPresetName || '';
    voicerRenderUserPresets();

    document.getElementById('voicer-tts-template').value = v.tts.template || '';
    const tempVal = v.tts.template || '';
    const tempLi = document.querySelector(`#voicer-template-options li[data-value="${tempVal}"]`);
    if (tempLi) {
        document.getElementById('voicer-template-selected-text').textContent = tempLi.textContent;
        document.querySelectorAll('#voicer-template-options li').forEach(l => l.classList.remove('selected'));
        tempLi.classList.add('selected');
    } else if (tempVal === '') {
        document.getElementById('voicer-template-selected-text').textContent = "Сначала обновите шаблоны...";
    }

    document.getElementById('voicer-tts-text').value = v.tts.text || '';
    document.getElementById('voicer-tts-autostt').checked = v.tts.autoStt !== false;

    document.getElementById('voicer-tts-speed-slider').value = v.tts.speedUp !== undefined ? v.tts.speedUp : 10;
    document.getElementById('voicer-tts-speed-number').value = v.tts.speedUp !== undefined ? v.tts.speedUp : 10;

    const speedCb = document.getElementById('voicer-speed-apply-all');
    if (speedCb) speedCb.checked = v.tts.speedUpApplyAll !== false;

    // 🔥 Восстанавливаем чекбоксы "Ко всем" СТРОГО из стейта этого проекта
    // (не дефолт, а именно сохранённое значение — true или false)
    const tmplCb = document.getElementById('voicer-template-apply-all');
    const autoCb = document.getElementById('voicer-autostt-apply-all');
    if (tmplCb) {
        // Если в стейте явно false — снимаем. Если true или undefined — ставим.
        tmplCb.checked = (v.tts.templateApplyAll === false) ? false : true;
    }
    if (autoCb) {
        autoCb.checked = (v.tts.autoSttApplyAll === false) ? false : true;
    }

    document.getElementById('voicer-tts-progress-fill').style.width = `${v.tts.progress || 0}%`;
    document.getElementById('voicer-tts-progress-text').innerText = `${Math.round(v.tts.progress || 0)}%`;
    document.getElementById('voicer-tts-status').innerHTML = v.tts.status || 'Ожидание...';
    document.getElementById('voicer-tts-log').innerHTML = v.tts.logs || '';

    const ttsBtn = document.getElementById('voicer-tts-btn');
    if (v.tts.isRunning) {
        ttsBtn.innerHTML = '<span class="material-symbols-outlined !text-[16px] animate-spin">sync</span> Запуск...';
        ttsBtn.disabled = true;
    } else {
        ttsBtn.innerHTML = '<span class="material-symbols-outlined !text-[16px]">play_arrow</span> Начать этот';
        ttsBtn.disabled = false;
    }

    // STT
    document.getElementById('voicer-stt-input').value = v.stt.filePath || '';
    document.getElementById('voicer-stt-prompt').value = v.stt.prompt || '';
    document.getElementById('voicer-stt-save-dir').value = v.stt.saveDir || '';
    document.getElementById('voicer-stt-result-path').value = v.stt.resultPath || '';
    const sttSaveApplyAll = document.getElementById('voicer-stt-save-apply-all');
    if (sttSaveApplyAll) sttSaveApplyAll.checked = v.stt.saveDirApplyAll === true;
    const sttUseGlobal = document.getElementById('voicer-stt-use-global-save-dir');
    if (sttUseGlobal) sttUseGlobal.checked = v.stt.useGlobalSaveDir === true;

    document.getElementById('voicer-stt-model').value = v.stt.model || 'small';
    const modelVal = v.stt.model || 'small';
    const modelLi = document.querySelector(`#voicer-whisper-model-options li[data-value="${modelVal}"]`);
    if (modelLi) {
        document.getElementById('voicer-whisper-model-selected-text').textContent = modelLi.textContent;
        document.querySelectorAll('#voicer-whisper-model-options li').forEach(l => l.classList.remove('selected'));
        modelLi.classList.add('selected');
    }

    document.getElementById('voicer-stt-progress-fill').style.width = `${v.stt.progress || 0}%`;
    document.getElementById('voicer-stt-progress-text').innerText = `${Math.round(v.stt.progress || 0)}%`;
    document.getElementById('voicer-stt-status').innerHTML = v.stt.status || 'Ожидание...';
    document.getElementById('voicer-stt-log').innerHTML = v.stt.logs || '';

    const sttBtn = document.getElementById('voicer-stt-btn');
    if (v.stt.isRunning) {
        sttBtn.innerHTML = '<span class="material-symbols-outlined !text-[16px] animate-spin">sync</span> Запуск...';
        sttBtn.disabled = true;
    } else {
        sttBtn.innerHTML = '<span class="material-symbols-outlined !text-[16px]">play_arrow</span> Начать этот';
        sttBtn.disabled = false;
    }
};

// 2. SAVE FROM UI
window.voicerSaveToTab = function () {
    const v = _getVoicer();
    if (!v) return;

    // 🔥 СНАЧАЛА считываем все значения из UI в локальные переменные
    const newApiKey = document.getElementById('voicer-tts-api-key').value;
    const newTemplate = document.getElementById('voicer-tts-template').value;
    const newOutFolder = document.getElementById('voicer-tts-output').value;
    const newText = document.getElementById('voicer-tts-text').value;
    const newAutoStt = document.getElementById('voicer-tts-autostt').checked;
    const newUserPresetName = document.getElementById('voicer-user-preset-name')?.value || '';

    const newSpeedUp = parseInt(document.getElementById('voicer-tts-speed-number').value) || 0;
    const speedCb = document.getElementById('voicer-speed-apply-all');
    const newSpeedUpApplyAll = speedCb ? speedCb.checked : v.tts.speedUpApplyAll;

    const tmplCb = document.getElementById('voicer-template-apply-all');
    const autoCb = document.getElementById('voicer-autostt-apply-all');
    const newTemplateApplyAll = tmplCb ? tmplCb.checked : v.tts.templateApplyAll;
    const newAutoSttApplyAll = autoCb ? autoCb.checked : v.tts.autoSttApplyAll;

    // 🔥 Запоминаем СТАРЫЕ значения ДО перезаписи (для сравнения)
    const oldAutoStt = v.tts.autoStt;
    const oldTemplate = v.tts.template;
    const oldSpeedUp = v.tts.speedUp;

    // 🔥 Сохраняем всё в стейт ЭТОЙ вкладки
    v.tts.apiKey = newApiKey;
    v.tts.template = newTemplate;
    v.tts.outFolder = newOutFolder;
    v.tts.text = newText;
    v.tts.autoStt = newAutoStt;
    v.tts.userPresetName = newUserPresetName;
    v.tts.templateApplyAll = newTemplateApplyAll;
    v.tts.autoSttApplyAll = newAutoSttApplyAll;
    v.tts.speedUp = newSpeedUp;
    v.tts.speedUpApplyAll = newSpeedUpApplyAll;

    if (newSpeedUpApplyAll === true && oldSpeedUp !== newSpeedUp) {
        voicerPropagateField('speedUp', newSpeedUp);
    }

    v.stt.filePath = document.getElementById('voicer-stt-input').value;
    v.stt.model = document.getElementById('voicer-stt-model').value;
    v.stt.prompt = document.getElementById('voicer-stt-prompt').value;
    v.stt.saveDir = document.getElementById('voicer-stt-save-dir').value;
    v.stt.saveDirApplyAll = !!document.getElementById('voicer-stt-save-apply-all')?.checked;
    v.stt.useGlobalSaveDir = !!document.getElementById('voicer-stt-use-global-save-dir')?.checked;

    eel.voicer_save_api_key(v.tts.apiKey);

    // 🔥 ПРОПАГАЦИЯ — ТОЛЬКО при РЕАЛЬНОМ изменении значения и ТОЛЬКО если флаг "Ко всем" включён.
    //
    // ВАЖНО:
    //   1. Флаги (templateApplyAll, autoSttApplyAll) НИКОГДА не пропагируются — они строго локальные!
    //   2. Значения (template, autoStt) пропагируются только если новое значение отличается от старого
    //   3. Это значит: переключение вкладок, redraw UI, повторный вызов saveToTab без изменений = НЕТ пропагации

    if (newTemplateApplyAll === true && newTemplate && oldTemplate !== newTemplate) {
        voicerPropagateField('template', newTemplate);
    }
    if (v.stt.saveDirApplyAll === true) {
        voicerPropagateSttSaveDir(v.stt.saveDir, v.stt.useGlobalSaveDir);
    }

    // === БАТЧ-ЗАГРУЗКА ДЛЯ VOICER ===

    window.voicerLoadTextFolder = async function () {
        try {
            const folderRes = await eel.voicer_browse_folder()();
            if (!folderRes.success) {
                if (folderRes.error !== "Отменено") voicer_add_log_global("Ошибка: " + folderRes.error, "error");
                return;
            }
            if (!folderRes.path) return;

            voicer_add_log_global(`Сканирую папку на наличие текстовых файлов...`, "info");
            const res = await eel.voicer_scan_text_folder(folderRes.path)();

            if (!res.success) return voicer_add_log_global("Ошибка сканирования: " + res.error, "error");
            if (!res.files || res.files.length === 0) {
                return voicer_add_log_global("В выбранной папке нет .txt, .md или .docx файлов!", "warning");
            }

            voicer_add_log_global(`Найдено ${res.files.length} текстовых файлов. Создаю проекты...`, "info");

            let lastTabId = null;
            voicerSaveToTab();
            const currentVoicer = _getVoicer();

            for (let fileData of res.files) {
                const newTabId = createTab(null, fileData.filename, 'voicer');
                const newVoicer = tabs[newTabId].voicer;

                newVoicer.tts.text = fileData.text;
                newVoicer.tts.outFolder = fileData.folder;
                newVoicer.tts.customFileName = fileData.filename;

                newVoicer.tts.apiKey = currentVoicer.tts.apiKey;
                newVoicer.tts.template = currentVoicer.tts.template;
                newVoicer.tts.autoStt = currentVoicer.tts.autoStt;
                newVoicer.tts.engine = currentVoicer.tts.engine;
                newVoicer.tts.voicePresetId = currentVoicer.tts.voicePresetId || '';
                newVoicer.tts.userPresetName = currentVoicer.tts.userPresetName || '';
                newVoicer.tts.mateoVoiceId = currentVoicer.tts.mateoVoiceId || '';

                lastTabId = newTabId;
            }

            if (lastTabId) {
                switchTab(lastTabId);
                renderTabs();
            }

            voicer_add_log_global(`✅ Создано ${res.files.length} проектов из папки`, "success");
        } catch (e) {
            console.error(e);
            voicer_add_log_global("Критическая ошибка: " + e, "error");
        }
    };

    window.voicerLoadAudioFolder = async function () {
        try {
            const folderRes = await eel.voicer_browse_folder()();
            if (!folderRes.success) {
                if (folderRes.error !== "Отменено") voicer_add_log_global("Ошибка: " + folderRes.error, "error");
                return;
            }
            if (!folderRes.path) return;

            voicer_add_log_global(`Сканирую папку на наличие медиафайлов...`, "info");
            const res = await eel.voicer_scan_audio_folder(folderRes.path)();

            if (!res.success) return voicer_add_log_global("Ошибка сканирования: " + res.error, "error");
            if (!res.files || res.files.length === 0) {
                return voicer_add_log_global("В выбранной папке нет медиафайлов!", "warning");
            }

            voicer_add_log_global(`Найдено ${res.files.length} медиафайлов. Создаю проекты...`, "info");

            let lastTabId = null;
            voicerSaveToTab();
            const currentVoicer = _getVoicer();

            for (let fileData of res.files) {
                const newTabId = createTab(null, fileData.filename, 'voicer');
                const newVoicer = tabs[newTabId].voicer;

                newVoicer.stt.filePath = fileData.path;
                if (fileData.prompt) newVoicer.stt.prompt = fileData.prompt;

                newVoicer.stt.model = currentVoicer.stt.model;
                newVoicer.stt.saveDir = currentVoicer.stt.saveDir || fileData.path.substring(0, Math.max(fileData.path.lastIndexOf('/'), fileData.path.lastIndexOf('\\')));
                newVoicer.stt.saveDirApplyAll = currentVoicer.stt.saveDirApplyAll;
                newVoicer.stt.useGlobalSaveDir = currentVoicer.stt.useGlobalSaveDir;

                lastTabId = newTabId;
            }

            if (lastTabId) {
                switchTab(lastTabId);
                renderTabs();
                // Automatically switch subtab to STT so user sees what was loaded
                if (typeof switchVoicerSubTab === 'function') switchVoicerSubTab('transcription');
            }

            voicer_add_log_global(`✅ Создано ${res.files.length} проектов из папки`, "success");
        } catch (e) {
            console.error(e);
            voicer_add_log_global("Критическая ошибка: " + e, "error");
        }
    };

    // === БАТЧ-ЗАПУСК ===

    window.voicerTtsStartAll = async function () {
        voicerSaveToTab();
        const ttsTabs = Object.keys(tabs).filter(id => {
            const t = tabs[id];
            return t.category === 'voicer' && t.voicer && t.voicer.tts.text.trim() !== '' && !t.voicer.tts.isRunning;
        });

        if (ttsTabs.length === 0) return alert("Нет готовых проектов для синтеза речи!");

        const btnAll = document.getElementById('voicer-tts-btn-all');
        if (btnAll) {
            btnAll.disabled = true;
            btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-[16px]">sync</span> Запуск...';
        }

        voicer_add_log_global(`🚀 Запуск ${ttsTabs.length} задач синтеза речи...`, "success");

        for (let tabId of ttsTabs) {
            const v = tabs[tabId].voicer;
            if (!v.tts.apiKey || !v.tts.template || !v.tts.outFolder) {
                voicer_add_log_global(`[${tabs[tabId].name}] Пропуск: не заполнены настройки TTS`, "error");
                continue;
            }

            v.tts.isRunning = true;
            v.tts.progress = 0;
            v.tts.logs = '';
            if (activeTabId === tabId) voicerSyncFromTab();

            eel.voicer_tts_start(
                tabId, v.tts.apiKey, v.tts.text, v.tts.template,
                v.tts.outFolder, v.tts.autoStt, v.stt.model, "ru", v.tts.customFileName || "", v.tts.speedUp || 0
            )();
            await new Promise(r => setTimeout(r, 500)); // Задержка между запросами
        }

        if (btnAll) {
            btnAll.disabled = false;
            btnAll.innerHTML = '<span class="material-symbols-outlined !text-[16px]">rocket_launch</span> Начать все';
        }
    };

    window.voicerSttStartAll = async function () {
        voicerSaveToTab();
        const sttTabs = Object.keys(tabs).filter(id => {
            const t = tabs[id];
            return t.category === 'voicer' && t.voicer && t.voicer.stt.filePath !== '' && !t.voicer.stt.isRunning;
        });

        if (sttTabs.length === 0) return alert("Нет готовых проектов для транскрибации!");

        const btnAll = document.getElementById('voicer-stt-btn-all');
        if (btnAll) {
            btnAll.disabled = true;
            btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-[16px]">sync</span> Запуск...';
        }

        voicer_add_log_global(`🚀 Запуск ${sttTabs.length} задач транскрибации...`, "success");

        for (let tabId of sttTabs) {
            const v = tabs[tabId].voicer;
            v.stt.isRunning = true;
            v.stt.progress = 0;
            v.stt.logs = '';
            if (activeTabId === tabId) voicerSyncFromTab();

            eel.voicer_whisper_start(
                tabId, v.stt.filePath, v.stt.model, "ru", v.stt.prompt, v.stt.saveDir || ""
            )();
            await new Promise(r => setTimeout(r, 500)); // Задержка для инициализации потока
        }

        if (btnAll) {
            btnAll.disabled = false;
            btnAll.innerHTML = '<span class="material-symbols-outlined !text-[16px]">rocket_launch</span> Начать все';
        }
    };
    if (newAutoSttApplyAll === true && oldAutoStt !== newAutoStt) {
        voicerPropagateField('autoStt', newAutoStt);
    }
};

// 3. FILE/FOLDER DIALOGS
window.voicerTtsBrowseFolder = async function () {
    const res = await eel.voicer_browse_folder()();
    if (res.success) {
        document.getElementById('voicer-tts-output').value = res.path;
        voicerSaveToTab();
    }
};

window.voicerSttBrowseFile = async function () {
    const res = await eel.voicer_browse_file("media")();
    if (res.success) {
        document.getElementById('voicer-stt-input').value = res.path;
        const saveDirEl = document.getElementById('voicer-stt-save-dir');
        if (saveDirEl && !saveDirEl.value) {
            saveDirEl.value = res.path.substring(0, Math.max(res.path.lastIndexOf('/'), res.path.lastIndexOf('\\')));
        }
        voicerSaveToTab();

        // Auto-load text prompt if exists (like Whisperion does)
        const txtPath = res.path.replace(/\.[^/.]+$/, "") + ".txt";
        // Check if we can read it to populate prompt
    }
};

window.voicerSttBrowseSaveDir = async function () {
    const res = await eel.voicer_browse_folder()();
    if (!res.success) return;
    document.getElementById('voicer-stt-save-dir').value = res.path || '';
    voicerSaveToTab();
    const v = _getVoicer();
    if (v && v.stt.useGlobalSaveDir) {
        await eel.voicer_save_srt_default_dir(v.stt.saveDir)();
    }
};

window.voicerToggleGlobalSrtSaveDir = async function () {
    const v = _getVoicer();
    if (!v) return;
    voicerSaveToTab();
    await eel.voicer_save_srt_default_dir(v.stt.useGlobalSaveDir ? v.stt.saveDir : "")();
    voicer_add_log_global(v.stt.useGlobalSaveDir ? "📌 Папка SRT сохранена как общая по умолчанию." : "📌 Общая папка SRT по умолчанию отключена.", "info");
};

window.voicerToggleSttSaveApplyAll = function () {
    voicerSaveToTab();
    const v = _getVoicer();
    if (v && v.stt.saveDirApplyAll) {
        voicerPropagateSttSaveDir(v.stt.saveDir, v.stt.useGlobalSaveDir);
        voicer_add_log_global("📁 Папка сохранения SRT применена ко всем Voicer-проектам.", "info");
    }
};

function voicerPropagateSttSaveDir(saveDir, useGlobalSaveDir) {
    Object.keys(tabs || {}).forEach(id => {
        if (id === activeTabId) return;
        const tab = tabs[id];
        if (!tab || tab.category !== 'voicer' || !tab.voicer) return;
        tab.voicer.stt.saveDir = saveDir || '';
        tab.voicer.stt.useGlobalSaveDir = !!useGlobalSaveDir;
        if (tab.voicer.stt.saveDirApplyAll === undefined) tab.voicer.stt.saveDirApplyAll = false;
    });
}

// === CUSTOM DROPDOWN LOGIC ===
window.voicerToggleSelect = function (selectId) {
    document.querySelectorAll('.custom-select.open').forEach(s => {
        if (s.id !== selectId) {
            s.classList.remove('open');
            s.querySelector('.select-options').classList.add('hidden');
        }
    });
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const opts = sel.querySelector('.select-options');
    sel.classList.toggle('open');
    opts.classList.toggle('hidden');
};

window.voicerSelectOption = function (li) {
    const sel = li.closest('.custom-select');
    if (!sel) return;
    const value = li.getAttribute('data-value');
    const label = li.textContent;

    document.getElementById('voicer-template-selected-text').textContent = label;
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');

    const hidden = document.getElementById('voicer-tts-template');
    if (hidden) {
        hidden.value = value;
        voicerSaveToTab();
    }
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');
};

window.voicerSelectUserPresetOption = function (li) {
    const presetId = li.getAttribute('data-value') || '';
    const v = _getVoicer();
    if (!v) return;
    v.tts.voicePresetId = presetId;
    const preset = voicerGetPresetById(presetId);
    if (preset) {
        v.tts.userPresetName = preset.name;
        const input = document.getElementById('voicer-user-preset-name');
        if (input) input.value = preset.name;
    }
    voicerRenderUserPresets();
    const sel = li.closest('.custom-select');
    if (sel) {
        sel.classList.remove('open');
        sel.querySelector('.select-options')?.classList.add('hidden');
    }
    voicerSaveToTab();
};

window.voicerApplySelectedVoicePreset = function () {
    const v = _getVoicer();
    if (!v) return;
    const preset = voicerGetPresetById(v.tts.voicePresetId);
    if (!preset) return alert("Сначала выберите сохранённый шаблон");

    v.tts.engine = preset.engine;
    v.tts.userPresetName = preset.name;
    if (preset.engine === 'mateo') {
        v.tts.mateoVoiceId = preset.mateoVoiceId || '';
        const hidden = document.getElementById('voicer-mateo-voice-id');
        if (hidden) hidden.value = v.tts.mateoVoiceId;
    } else {
        v.tts.template = preset.standardTemplateUuid || '';
        const hidden = document.getElementById('voicer-tts-template');
        if (hidden) hidden.value = v.tts.template;
    }

    voicerSyncFromTab();
    voicerSaveToTab();
    voicer_add_log_global(`✓ Шаблон '${preset.name}' применён к проекту`, "success");
};

window.voicerSaveCurrentVoicePreset = async function () {
    const payload = voicerCurrentPresetPayload();
    if (!payload) return;
    if (!payload.name) return alert("Введите название шаблона");
    if (payload.engine === 'standard' && !payload.standardTemplateUuid) {
        return alert("Для ElevenLabs API сначала выберите голосовой шаблон");
    }
    if (payload.engine === 'mateo' && !payload.mateoVoiceId) {
        return alert("Для Voicer Mateo сначала выберите Voice ID");
    }

    const res = await eel.voicer_save_voice_preset(payload)();
    if (!res || !res.success) {
        return alert(res?.error || "Не удалось сохранить шаблон");
    }

    voicerUserPresets = Array.isArray(res.presets) ? res.presets : voicerUserPresets;
    const v = _getVoicer();
    if (v) {
        v.tts.voicePresetId = res.preset.id;
        v.tts.userPresetName = res.preset.name;
    }
    voicerRenderUserPresets();
    voicerSaveToTab();
    voicer_add_log_global(`✓ Шаблон '${res.preset.name}' сохранён`, "success");
};

window.voicerDeleteSelectedVoicePreset = async function () {
    const v = _getVoicer();
    if (!v || !v.tts.voicePresetId) return alert("Сначала выберите шаблон для удаления");
    const preset = voicerGetPresetById(v.tts.voicePresetId);
    const res = await eel.voicer_delete_voice_preset(v.tts.voicePresetId)();
    if (!res || !res.success) {
        return alert(res?.error || "Не удалось удалить шаблон");
    }
    voicerUserPresets = Array.isArray(res.presets) ? res.presets : [];
    v.tts.voicePresetId = '';
    voicerRenderUserPresets();
    voicerSaveToTab();
    voicer_add_log_global(`✓ Шаблон '${preset?.name || ''}' удалён`, "warning");
};

window.voicerSelectWhisperOption = function (li) {
    const sel = li.closest('.custom-select');
    if (!sel) return;
    const value = li.getAttribute('data-value');
    const label = li.textContent;

    document.getElementById('voicer-whisper-model-selected-text').textContent = label;
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');

    const hidden = document.getElementById('voicer-stt-model');
    if (hidden) {
        hidden.value = value;
        voicerSaveToTab();
    }
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');
};

document.addEventListener('click', function (e) {
    if (!e.target.closest('#voicer-template-select') && !e.target.closest('#voicer-whisper-model-select') && !e.target.closest('#voicer-user-preset-select')) {
        document.querySelectorAll('#voicer-template-select.open, #voicer-whisper-model-select.open, #voicer-user-preset-select.open').forEach(sel => {
            sel.classList.remove('open');
            sel.querySelector('.select-options').classList.add('hidden');
        });
    }
});

// 4. TTS API
window.voicerFetchTemplates = async function (isAuto = false) {
    const ul = document.getElementById('voicer-template-options');
    const hidden = document.getElementById('voicer-tts-template');
    const label = document.getElementById('voicer-template-selected-text');

    ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Загрузка...</li>';
    label.textContent = "Загрузка...";

    voicerSaveToTab();
    const v = _getVoicer();
    const key = (v && v.tts.apiKey) ? v.tts.apiKey.trim() :
        document.getElementById('voicer-tts-api-key').value.trim();

    if (!key) {
        if (!isAuto) alert("Введите API ключ ElevenLabs!");
        ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Сначала обновите шаблоны...</li>';
        label.textContent = "Сначала обновите шаблоны...";
        return;
    }

    // Используем единую функцию валидации
    await voicerValidateAndFetch(key);
};

window.voicerTtsStart = async function () {
    voicerSaveToTab();
    const v = _getVoicer();

    if (!v.tts.apiKey) return alert("Введите API ключ!");
    if (!v.tts.template) return alert("Выберите голосовой шаблон!");
    if (!v.tts.outFolder) return alert("Выберите папку для сохранения!");
    if (!v.tts.text.trim()) return alert("Введите текст для озвучки!");

    v.tts.isRunning = true;
    v.tts.progress = 0;
    v.tts.logs = '';
    voicerSyncFromTab();

    // 🔥 Передаем customFileName последним аргументом
    await eel.voicer_tts_start(
        activeTabId, v.tts.apiKey, v.tts.text, v.tts.template,
        v.tts.outFolder, v.tts.autoStt, v.stt.model, "ru", v.tts.customFileName || "", v.tts.speedUp || 0
    )();
};

// 5. WHISPER API
window.voicerSttStart = async function () {
    voicerSaveToTab();
    const v = _getVoicer();

    if (!v.stt.filePath) return alert("Выберите медиафайл!");

    v.stt.isRunning = true;
    v.stt.progress = 0;
    v.stt.logs = '';
    voicerSyncFromTab();

    await eel.voicer_whisper_start(
        activeTabId, v.stt.filePath, v.stt.model, "ru", v.stt.prompt, v.stt.saveDir || ""
    )();
};

// 6. EEL CALLBACKS
eel.expose(voicer_add_log);
function voicer_add_log(tab_id, msg, log_type) {
    if (!tabs[tab_id] || !tabs[tab_id].voicer) return;
    const v = tabs[tab_id].voicer;

    // Auto-detect module based on who is running, or from context
    // Since Python calls it, let's inject to both logs or determine via running state
    let target = v.tts.isRunning ? 'tts' : (v.stt.isRunning ? 'stt' : 'stt');

    const time = new Date().toLocaleTimeString();
    const color = log_type === 'error' ? 'text-red-400' : (log_type === 'success' ? 'text-green-400' : (log_type === 'warning' ? 'text-yellow-400' : 'text-white/60'));
    const entry = `<div class="${color}">[${time}] ${msg}</div>`;

    v[target].logs += entry;

    if (activeTabId === tab_id) {
        const lc = document.getElementById(`voicer-${target}-log`);
        if (lc) {
            lc.innerHTML += entry;
            lc.scrollTop = lc.scrollHeight;
        }
    }
}

eel.expose(voicer_update_status);
function voicer_update_status(tab_id, module, msg, colorClass) {
    const mod = module === 'synthesis' ? 'tts' : 'stt';
    if (!tabs[tab_id] || !tabs[tab_id].voicer) return;
    const html = `<span class="${colorClass}">${msg}</span>`;
    tabs[tab_id].voicer[mod].status = html;
    if (activeTabId === tab_id) {
        const el = document.getElementById(`voicer-${mod}-status`);
        if (el) el.innerHTML = html;
    }
}

eel.expose(voicer_update_progress);
function voicer_update_progress(tab_id, module, pct) {
    const mod = module === 'synthesis' ? 'tts' : 'stt';
    if (!tabs[tab_id] || !tabs[tab_id].voicer) return;
    tabs[tab_id].voicer[mod].progress = pct;
    if (activeTabId === tab_id) {
        const fill = document.getElementById(`voicer-${mod}-progress-fill`);
        const txt = document.getElementById(`voicer-${mod}-progress-text`);
        if (fill) fill.style.width = `${pct}%`;
        if (txt) txt.innerText = `${Math.round(pct)}%`;
    }
}

eel.expose(voicer_task_done);
function voicer_task_done(tab_id, module, success, result_path) {
    const mod = module === 'synthesis' ? 'tts' : 'stt';
    if (!tabs[tab_id] || !tabs[tab_id].voicer) return;

    tabs[tab_id].voicer[mod].isRunning = false;

    if (success && mod === 'tts' && tabs[tab_id].voicer.tts.autoStt) {
        // If auto STT, set the input of STT to the result audio
        tabs[tab_id].voicer.stt.filePath = result_path;
        // The python backend already launched whisper
        tabs[tab_id].voicer.stt.isRunning = true;
    }
    if (success && mod === 'stt') {
        tabs[tab_id].voicer.stt.resultPath = result_path || '';
    }

    if (activeTabId === tab_id) voicerSyncFromTab();
}

function voicerGetCurrentSrtPath() {
    const v = _getVoicer();
    return v && v.stt ? (v.stt.resultPath || '').trim() : '';
}

async function voicerCopyText(text, successMessage) {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    voicer_add_log_global(successMessage, "success");
}

function voicerEnsureSrtPath() {
    const srtPath = voicerGetCurrentSrtPath();
    if (!srtPath) {
        alert("Сначала выполните транскрибацию и получите SRT.", "warning");
        return "";
    }
    return srtPath;
}

window.voicerOpenSrtFolder = function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    eel.open_folder(activeTabId, srtPath);
};

window.voicerOpenSrtFile = function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    eel.open_file(activeTabId, srtPath);
};

window.voicerCopySrtPath = async function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    await voicerCopyText(srtPath, "📋 Путь к SRT скопирован.");
};

window.voicerCopySrtText = async function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const res = await eel.voicer_read_text_file(srtPath)();
    if (!res.success) return alert(res.error || "Не удалось прочитать SRT.", "error");
    await voicerCopyText(res.text || "", "📋 Текст SRT скопирован.");
};

window.voicerSaveSrtAs = async function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const res = await eel.voicer_save_srt_as(srtPath)();
    if (res.success && res.path) {
        const v = _getVoicer();
        if (v && v.stt) {
            v.stt.resultPath = res.path;
            voicerSyncFromTab();
        }
        voicer_add_log_global(`💾 SRT сохранён как: ${res.path}`, "success");
    }
};

function voicerGetOrCreateTargetTab(category, namePrefix) {
    const existingId = Object.keys(tabs || {}).find(id => tabs[id] && tabs[id].category === category);
    if (existingId) return existingId;
    return createTab(null, namePrefix, category);
}

window.voicerUseSrtInProgram = function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const tabId = voicerGetOrCreateTargetTab('video', 'Субтитры');
    tabs[tabId].inputs.addSubs = true;
    tabs[tabId].inputs.subsPath = srtPath;
    voicer_add_log_global("🎬 SRT подставлен в программу как файл субтитров.", "success");
};

window.voicerUseSrtForRenderSubs = function () {
    window.voicerUseSrtInProgram();
};

window.voicerSendSrtToPrompter = async function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const tabId = voicerGetOrCreateTargetTab('video', 'Prompter');
    if (!tabs[tabId].prompter) tabs[tabId].prompter = {};
    tabs[tabId].prompter.srtPath = srtPath;
    if (!tabs[tabId].prompter.saveDir) {
        tabs[tabId].prompter.saveDir = srtPath.substring(0, Math.max(srtPath.lastIndexOf('/'), srtPath.lastIndexOf('\\')));
    }
    const layout = await eel.prompter_parse_srt_layout(srtPath)();
    if (layout && layout.success) {
        tabs[tabId].prompter.srtSubsCount = layout.total_subs;
        tabs[tabId].prompter.srtDurationSec = layout.duration_sec || 0;
        tabs[tabId].prompter.srtPreview = `Длительность: ${formatDuration(layout.duration_sec)}`;
    }
    voicer_add_log_global("📝 SRT отправлен в Prompter.", "success");
};

window.voicerSendSrtToOverlay = function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const tabId = voicerGetOrCreateTargetTab('image', 'Overlay');
    tabs[tabId].overlay.srtPath = srtPath;
    if (!tabs[tabId].overlay.outFolder) {
        tabs[tabId].overlay.outFolder = srtPath.substring(0, Math.max(srtPath.lastIndexOf('/'), srtPath.lastIndexOf('\\')));
    }
    voicer_add_log_global("🖼️ SRT отправлен в Overlay.", "success");
};

window.voicerSendSrtToTiming = function () {
    const srtPath = voicerEnsureSrtPath();
    if (!srtPath) return;
    const tabId = voicerGetOrCreateTargetTab('image', 'Timing');
    tabs[tabId].timing.srtPath = srtPath;
    voicer_add_log_global("⏱️ SRT отправлен в Timing.", "success");
};

// 🔥 Новая функция: подгрузка ключа из config.json в поле Voicer + автозагрузка голосов
window.voicerLoadKeyFromConfig = async function () {
    try {
        const keyInput = document.getElementById('voicer-tts-api-key');
        if (!keyInput) return;

        // 1. Сначала пробуем взять ключ из стейта активной вкладки (если уже введён вручную)
        const v = _getVoicer();
        if (v && v.tts.apiKey && v.tts.apiKey.trim()) {
            keyInput.value = v.tts.apiKey;
            await voicerValidateAndFetch(v.tts.apiKey);
            return;
        }

        // 2. Иначе — берём из config.json
        const conf = await eel.get_config()();
        const cfgKey = conf && conf.elevenlabs_api_key ? conf.elevenlabs_api_key.trim() : "";
        if (cfgKey) {
            keyInput.value = cfgKey;
            if (v) {
                v.tts.apiKey = cfgKey;
                voicerSaveToTab();
            }
            await voicerValidateAndFetch(cfgKey);
        } else {
            // Нет ключа — сбрасываем рамку и список
            keyInput.style.borderColor = 'rgba(255,255,255,0.05)';
            const select = document.getElementById('voicer-tts-template');
            if (select) {
                select.innerHTML = '<option value="">Сначала введите API-ключ ElevenLabs...</option>';
            }
        }
    } catch (e) {
        console.error('[Voicer] Ошибка загрузки ключа:', e);
    }
};

// 🔥 Валидация ключа и подгрузка голосов
window.voicerValidateAndFetch = async function (key) {
    const keyInput = document.getElementById('voicer-tts-api-key');
    const ul = document.getElementById('voicer-template-options');
    const hidden = document.getElementById('voicer-tts-template');
    const label = document.getElementById('voicer-template-selected-text');

    if (!keyInput || !ul || !label) return;

    if (!key || !key.trim()) {
        keyInput.style.borderColor = 'rgba(255,255,255,0.05)';
        ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Сначала введите API-ключ ElevenLabs...</li>';
        label.textContent = "Сначала введите API-ключ ElevenLabs...";
        return;
    }

    // Жёлтая рамка — проверка
    keyInput.style.borderColor = '#F59E0B';
    ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Загрузка голосов...</li>';
    label.textContent = "Загрузка голосов...";

    try {
        const res = await eel.voicer_tts_get_templates(key)();
        if (res && res.success) {
            // Зелёная рамка — всё ок
            keyInput.style.borderColor = '#06B6D4';

            // Заполняем список голосов
            const v = _getVoicer();
            const templates = Array.isArray(res.templates) ? res.templates : [];
            let selectedUuid = templates.length > 0 ? ((v && v.tts.template) ? v.tts.template : templates[0].uuid) : '';

            // Check if selectedUuid actually exists in templates
            const exists = templates.some(t => t.uuid === selectedUuid);
            if (!exists && templates.length > 0) {
                selectedUuid = templates[0].uuid;
            }

            ul.innerHTML = templates.length > 0
                ? templates.map(t =>
                    `<li data-value="${t.uuid}" onclick="voicerSelectOption(this)" class="${t.uuid === selectedUuid ? 'selected' : ''}">${t.title}</li>`
                ).join('')
                : '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Ключ валиден, но шаблонов пока нет</li>';


            if (v && templates.length > 0) {
                v.tts.template = selectedUuid;
                hidden.value = selectedUuid;
                const selTemp = templates.find(t => t.uuid === selectedUuid);
                label.textContent = selTemp ? selTemp.title : templates[0].title;
                voicerSaveToTab();
            } else {
                hidden.value = '';
                label.textContent = "Ключ валиден, но шаблонов нет";
                if (v) {
                    v.tts.template = '';
                    voicerSaveToTab();
                }
            }

            // Сохраняем ключ глобально через бэкенд
            try { await eel.voicer_save_api_key(key)(); } catch (e) { }

            // Лог
            voicer_add_log_global("✅ API-ключ ElevenLabs валиден. Загружено голосов: " + res.templates.length, "success");
        } else {
            // Красная рамка — ошибка
            keyInput.style.borderColor = '#EF4444';
            ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Ошибка: неверный ключ или пусто</li>';
            label.textContent = "Ошибка: неверный ключ";
            voicer_add_log_global("❌ Ошибка проверки ключа: " + (res.error || 'неизвестная'), "error");
        }
    } catch (e) {
        keyInput.style.borderColor = '#EF4444';
        ul.innerHTML = '<li data-value="" onclick="voicerSelectOption(this)" class="selected">Ошибка соединения</li>';
        label.textContent = "Ошибка соединения";
        voicer_add_log_global("❌ Ошибка сети: " + e, "error");
    }
};

// 🔥 Хелпер для лога (пишет в активную вкладку, если она есть)
function voicer_add_log_global(msg, type) {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    if (typeof voicer_add_log === 'function') {
        voicer_add_log(activeTabId, msg, type);
    }
}

// 🔥 Обработчик ввода ключа вручную (с debounce)
let _voicerKeyDebounce = null;
document.addEventListener('DOMContentLoaded', () => {
    voicerLoadUserPresets();
    const keyInput = document.getElementById('voicer-tts-api-key');
    if (keyInput) {
        keyInput.addEventListener('input', () => {
            const v = _getVoicer();
            if (v) {
                v.tts.apiKey = keyInput.value.trim();
                voicerSaveToTab();
            }
            // Debounce: ждём 800мс после остановки ввода → валидируем
            if (_voicerKeyDebounce) clearTimeout(_voicerKeyDebounce);
            _voicerKeyDebounce = setTimeout(() => {
                voicerValidateAndFetch(keyInput.value.trim());
            }, 800);
        });
    }

    // Первичная подгрузка ключа при загрузке страницы
    setTimeout(() => voicerLoadKeyFromConfig(), 500);
});

// 🔥 ЗАГРУЗКА ТЕКСТА ИЗ .TXT / .DOCX
window.voicerLoadTextFromFile = async function () {
    try {
        const res = await eel.voicer_pick_text_file(activeTabId)();
        if (res && res.success) {
            const text = res.text;
            const ta = document.getElementById('voicer-tts-text');

            if (ta) {
                const existing = ta.value.trim();
                if (existing.length > 0) {
                    const replace = confirm("В поле уже есть текст. Заменить его?\n\nОК — заменить\nОтмена — добавить в конец");
                    ta.value = replace ? text : (existing + "\n\n" + text);
                } else {
                    ta.value = text;
                }

                const v = _getVoicer();

                // 🔥 Автоматически прописываем папку сохранения
                if (res.folder) {
                    document.getElementById('voicer-tts-output').value = res.folder;
                    v.tts.outFolder = res.folder;
                    voicer_add_log_global(`📁 Папка сохранения изменена на исходную папку файла`, "info");
                }

                // 🔥 Запоминаем имя файла (без расширения) для сохранения mp3
                if (res.filename) {
                    v.tts.customFileName = res.filename;
                }

                voicerSaveToTab();
                voicer_add_log_global(`✅ Текст загружен из файла ${res.filename} (${text.length} симв.)`, "success");
            }
        } else if (res && res.error && res.error !== "Отменено") {
            voicer_add_log_global("❌ Ошибка чтения файла: " + res.error, "error");
        }
    } catch (e) {
        voicer_add_log_global("❌ Ошибка чтения файла", "error");
    }
};

// 🔥 ТОГГЛ "КО ВСЕМ" для голосового шаблона
window.voicerToggleTemplateApplyAll = function () {
    const v = _getVoicer();
    if (!v) return;
    const cb = document.getElementById('voicer-template-apply-all');
    if (!cb) return;

    v.tts.templateApplyAll = cb.checked;

    if (cb.checked && v.tts.template) {
        voicerPropagateField('template', v.tts.template);
        voicer_add_log_global("✓ Голосовой шаблон применён ко всем проектам", "info");
    } else if (!cb.checked) {
        voicer_add_log_global("🚫 Этот проект теперь независим (Голосовой шаблон)", "warning");
    }
};

// 🔥 ТОГГЛ "КО ВСЕМ" для автопереноса
window.voicerToggleAutoSttApplyAll = function () {
    const v = _getVoicer();
    if (!v) return;
    const cb = document.getElementById('voicer-autostt-apply-all');
    if (!cb) return;

    v.tts.autoSttApplyAll = cb.checked;

    if (cb.checked) {
        voicerPropagateField('autoStt', v.tts.autoStt);
        voicer_add_log_global("✓ Авто-перенос применён ко всем проектам", "info");
    } else if (!cb.checked) {
        voicer_add_log_global("🚫 Этот проект теперь независим (Авто-перенос)", "warning");
    }
};

// 🔥 ПОМОЩНИК: Раздает значения по всем проектам
function voicerPropagateField(field, value) {
    if (!tabs || !activeTabId) return;
    const flagMap = { 'template': 'templateApplyAll', 'autoStt': 'autoSttApplyAll', 'speedUp': 'speedUpApplyAll' };
    const flag = flagMap[field];
    if (!flag) return;

    const srcTab = tabs[activeTabId];
    // Двойная защита: источник должен иметь флаг "Ко всем" = true
    if (!srcTab || srcTab.category !== 'voicer' || !srcTab.voicer || srcTab.voicer.tts[flag] !== true) {
        return;
    }

    let count = 0;
    Object.keys(tabs).forEach(function (id) {
        if (id === activeTabId) return; // Не применяем к самому себе
        const t = tabs[id];

        // Строгая фильтрация: только проекты Voicer
        if (!t || t.category !== 'voicer') return;

        // Если voicer ещё не создан (например, фоновые вкладки) — создаём его с дефолтами,
        // чтобы он мог принять новое значение!
        if (!t.voicer) {
            t.voicer = {
                tts: {
                    apiKey: '', template: '', outFolder: '', text: '',
                    autoStt: true, logs: '', status: 'Ожидание...', progress: 0, isRunning: false,
                    templateApplyAll: true, autoSttApplyAll: true
                },
                stt: { filePath: '', model: 'small', prompt: '', logs: '', status: 'Ожидание...', progress: 0, isRunning: false }
            };
        }

        // ВАЖНО: Если у целевой вкладки галочка "Ко всем" СНЯТА, мы её ИГНОРИРУЕМ!
        if (t.voicer.tts[flag] !== true) return;

        // Применяем значение
        t.voicer.tts[field] = value;
        count++;
    });

    if (count > 0 && typeof voicer_add_log_global === 'function') {
        const fieldName = field === 'autoStt' ? 'Авто-перенос' : (field === 'speedUp' ? 'Ускорение аудио' : 'Голосовой шаблон');
        voicer_add_log_global(`✓ Значение '${fieldName}' синхронизировано с ${count} проект(ами)`, "info");
    }
}


// === БАТЧ-ЗАГРУЗКА ИЗ ПАПКИ (Voicer) ===

window.voicerLoadTextFolder = async function () {
    try {
        const folderRes = await eel.voicer_browse_folder()();
        if (!folderRes.success) {
            if (folderRes.error !== "Отменено") voicer_add_log_global("Ошибка: " + folderRes.error, "error");
            return;
        }
        if (!folderRes.path) return;

        voicer_add_log_global(`Сканирую папку на наличие текстовых файлов...`, "info");
        const res = await eel.voicer_scan_text_folder(folderRes.path)();

        if (!res.success) return voicer_add_log_global("Ошибка сканирования: " + res.error, "error");
        if (!res.files || res.files.length === 0) {
            return voicer_add_log_global("В выбранной папке нет .txt, .md или .docx файлов!", "warning");
        }

        voicer_add_log_global(`Найдено ${res.files.length} текстовых файлов. Создаю проекты...`, "info");

        let lastTabId = null;
        voicerSaveToTab();
        const currentVoicer = _getVoicer();

        for (let fileData of res.files) {
            const newTabId = createTab(null, fileData.filename, 'voicer');
            const newVoicer = tabs[newTabId].voicer;

            newVoicer.tts.text = fileData.text;
            newVoicer.tts.outFolder = fileData.folder;
            newVoicer.tts.customFileName = fileData.filename;

            newVoicer.tts.apiKey = currentVoicer.tts.apiKey;
            newVoicer.tts.template = currentVoicer.tts.template;
            newVoicer.tts.autoStt = currentVoicer.tts.autoStt;
            newVoicer.tts.engine = currentVoicer.tts.engine;
            newVoicer.tts.voicePresetId = currentVoicer.tts.voicePresetId || '';
            newVoicer.tts.userPresetName = currentVoicer.tts.userPresetName || '';
            newVoicer.tts.mateoVoiceId = currentVoicer.tts.mateoVoiceId || '';

            lastTabId = newTabId;
        }

        if (lastTabId) {
            switchTab(lastTabId);
            renderTabs();
        }

        voicer_add_log_global(`✅ Создано ${res.files.length} проектов из папки`, "success");
    } catch (e) {
        console.error(e);
        voicer_add_log_global("Критическая ошибка: " + e, "error");
    }
};

window.voicerLoadAudioFolder = async function () {
    try {
        const folderRes = await eel.voicer_browse_folder()();
        if (!folderRes.success) {
            if (folderRes.error !== "Отменено") voicer_add_log_global("Ошибка: " + folderRes.error, "error");
            return;
        }
        if (!folderRes.path) return;

        voicer_add_log_global(`Сканирую папку на наличие медиафайлов...`, "info");
        const res = await eel.voicer_scan_audio_folder(folderRes.path)();

        if (!res.success) return voicer_add_log_global("Ошибка сканирования: " + res.error, "error");
        if (!res.files || res.files.length === 0) {
            return voicer_add_log_global("В выбранной папке нет медиафайлов!", "warning");
        }

        voicer_add_log_global(`Найдено ${res.files.length} медиафайлов. Создаю проекты...`, "info");

        let lastTabId = null;
        voicerSaveToTab();
        const currentVoicer = _getVoicer();

        for (let fileData of res.files) {
            const newTabId = createTab(null, fileData.filename, 'voicer');
            const newVoicer = tabs[newTabId].voicer;

            newVoicer.stt.filePath = fileData.path;
            if (fileData.prompt) newVoicer.stt.prompt = fileData.prompt;
            newVoicer.stt.model = currentVoicer.stt.model;
            newVoicer.stt.saveDir = currentVoicer.stt.saveDir || fileData.path.substring(0, Math.max(fileData.path.lastIndexOf('/'), fileData.path.lastIndexOf('\\')));
            newVoicer.stt.saveDirApplyAll = currentVoicer.stt.saveDirApplyAll;
            newVoicer.stt.useGlobalSaveDir = currentVoicer.stt.useGlobalSaveDir;

            lastTabId = newTabId;
        }

        if (lastTabId) {
            switchTab(lastTabId);
            renderTabs();
            if (typeof switchVoicerSubTab === 'function') switchVoicerSubTab('transcription');
        }

        voicer_add_log_global(`✅ Создано ${res.files.length} проектов из папки`, "success");
    } catch (e) {
        console.error(e);
        voicer_add_log_global("Критическая ошибка: " + e, "error");
    }
};

// === БАТЧ-ЗАПУСК (Voicer) ===

window.voicerTtsStartAll = async function () {
    voicerSaveToTab();
    const ttsTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        return t.category === 'voicer' && t.voicer && t.voicer.tts.text.trim() !== '' && !t.voicer.tts.isRunning;
    });

    if (ttsTabs.length === 0) return alert("Нет готовых проектов для синтеза речи!");

    const btnAll = document.getElementById('voicer-tts-btn-all');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-[16px]">sync</span> Запуск...';
    }

    voicer_add_log_global(`🚀 Запуск ${ttsTabs.length} задач синтеза речи (ПОСЛЕДОВАТЕЛЬНО)...`, "success");

    for (let i = 0; i < ttsTabs.length; i++) {
        let tabId = ttsTabs[i];
        const v = tabs[tabId].voicer;
        if (!v.tts.apiKey || !v.tts.template || !v.tts.outFolder) {
            voicer_add_log_global(`[${tabs[tabId].name}] Пропуск: не заполнены настройки TTS`, "error");
            continue;
        }

        voicer_add_log_global(`[${i + 1}/${ttsTabs.length}] Старт: ${tabs[tabId].name}`, "info");

        v.tts.isRunning = true;
        v.tts.progress = 0;
        v.tts.logs = '';
        if (activeTabId === tabId) voicerSyncFromTab();

        eel.voicer_tts_start(
            tabId, v.tts.apiKey, v.tts.text, v.tts.template,
            v.tts.outFolder, v.tts.autoStt, v.stt.model, "ru", v.tts.customFileName || "", v.tts.speedUp || 0
        )();

        // 🔥 МАГИЯ ЗДЕСЬ: Ждем, пока бэкенд не вернет isRunning = false
        while (tabs[tabId] && tabs[tabId].voicer && tabs[tabId].voicer.tts.isRunning) {
            await new Promise(r => setTimeout(r, 1000));
        }
    }

    if (btnAll) {
        btnAll.disabled = false;
        btnAll.innerHTML = '<span class="material-symbols-outlined !text-[16px]">rocket_launch</span> Начать все';
    }
    voicer_add_log_global(`✅ Все задачи синтеза речи завершены!`, "success");
};

window.voicerSttStartAll = async function () {
    voicerSaveToTab();
    const sttTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        return t.category === 'voicer' && t.voicer && t.voicer.stt.filePath !== '' && !t.voicer.stt.isRunning;
    });

    if (sttTabs.length === 0) return alert("Нет готовых проектов для транскрибации!");

    const btnAll = document.getElementById('voicer-stt-btn-all');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-[16px]">sync</span> Запуск...';
    }

    voicer_add_log_global(`🚀 Запуск ${sttTabs.length} задач транскрибации (ПОСЛЕДОВАТЕЛЬНО)...`, "success");

    for (let i = 0; i < sttTabs.length; i++) {
        let tabId = sttTabs[i];
        const v = tabs[tabId].voicer;

        voicer_add_log_global(`[${i + 1}/${sttTabs.length}] Старт транскрибации: ${tabs[tabId].name}`, "info");

        v.stt.isRunning = true;
        v.stt.progress = 0;
        v.stt.logs = '';
        if (activeTabId === tabId) voicerSyncFromTab();

        eel.voicer_whisper_start(
            tabId, v.stt.filePath, v.stt.model, "ru", v.stt.prompt, v.stt.saveDir || ""
        )();

        // 🔥 ЖДЕМ ЗАВЕРШЕНИЯ ТЕКУЩЕЙ ТРАНСКРИБАЦИИ
        while (tabs[tabId] && tabs[tabId].voicer && tabs[tabId].voicer.stt.isRunning) {
            await new Promise(r => setTimeout(r, 1000));
        }
    }

    if (btnAll) {
        btnAll.disabled = false;
        btnAll.innerHTML = '<span class="material-symbols-outlined !text-[16px]">rocket_launch</span> Начать все';
    }
    voicer_add_log_global(`✅ Все задачи транскрибации завершены!`, "success");
};

window.voicerToggleSpeedApplyAll = function () {
    const v = _getVoicer();
    if (!v) return;
    const cb = document.getElementById('voicer-speed-apply-all');
    if (!cb) return;

    v.tts.speedUpApplyAll = cb.checked;

    if (cb.checked) {
        voicerPropagateField('speedUp', v.tts.speedUp);
        voicer_add_log_global("✓ Ускорение аудио применено ко всем проектам", "info");
    } else {
        voicer_add_log_global("🚫 Этот проект теперь независим (Ускорение аудио)", "warning");
    }
};


window.downloadVoicerDebugLog = async function () {
    try {
        const res = await eel.voicer_get_debug_log()();
        if (res.success) {
            const blob = new Blob([res.log_content], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'voicer_debug.log';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            voicer_add_log_global("✅ Подробный Debug-лог успешно скачан.", "success");
        } else {
            alert("Ошибка скачивания лога: " + res.error);
        }
    } catch (e) {
        alert("Ошибка связи с бэкендом: " + e);
    }
};

// ============================================================
// === VOICER MATEO — Полная поддержка второго движка =========
// ============================================================

// --- Переключатель движков ---
window.voicerSwitchEngine = function (engine) {
    const v = _getVoicer();
    if (!v) return;

    v.tts.engine = engine;

    const standardBlock = document.getElementById('voicer-standard-block');
    const mateoBlock = document.getElementById('voicer-mateo-block');
    const btnStandard = document.getElementById('voicer-engine-btn-standard');
    const btnMateo = document.getElementById('voicer-engine-btn-mateo');

    if (engine === 'mateo') {
        if (standardBlock) standardBlock.classList.add('hidden');
        if (mateoBlock) mateoBlock.classList.remove('hidden');

        // Кнопка Mateo — активная (фиолетовая)
        if (btnMateo) {
            btnMateo.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all bg-[#A78BFA]/20 text-[#A78BFA] border border-[#A78BFA]/30 shadow-[0_0_10px_rgba(167,139,250,0.2)]';
        }
        // Кнопка Standard — неактивная
        if (btnStandard) {
            btnStandard.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all text-white/30 hover:text-[#06B6D4] hover:bg-[#06B6D4]/10 border border-transparent';
        }

        // Подгружаем токен Mateo из config.json при первом переключении
        if (!v.tts.mateoToken) {
            eel.voicer_get_mateo_token()(function (tok) {
                if (tok) {
                    v.tts.mateoToken = tok;
                    const inp = document.getElementById('voicer-mateo-token');
                    if (inp) inp.value = tok;
                }
            });
        }
    } else {
        if (standardBlock) standardBlock.classList.remove('hidden');
        if (mateoBlock) mateoBlock.classList.add('hidden');

        // Кнопка Standard — активная (голубая)
        if (btnStandard) {
            btnStandard.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all bg-[#06B6D4]/20 text-[#06B6D4] border border-[#06B6D4]/30 shadow-[0_0_10px_rgba(6,182,212,0.2)]';
        }
        // Кнопка Mateo — неактивная
        if (btnMateo) {
            btnMateo.className = 'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all text-white/30 hover:text-[#A78BFA] hover:bg-[#A78BFA]/10 border border-transparent';
        }
    }

    voicerSaveToTab();
};

// --- Сохранение токена Mateo ---
window.voicerMateoSaveToken = function () {
    const v = _getVoicer();
    const inp = document.getElementById('voicer-mateo-token');
    if (!v || !inp) return;
    v.tts.mateoToken = inp.value.trim();
    // Дебаунс — сохраняем в config.json через 800мс
    if (window._mateoTokenDebounce) clearTimeout(window._mateoTokenDebounce);
    window._mateoTokenDebounce = setTimeout(() => {
        eel.voicer_save_mateo_token(v.tts.mateoToken)();
    }, 800);
    voicerSaveToTab();
};

// --- Выбор голоса Mateo ---
window.voicerMateoSelectVoice = function (li) {
    const sel = li.closest('.custom-select');
    if (!sel) return;
    const value = li.getAttribute('data-value');
    const label = li.textContent;

    document.getElementById('voicer-mateo-voice-selected-text').textContent = label;
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');

    const customInput = document.getElementById('voicer-mateo-voice-custom');
    const hiddenInput = document.getElementById('voicer-mateo-voice-id');

    if (value === '__custom__') {
        if (customInput) customInput.classList.remove('hidden');
    } else {
        if (customInput) customInput.classList.add('hidden');
        if (hiddenInput) hiddenInput.value = value;
    }

    voicerSaveToTab();
};

// --- Выбор модели Mateo ---
window.voicerMateoSelectModel = function (li) {
    const sel = li.closest('.custom-select');
    if (!sel) return;
    const value = li.getAttribute('data-value');
    const label = li.textContent;

    document.getElementById('voicer-mateo-model-selected-text').textContent = label;
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');

    const hidden = document.getElementById('voicer-mateo-model-id');
    if (hidden) hidden.value = value;

    voicerSaveToTab();
};

// --- Выбор типа разбивки Mateo ---
window.voicerMateoSelectSplit = function (li) {
    const sel = li.closest('.custom-select');
    if (!sel) return;
    const value = li.getAttribute('data-value');
    const label = li.textContent;

    document.getElementById('voicer-mateo-split-selected-text').textContent = label;
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');

    const hidden = document.getElementById('voicer-mateo-split-type');
    if (hidden) hidden.value = value;

    voicerSaveToTab();
};

// --- Тоггл авто-пауз Mateo ---
window.voicerMateoToggleAutoPause = function () {
    const cb = document.getElementById('voicer-mateo-autopause');
    const params = document.getElementById('voicer-mateo-pause-params');
    if (!cb || !params) return;
    if (cb.checked) {
        params.classList.remove('hidden');
    } else {
        params.classList.add('hidden');
    }
    voicerSaveToTab();
};

// --- Закрытие Mateo-дропдаунов при клике снаружи ---
document.addEventListener('click', function (e) {
    if (!e.target.closest('#voicer-mateo-voice-select') &&
        !e.target.closest('#voicer-mateo-model-select') &&
        !e.target.closest('#voicer-mateo-split-select')) {
        ['voicer-mateo-voice-select', 'voicer-mateo-model-select', 'voicer-mateo-split-select'].forEach(id => {
            const sel = document.getElementById(id);
            if (sel && sel.classList.contains('open')) {
                sel.classList.remove('open');
                const opts = sel.querySelector('.select-options');
                if (opts) opts.classList.add('hidden');
            }
        });
    }
});

// --- Расширение voicerSaveToTab: сохраняем параметры Mateo ---
const _origVoicerSaveToTab = window.voicerSaveToTab;
window.voicerSaveToTab = function () {
    _origVoicerSaveToTab();

    const v = _getVoicer();
    if (!v) return;

    // Engine
    const engineStandard = document.getElementById('voicer-engine-btn-standard');
    // определяем активный движок по классу кнопки Mateo
    const btnMateoEl = document.getElementById('voicer-engine-btn-mateo');
    if (btnMateoEl && btnMateoEl.classList.contains('text-[#A78BFA]')) {
        v.tts.engine = 'mateo';
    } else {
        v.tts.engine = v.tts.engine || 'standard';
    }

    // Mateo fields
    const mateoToken = document.getElementById('voicer-mateo-token');
    if (mateoToken) v.tts.mateoToken = mateoToken.value.trim();

    const mateoVoiceId = document.getElementById('voicer-mateo-voice-id');
    const mateoVoiceCustom = document.getElementById('voicer-mateo-voice-custom');
    if (mateoVoiceId) {
        if (mateoVoiceCustom && !mateoVoiceCustom.classList.contains('hidden')) {
            v.tts.mateoVoiceId = mateoVoiceCustom.value.trim() || mateoVoiceId.value;
        } else {
            v.tts.mateoVoiceId = mateoVoiceId.value;
        }
    }

    const mateoModelId = document.getElementById('voicer-mateo-model-id');
    if (mateoModelId) v.tts.mateoModelId = mateoModelId.value;

    const mateoSplitType = document.getElementById('voicer-mateo-split-type');
    if (mateoSplitType) v.tts.mateoSplitType = mateoSplitType.value;

    const mateoSplitOutput = document.getElementById('voicer-mateo-split-output');
    if (mateoSplitOutput) v.tts.mateoSplitOutput = mateoSplitOutput.checked;

    const mateoAutoPause = document.getElementById('voicer-mateo-autopause');
    if (mateoAutoPause) v.tts.mateoAutoPauseEnabled = mateoAutoPause.checked;

    const mateoPauseDuration = document.getElementById('voicer-mateo-pause-duration');
    if (mateoPauseDuration) v.tts.mateoAutoPauseDuration = parseFloat(mateoPauseDuration.value) || 1.0;

    const mateoPauseFreq = document.getElementById('voicer-mateo-pause-frequency');
    if (mateoPauseFreq) v.tts.mateoAutoPauseFrequency = parseInt(mateoPauseFreq.value) || 1;
};

// --- Расширение voicerSyncFromTab: восстанавливаем параметры Mateo ---
const _origVoicerSyncFromTab = window.voicerSyncFromTab;
window.voicerSyncFromTab = function () {
    _origVoicerSyncFromTab();

    const v = _getVoicer();
    if (!v) return;

    // Восстанавливаем активный движок
    if (v.tts.engine === 'mateo') {
        voicerSwitchEngine('mateo');
    } else {
        voicerSwitchEngine('standard');
    }

    // Mateo token
    const mateoToken = document.getElementById('voicer-mateo-token');
    if (mateoToken) mateoToken.value = v.tts.mateoToken || '';

    // Voice ID
    const mateoVoiceId = document.getElementById('voicer-mateo-voice-id');
    if (mateoVoiceId && v.tts.mateoVoiceId) {
        mateoVoiceId.value = v.tts.mateoVoiceId;
        const li = document.querySelector(`#voicer-mateo-voice-options li[data-value="${v.tts.mateoVoiceId}"]`);
        if (li) {
            document.getElementById('voicer-mateo-voice-selected-text').textContent = li.textContent;
            document.querySelectorAll('#voicer-mateo-voice-options li').forEach(l => l.classList.remove('selected'));
            li.classList.add('selected');
        }
    }

    // Model ID
    const mateoModelId = document.getElementById('voicer-mateo-model-id');
    if (mateoModelId && v.tts.mateoModelId) {
        mateoModelId.value = v.tts.mateoModelId;
        const li = document.querySelector(`#voicer-mateo-model-options li[data-value="${v.tts.mateoModelId}"]`);
        if (li) {
            document.getElementById('voicer-mateo-model-selected-text').textContent = li.textContent;
            document.querySelectorAll('#voicer-mateo-model-options li').forEach(l => l.classList.remove('selected'));
            li.classList.add('selected');
        }
    }

    // Split type
    const mateoSplitType = document.getElementById('voicer-mateo-split-type');
    if (mateoSplitType && v.tts.mateoSplitType) {
        mateoSplitType.value = v.tts.mateoSplitType;
        const li = document.querySelector(`#voicer-mateo-split-options li[data-value="${v.tts.mateoSplitType}"]`);
        if (li) {
            document.getElementById('voicer-mateo-split-selected-text').textContent = li.textContent;
            document.querySelectorAll('#voicer-mateo-split-options li').forEach(l => l.classList.remove('selected'));
            li.classList.add('selected');
        }
    }

    // Split output checkbox
    const mateoSplitOutput = document.getElementById('voicer-mateo-split-output');
    if (mateoSplitOutput) mateoSplitOutput.checked = !!v.tts.mateoSplitOutput;

    // Auto pause
    const mateoAutoPause = document.getElementById('voicer-mateo-autopause');
    const mateoPauseParams = document.getElementById('voicer-mateo-pause-params');
    if (mateoAutoPause) {
        mateoAutoPause.checked = !!v.tts.mateoAutoPauseEnabled;
        if (mateoPauseParams) {
            if (v.tts.mateoAutoPauseEnabled) {
                mateoPauseParams.classList.remove('hidden');
            } else {
                mateoPauseParams.classList.add('hidden');
            }
        }
    }

    const mateoPauseDuration = document.getElementById('voicer-mateo-pause-duration');
    if (mateoPauseDuration) mateoPauseDuration.value = v.tts.mateoAutoPauseDuration || 1.0;

    const mateoPauseFreq = document.getElementById('voicer-mateo-pause-frequency');
    if (mateoPauseFreq) mateoPauseFreq.value = v.tts.mateoAutoPauseFrequency || 1;
};

// --- Переопределяем voicerTtsStart с поддержкой Mateo ---
const _origVoicerTtsStart = window.voicerTtsStart;
window.voicerTtsStart = async function () {
    voicerSaveToTab();
    const v = _getVoicer();
    if (!v) return;

    if (v.tts.engine === 'mateo') {
        // === Запуск через Voicer Mateo ===
        if (!v.tts.mateoToken) return alert("Введите токен Voicer Mateo!");
        if (!v.tts.mateoVoiceId) return alert("Выберите голос для Voicer Mateo!");
        if (!v.tts.outFolder) return alert("Выберите папку для сохранения!");
        if (!v.tts.text.trim()) return alert("Введите текст для озвучки!");

        v.tts.isRunning = true;
        v.tts.progress = 0;
        v.tts.logs = '';
        voicerSyncFromTab();

        await eel.voicer_mateo_tts_start(
            activeTabId,
            v.tts.mateoToken,
            v.tts.text,
            v.tts.mateoVoiceId,
            v.tts.mateoModelId || 'eleven_multilingual_v2',
            v.tts.mateoSplitType || 'smart',
            !!v.tts.mateoSplitOutput,
            !!v.tts.mateoAutoPauseEnabled,
            v.tts.mateoAutoPauseDuration || 1.0,
            v.tts.mateoAutoPauseFrequency || 1,
            v.tts.outFolder,
            v.tts.autoStt,
            v.stt.model || 'small',
            'ru',
            v.tts.customFileName || '',
            v.tts.speedUp || 0
        )();
    } else {
        // === Стандартный запуск ===
        if (!v.tts.apiKey) return alert("Введите API ключ!");
        if (!v.tts.template) return alert("Выберите голосовой шаблон!");
        if (!v.tts.outFolder) return alert("Выберите папку для сохранения!");
        if (!v.tts.text.trim()) return alert("Введите текст для озвучки!");

        v.tts.isRunning = true;
        v.tts.progress = 0;
        v.tts.logs = '';
        voicerSyncFromTab();

        await eel.voicer_tts_start(
            activeTabId, v.tts.apiKey, v.tts.text, v.tts.template,
            v.tts.outFolder, v.tts.autoStt, v.stt.model, "ru", v.tts.customFileName || "", v.tts.speedUp || 0
        )();
    }
};

// --- Переопределяем voicerTtsStartAll с поддержкой Mateo ---
window.voicerTtsStartAll = async function () {
    voicerSaveToTab();
    const ttsTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        return t.category === 'voicer' && t.voicer && t.voicer.tts.text.trim() !== '' && !t.voicer.tts.isRunning;
    });

    if (ttsTabs.length === 0) return alert("Нет готовых проектов для синтеза речи!");

    const btnAll = document.getElementById('voicer-tts-btn-all');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-[16px]">sync</span> Запуск...';
    }

    voicer_add_log_global(`🚀 Запуск ${ttsTabs.length} задач синтеза речи (ПОСЛЕДОВАТЕЛЬНО)...`, "success");

    for (let i = 0; i < ttsTabs.length; i++) {
        let tabId = ttsTabs[i];
        const v = tabs[tabId].voicer;

        voicer_add_log_global(`[${i + 1}/${ttsTabs.length}] Старт: ${tabs[tabId].name}`, "info");

        v.tts.isRunning = true;
        v.tts.progress = 0;
        v.tts.logs = '';
        if (activeTabId === tabId) voicerSyncFromTab();

        if (v.tts.engine === 'mateo') {
            if (!v.tts.mateoToken || !v.tts.mateoVoiceId || !v.tts.outFolder) {
                voicer_add_log_global(`[${tabs[tabId].name}] Пропуск: не заполнены настройки Mateo`, "error");
                v.tts.isRunning = false;
                continue;
            }
            eel.voicer_mateo_tts_start(
                tabId,
                v.tts.mateoToken,
                v.tts.text,
                v.tts.mateoVoiceId,
                v.tts.mateoModelId || 'eleven_multilingual_v2',
                v.tts.mateoSplitType || 'smart',
                !!v.tts.mateoSplitOutput,
                !!v.tts.mateoAutoPauseEnabled,
                v.tts.mateoAutoPauseDuration || 1.0,
                v.tts.mateoAutoPauseFrequency || 1,
                v.tts.outFolder,
                v.tts.autoStt,
                v.stt.model || 'small',
                'ru',
                v.tts.customFileName || '',
                v.tts.speedUp || 0
            )();
        } else {
            if (!v.tts.apiKey || !v.tts.template || !v.tts.outFolder) {
                voicer_add_log_global(`[${tabs[tabId].name}] Пропуск: не заполнены настройки TTS`, "error");
                v.tts.isRunning = false;
                continue;
            }
            eel.voicer_tts_start(
                tabId, v.tts.apiKey, v.tts.text, v.tts.template,
                v.tts.outFolder, v.tts.autoStt, v.stt.model, "ru", v.tts.customFileName || "", v.tts.speedUp || 0
            )();
        }

        // Ждём завершения
        while (tabs[tabId] && tabs[tabId].voicer && tabs[tabId].voicer.tts.isRunning) {
            await new Promise(r => setTimeout(r, 1000));
        }
    }

    if (btnAll) {
        btnAll.disabled = false;
        btnAll.innerHTML = '<span class="material-symbols-outlined !text-[16px]">rocket_launch</span> Начать все';
    }
    voicer_add_log_global(`✅ Все задачи синтеза речи завершены!`, "success");
};

// --- Загрузка токена Mateo из config.json при старте ---
document.addEventListener('DOMContentLoaded', () => {
    voicerLoadUserPresets();
    setTimeout(() => {
        eel.voicer_get_mateo_token()(function (tok) {
            const v = _getVoicer();
            if (tok && v && !v.tts.mateoToken) {
                v.tts.mateoToken = tok;
                const inp = document.getElementById('voicer-mateo-token');
                if (inp) inp.value = tok;
            }
        });
    }, 600);
});

