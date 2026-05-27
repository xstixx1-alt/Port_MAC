/* 
* Stocky non Stop — Image Overlay UI
* Автор: Азат | @inomix
*/
// === IMAGE OVERLAY AUTOMATION STATE ===
// overlayState удалён — состояние теперь хранится в window.tabs[activeTabId].overlay

// 1. Initializer wrapper mapped to the single dashboard
async function showOverlayPage(el) {
    // Скрыть все страницы
    ['page-download', 'page-render', 'page-overlay', 'page-timing', 'page-composer', 'page-voicer', 'page-prompter'].forEach(id => {
        const e = document.getElementById(id);
        if (e) { e.classList.add('hidden'); e.style.display = 'none'; }
    });

    // Показать overlay
    const target = document.getElementById('page-overlay');
    if (target) {
        target.classList.remove('hidden');
        target.style.display = 'flex';
    }

    // Подсветка пункта меню
    document.querySelectorAll('.submenu-item, .imgfactory-submenu-item, .voicer-submenu-item').forEach(x => {
        x.classList.remove('active', 'active-overlay', 'active-timing', 'active-composer', 'active-voicer');
    });
    if (el) el.classList.add('active-overlay');

    // Авто-раскрытие Image Factory подменю
    const imgSubmenu = document.getElementById('imgfactory-submenu');
    const imgArrow = document.getElementById('imgfactory-arrow');
    if (imgSubmenu && !imgSubmenu.classList.contains('open')) {
        imgSubmenu.classList.add('open');
        if (imgArrow) imgArrow.textContent = 'expand_more';
    }

    currentMode = 'mode-overlay';

    // ВАЖНО: Активируем рабочее пространство Image
    if (typeof switchToCategory === 'function') switchToCategory('image');
    if (typeof renderTabs === 'function') renderTabs();

    // Подгрузка ключа
    setTimeout(async () => {
        try {
            const conf = await eel.get_config()();
            const keyInput = document.getElementById('overlay-api-key');
            const providerInput = document.getElementById('overlay-provider');
            const tab = tabs[activeTabId] && tabs[activeTabId].overlay ? tabs[activeTabId].overlay : null;
            const provider = (tab && tab.provider) || (conf && conf.ai_provider) || "deepseek";
            const aiKey = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : "";
            const aiModel = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : "";
            if (providerInput) providerInput.value = provider;
            if (window.renderAiModelOptions) window.renderAiModelOptions("overlay", provider, aiModel, conf);
            if (keyInput && aiKey) {
                keyInput.value = aiKey;
                overlaySaveKey();
            }
        } catch (e) { }
    }, 200);
}

async function overlaySaveKey() {
    const keyInput = document.getElementById('overlay-api-key');
    const key = keyInput.value.trim();
    const provider = document.getElementById('overlay-provider').value || 'deepseek';
    const model = document.getElementById('overlay-model').value || '';
    if (!key) {
        keyInput.style.borderColor = 'rgba(255,255,255,0.05)';
        return;
    }

    keyInput.style.borderColor = '#F59E0B'; // yellow indicating checking
    try {
        const keyRes = await eel.overlay_validate_key(key, provider, model)();
        if (keyRes.valid) {
            keyInput.style.borderColor = '#10B981'; // green
            overlayLog(`AI подключен: ${keyRes.provider_label || provider} / ${keyRes.model || model}`, "success");
            const t = tabs[activeTabId] && tabs[activeTabId].overlay;
            if (t) {
                t.apiKey = key;
                t.provider = provider;
                t.model = keyRes.model || model;
            }
        } else {
            keyInput.style.borderColor = '#EF4444'; // red
            overlayLog("Ошибка ключа API: " + (keyRes.error || 'недействителен'), "error");
        }
    } catch (e) {
        keyInput.style.borderColor = '#EF4444';
    }
}

function overlayLog(msg, type = 'info') {
    const logContainer = document.getElementById('overlay-log-container');
    if (!logContainer) return;

    if (logContainer.innerHTML.includes("Ожидание настройки")) logContainer.innerHTML = "";

    const colors = {
        'info': 'text-white/60',
        'success': 'text-[#10B981]',
        'error': 'text-red-400',
        'warning': 'text-yellow-400'
    };
    const c = colors[type] || colors['info'];

    const time = new Date().toLocaleTimeString();
    const entryHtml = `<div class="${c}">[${time}] ${msg}</div>`;

    // 1. В DOM (для немедленной видимости)
    logContainer.innerHTML += entryHtml;
    logContainer.scrollTop = logContainer.scrollHeight;

    // 2. 🔥 В состояние текущей вкладки (для изоляции при переключении)
    if (activeTabId && tabs && tabs[activeTabId] && tabs[activeTabId].overlay) {
        if (typeof tabs[activeTabId].overlay.logs !== 'string') {
            tabs[activeTabId].overlay.logs = '';
        }
        tabs[activeTabId].overlay.logs += entryHtml;
    }
}

// === СИНХРОНИЗАЦИЯ И ИЗОЛЯЦИЯ ВКЛАДОК OVERLAY ===

// Сохраняем UI в текущую вкладку
window.overlaySaveToTab = function () {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    const t = tabs[activeTabId].overlay;
    if (!t) return;

    t.threads = document.getElementById('overlay-threads').value;
    t.promptPath = document.getElementById('overlay-prompt-path').value;
    t.outFolder = document.getElementById('overlay-output-path').value;
    t.srtPath = document.getElementById('overlay-srt-path').value;
    t.apiKey = document.getElementById('overlay-api-key').value || '';
    t.provider = document.getElementById('overlay-provider').value || 'deepseek';
    t.model = document.getElementById('overlay-model').value || '';

    const cb = document.getElementById('overlay-apply-all');
    if (cb && cb.checked) {
        overlayApplyToAll();
    }
};

// Восстанавливаем UI из текущей вкладки
window.overlaySyncFromTab = function () {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    const t = tabs[activeTabId].overlay;
    if (!t) return;

    document.getElementById('overlay-threads').value = t.threads || 20;
    document.getElementById('overlay-prompt-path').value = t.promptPath || '';
    document.getElementById('overlay-output-path').value = t.outFolder || '';
    document.getElementById('overlay-srt-path').value = t.srtPath || '';
    document.getElementById('overlay-api-key').value = t.apiKey || '';
    const provider = t.provider || 'deepseek';
    document.getElementById('overlay-provider').value = provider;
    if (window.renderAiModelOptions) {
        eel.get_config()(function (conf) {
            window.renderAiModelOptions("overlay", provider, t.model || "", conf);
            if (!t.apiKey && window.getAiKeyByProvider) {
                const resolvedKey = window.getAiKeyByProvider(conf, provider);
                document.getElementById('overlay-api-key').value = resolvedKey || '';
                t.apiKey = resolvedKey || '';
            }
        });
    }

    document.getElementById('overlay-subs-count').innerText = t.subsCount || 0;
    document.getElementById('overlay-windows-count').innerText = t.windowsCount || 0;

    // 🔥 Восстанавливаем логи конкретно этой вкладки
    const logContainer = document.getElementById('overlay-log-container');
    if (logContainer) {
        if (typeof t.logs === 'string' && t.logs.length > 0) {
            logContainer.innerHTML = t.logs;
            logContainer.scrollTop = logContainer.scrollHeight;
        } else {
            logContainer.innerHTML = '<div class="italic opacity-30">Ожидание настройки системы...</div>';
        }
    }

    // 🔥 Восстанавливаем промпты/окна в правой панели
    const promptsList = document.getElementById('overlay-prompts-list');
    if (promptsList) {
        if (t.windows && t.windows.length > 0) {
            let html = '';
            t.windows.forEach(function (w, i) {
                const prompt = (t.prompts && t.prompts[i]) ? t.prompts[i] : '';
                const statusText = prompt ? 'ГОТОВО' : 'Ожидание';
                const statusCls = prompt ? 'text-[#10B981]' : 'text-yellow-500/50';
                html += `
                    <div id="overlay-prompt-card-${i}" class="bg-[#11111a] border border-[#10B981]/10 rounded-xl p-3 flex flex-col gap-2 shrink-0">
                        <div class="flex justify-between items-center">
                            <span class="text-[10px] font-bold text-[#10B981] uppercase tracking-widest">Окно ${i + 1} (${w.start_time} - ${w.end_time})</span>
                            <span id="overlay-prompt-status-${i}" class="text-[10px] uppercase font-bold ${statusCls}">${statusText}</span>
                        </div>
                        <textarea id="overlay-prompt-text-${i}" class="overlay-input w-full h-20 text-[11px] resize-none ${prompt ? '' : 'pointer-events-none opacity-50'} custom-scrollbar">${prompt}</textarea>
                    </div>
                `;
            });
            promptsList.innerHTML = html;
        } else {
            promptsList.innerHTML = `
                <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div class="text-white/10 text-center font-bold uppercase tracking-widest text-sm flex flex-col items-center gap-2">
                        <span class="material-symbols-outlined text-4xl">inventory_2</span>
                        Здесь появятся результаты
                    </div>
                </div>
            `;
        }
    }

    // 🔥 Прогресс-бар и статус из состояния вкладки
    const progFill = document.getElementById('overlay-progress-fill');
    const progText = document.getElementById('overlay-progress-text');
    const statusEl = document.getElementById('overlay-global-status');
    if (progFill) progFill.style.width = (t.progress || 0) + '%';
    if (progText) progText.innerText = (t.progress || 0) + '%';
    if (statusEl) {
        statusEl.innerText = t.status || 'Ожидание...';
        statusEl.className = t.statusClass || 'text-white font-bold';
    }

    // Токены и стоимость
    const tokensEl = document.getElementById('overlay-tokens-count');
    const costEl = document.getElementById('overlay-cost-count');
    if (tokensEl) tokensEl.innerText = (t.tokens || 0).toLocaleString();
    if (costEl) costEl.innerText = '$' + (t.cost || 0).toFixed(4);
};

// Применяется ТОЛЬКО если главный чекбокс "Ко всем проектам" включён.
// НИКОГДА не копирует: srtPath, outFolder, promptPath.
// Копирует только: threads (настройку потоков).
// docx управляется отдельным чекбоксом рядом с полем docx.
window.overlayApplyToAll = function () {
    if (!activeTabId || !tabs) return;
    const src = tabs[activeTabId].overlay;
    if (!src) return;

    const applyAllCb = document.getElementById('overlay-apply-all');
    const applyAll = applyAllCb && applyAllCb.checked;
    if (!applyAll) return;

    Object.keys(tabs).forEach(function (id) {
        if (id === activeTabId) return;
        let t = tabs[id];
        if (t.category !== 'image') return;

        if (!t.overlay) {
            t.overlay = {
                srtPath: '', promptPath: '', outFolder: '',
                windows: [], prompts: [],
                subsCount: 0, windowsCount: 0, threads: 20,
                logs: '', progress: 0, tokens: 0, cost: 0,
                status: 'Ожидание...', statusClass: 'text-white font-bold'
            };
        }

        // ✅ Копируем ТОЛЬКО threads
        t.overlay.threads = src.threads;

        // ❌ НЕ копируем: outFolder, srtPath, promptPath
        //    Каждый проект имеет свою папку, свой SRT и свой docx (docx управляется отдельным чекбоксом)
    });
};

window.overlayProviderChanged = function () {
    const t = tabs[activeTabId] && tabs[activeTabId].overlay;
    eel.get_config()(function (conf) {
        const provider = document.getElementById('overlay-provider').value || 'deepseek';
        const key = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : '';
        const model = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : '';
        if (t) {
            t.provider = provider;
            t.apiKey = key;
            t.model = model;
        }
        document.getElementById('overlay-api-key').value = key;
        if (window.renderAiModelOptions) window.renderAiModelOptions("overlay", provider, model, conf);
    });
};

async function overlayBrowseSrt() {
    try {
        const res = await eel.overlay_browse_file("srt")();
        if (res.success && res.path) {
            document.getElementById('overlay-srt-path').value = res.path;

            // 🔥 Автоматически подставляем папку SRT как папку сохранения (если пусто)
            const currentOut = document.getElementById('overlay-output-path').value.trim();
            if (!currentOut) {
                const srtFolder = res.path.substring(0, Math.max(res.path.lastIndexOf('/'), res.path.lastIndexOf('\\')));
                document.getElementById('overlay-output-path').value = srtFolder;
                overlayLog(`Папка сохранения установлена: ${srtFolder}`, "info");
            }

            overlaySaveToTab();
            overlayLog("Загрузка SRT файла...", "info");

            // 🔥 Передаём tab_id для изоляции состояния на бэкенде
            const loadRes = await eel.overlay_load_srt(res.path, activeTabId)();
            if (loadRes.success) {
                const t = tabs[activeTabId].overlay;
                t.subsCount = loadRes.total_subs || 0;
                t.windowsCount = loadRes.windows_count || 0;
                overlaySyncFromTab();
                overlayLog(`SRT загружен: ${loadRes.windows_count} окон`, "success");
            } else {
                overlayLog("Ошибка парсинга SRT: " + loadRes.error, "error");
            }
        }
    } catch (e) {
        console.error(e);
    }
}

async function overlayBrowseOutputFolder() {
    try {
        const res = await eel.overlay_browse_folder()();
        if (res.success && res.path) {
            document.getElementById('overlay-output-path').value = res.path;
            overlaySaveToTab();
            overlayLog(`Выбрана папка: ${res.path}`, "info");
        }
    } catch (e) {
        console.error(e);
    }
}

async function overlayBrowsePromptDocx() {
    try {
        const res = await eel.overlay_browse_file("docx")();
        if (res.success && res.path) {
            document.getElementById('overlay-prompt-path').value = res.path;
            overlaySaveToTab();
            overlayLog(`Выбран файл промпта: ${res.path}`, "success");

            // 🔥 Если галочка рядом с docx включена — копируем ко всем проектам
            const docxApplyCb = document.getElementById('overlay-docx-apply-all');
            if (docxApplyCb && docxApplyCb.checked) {
                overlayPropagateDocx(res.path);
                overlayLog(`✓ Системный промпт применён ко всем проектам Image Factory`, "info");
            }
        }
    } catch (e) {
        console.error(e);
    }
}

// 🔥 Копирует только docx во все image-проекты
function overlayPropagateDocx(docxPath) {
    if (!tabs) return;
    Object.keys(tabs).forEach(function (id) {
        const t = tabs[id];
        if (t.category !== 'image') return;
        if (!t.overlay) {
            t.overlay = {
                srtPath: '', promptPath: '', outFolder: '',
                windows: [], prompts: [],
                subsCount: 0, windowsCount: 0, threads: 20,
                logs: '', progress: 0, tokens: 0, cost: 0,
                status: 'Ожидание...', statusClass: 'text-white font-bold'
            };
        }
        t.overlay.promptPath = docxPath;
    });
}

async function startOverlayAutoProcess() {
    overlaySaveToTab();
    const tab = tabs[activeTabId].overlay;

    const key = document.getElementById('overlay-api-key').value.trim();
    const provider = document.getElementById('overlay-provider').value || 'deepseek';
    const model = document.getElementById('overlay-model').value || '';
    if (!key) return alert("Введите API ключ выбранного AI-провайдера!");
    if (!tab.srtPath) return alert("Выберите SRT файл!");
    if (!tab.promptPath) return alert("Выберите файл .docx, .txt или .md с инструкциями!");
    if (!tab.outFolder) return alert("Выберите папку для сохранения!");

    const btn = document.getElementById('btn-start-overlay-auto');
    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-sm">sync</span> Работаем...';

    document.getElementById('overlay-global-status').innerText = 'В процессе...';
    document.getElementById('overlay-global-status').className = 'text-yellow-400';
    tab.status = 'В процессе...';
    tab.statusClass = 'text-yellow-400';

    const oFill = document.getElementById('overlay-progress-fill');
    const oText = document.getElementById('overlay-progress-text');
    if (oFill) oFill.style.width = '0%';
    if (oText) oText.innerText = '0%';

    let totalTokens = 0;
    let totalCost = 0.0;
    const PRICE_INPUT_1M = 0.14;
    const PRICE_OUTPUT_1M = 0.28;

    document.getElementById('overlay-prompts-list').innerHTML = '';

    try {
        const keyRes = await eel.overlay_validate_key(key, provider, model)();
        if (!keyRes.valid) throw new Error("Неверный ключ API: " + (keyRes.error || ""));
        overlayLog(`AI provider: ${keyRes.provider_label || provider} | model: ${keyRes.model || model}`, "info");

        overlayLog("Отправка системного промпта...", "info");
        const promptRes = await eel.overlay_load_system_prompt(tab.promptPath, "prompts")();
        if (!promptRes.success) throw new Error("Не удалось загрузить файл промпта: " + promptRes.error);

        const loadRes = await eel.overlay_load_srt(tab.srtPath, activeTabId)();
        if (!loadRes.success) throw new Error("Ошибка SRT: " + loadRes.error);

        const winRes = await eel.overlay_get_windows(activeTabId)();
        if (!winRes.success) throw new Error("Ошибка окон: " + winRes.error);

        tab.windows = winRes.windows;
        overlayLog(`Найдено ${tab.windows.length} окон для генерации`, "info");

        let htmlList = '';
        tab.windows.forEach((w, i) => {
            htmlList += `
                <div id="overlay-prompt-card-${i}" class="bg-[#11111a] border border-[#10B981]/10 rounded-xl p-3 flex flex-col gap-2 shrink-0">
                    <div class="flex justify-between items-center">
                        <span class="text-[10px] font-bold text-[#10B981] uppercase tracking-widest">Окно ${i + 1} (${w.start_time} - ${w.end_time})</span>
                        <span id="overlay-prompt-status-${i}" class="text-[10px] uppercase font-bold text-yellow-500/50">Ожидание</span>
                    </div>
                    <textarea id="overlay-prompt-text-${i}" class="overlay-input w-full h-20 text-[11px] resize-none pointer-events-none opacity-50 custom-scrollbar" placeholder="..."></textarea>
                </div>
            `;
        });
        document.getElementById('overlay-prompts-list').innerHTML = htmlList;

        const total = tab.windows.length;
        let done = 0;
        let MAX_THREADS = parseInt(tab.threads) || 20;

        const currentTabForGen = activeTabId;  // Фиксируем таб на время генерации
        const fetchWithRetry = async (windowIdx, retries = 3) => {
            for (let r = 0; r <= retries; r++) {
                const res = await eel.overlay_generate_prompt(windowIdx, currentTabForGen)();
                if (res && res.success) return res;
                if (r < retries) {
                    const waitTime = (r + 1) * 2000;
                    overlayLog(`⚠️ Окно ${windowIdx + 1}: Ошибка сервера, ждем ${waitTime / 1000} сек...`, "warning");
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                } else return res;
            }
        };

        for (let i = 0; i < total; i += MAX_THREADS) {
            const batch = [];
            for (let j = 0; j < MAX_THREADS && (i + j) < total; j++) {
                const idx = i + j;
                document.getElementById(`overlay-prompt-status-${idx}`).innerText = "ГЕНЕРАЦИЯ...";
                document.getElementById(`overlay-prompt-status-${idx}`).className = "text-[10px] font-bold text-yellow-400 animate-pulse";

                const req = fetchWithRetry(idx).then(promptRes => {
                    if (promptRes && promptRes.success) {
                        const ta = document.getElementById(`overlay-prompt-text-${idx}`);
                        ta.value = promptRes.prompt;
                        ta.classList.remove('opacity-50', 'pointer-events-none');

                        document.getElementById(`overlay-prompt-status-${idx}`).innerText = "ГОТОВО";
                        document.getElementById(`overlay-prompt-status-${idx}`).className = "text-[10px] font-bold text-[#10B981]";

                        let tIn = promptRes.tokens_in || 0;
                        let tOut = promptRes.tokens_out || 0;
                        totalTokens += (tIn + tOut);
                        totalCost += (tIn / 1000000 * PRICE_INPUT_1M) + (tOut / 1000000 * PRICE_OUTPUT_1M);

                        document.getElementById('overlay-tokens-count').innerText = totalTokens.toLocaleString();
                        document.getElementById('overlay-cost-count').innerText = "$" + totalCost.toFixed(4);

                        // 🔥 Сохраняем промпт в состояние вкладки
                        if (!tab.prompts) tab.prompts = [];
                        tab.prompts[idx] = promptRes.prompt;
                    } else {
                        document.getElementById(`overlay-prompt-status-${idx}`).innerText = "ОШИБКА";
                        document.getElementById(`overlay-prompt-status-${idx}`).className = "text-[10px] font-bold text-red-500";
                    }
                    done++;
                    let pct = Math.round((done / total) * 100);
                    const pf = document.getElementById('overlay-progress-fill');
                    const pt = document.getElementById('overlay-progress-text');
                    if (pf) pf.style.width = pct + '%';
                    if (pt) pt.innerText = pct + '%';

                    // 🔥 Сохраняем прогресс и статистику в состояние вкладки
                    tab.progress = pct;
                    tab.tokens = totalTokens;
                    tab.cost = totalCost;
                });
                batch.push(req);
            }
            await Promise.all(batch);
        }

        // Экспорт
        let outFilePath = tab.outFolder;
        if (!outFilePath.endsWith('.txt')) {
            outFilePath = outFilePath.replace(/\\/g, '/');
            if (!outFilePath.endsWith('/')) outFilePath += '/';
            outFilePath += 'prompts_export.txt';
        }

        const expRes = await eel.overlay_export_prompts(outFilePath, currentTabForGen)();
        if (expRes.success) {
            overlayLog(`🎉 Промпты успешно сохранены!`, "success");
            document.getElementById('overlay-global-status').innerText = 'Завершено';
            document.getElementById('overlay-global-status').className = 'text-[#10B981] font-bold';
            tab.status = 'Завершено';
            tab.statusClass = 'text-[#10B981] font-bold';
        } else {
            overlayLog(`❌ Ошибка сохранения: ${expRes.error}`, "error");
        }

    } catch (err) {
        console.error(err);
        overlayLog(err.message, "error");
        document.getElementById('overlay-global-status').innerText = 'Ошибка';
        document.getElementById('overlay-global-status').className = 'text-red-400 font-bold';
        tab.status = 'Ошибка';
        tab.statusClass = 'text-red-400 font-bold';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-symbols-outlined">rocket_launch</span> НАЧАТЬ АВТОМАТИЗАЦИЮ';
    }
}

async function updateOverlayPrompt(idx, newText) {
    try {
        await eel.overlay_update_prompt(idx, newText)();
        overlayLog(`Промпт #${idx + 1} изменен вручную. Рекомендуется повторный экспорт.`, "warning");
    } catch (e) { }
}

window.copyOverlayLog = function () {
    const logContainer = document.getElementById('overlay-log-container');
    if (!logContainer) return;
    const text = logContainer.innerText; // Получаем чистый текст без html тегов
    navigator.clipboard.writeText(text);
    overlayLog("Лог скопирован в буфер обмена.", "info");
};

window.downloadOverlayLog = function () {
    const logContainer = document.getElementById('overlay-log-container');
    if (!logContainer) return;
    const text = logContainer.innerText;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ai_overlay_log.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    overlayLog("Начато скачивание файла логов.", "info");
};

window.showOverlayStub = function (element) { showOverlayPage(); };
window.showOverlayPage = showOverlayPage;
window.overlayBrowseSrt = overlayBrowseSrt;
window.overlayBrowseOutputFolder = overlayBrowseOutputFolder;
window.overlaySaveKey = overlaySaveKey;
window.startOverlayAutoProcess = startOverlayAutoProcess;

// === "КО ВСЕМ ПРОЕКТАМ" для Image Overlay ===
window.overlayToggleApplyAll = function () {
    overlaySaveToTab();
};

// === ЗАГРУЗИТЬ ПАПКУ С SRT (Рекурсивно) ===
window.overlayLoadFolder = async function () {
    try {
        const folderRes = await eel.overlay_browse_folder()();
        if (!folderRes.success) {
            if (folderRes.error !== "Отменено пользователем") overlayLog("Ошибка: " + folderRes.error, "error");
            return;
        }
        if (!folderRes.path) return;

        overlayLog(`Сканирую папку (и все подпапки) на наличие .srt...`, "info");
        const res = await eel.overlay_scan_srt_folder(folderRes.path)();
        if (!res.success) return overlayLog("Ошибка сканирования: " + res.error, "error");

        if (!res.files || res.files.length === 0) {
            return overlayLog("В выбранной папке и подпапках нет .srt файлов!", "warning");
        }

        overlayLog(`Найдено ${res.files.length} SRT файлов. Создаю проекты...`, "info");

        let lastTabId = null;

        // Кэшируем настройки текущей вкладки (чтобы скопировать их)
        overlaySaveToTab();
        const currentOverlay = tabs[activeTabId].overlay;
        const applyToAll = document.getElementById('overlay-apply-all').checked;

        for (let filepath of res.files) {
            const filename = filepath.split('/').pop().replace('.srt', '');
            const folderPath = filepath.substring(0, filepath.lastIndexOf('/'));

            const newTabId = createTab(null, filename, 'image');
            const newOverlay = tabs[newTabId].overlay;

            // SRT — из найденного файла
            newOverlay.srtPath = filepath;

            // 🔥 outFolder — ВСЕГДА из папки SRT (индивидуально для каждого проекта)
            newOverlay.outFolder = folderPath;

            // docx копируем только если галочка "Ко всем" рядом с docx включена
            const docxApplyCb = document.getElementById('overlay-docx-apply-all');
            const docxApplyAll = docxApplyCb && docxApplyCb.checked;
            newOverlay.promptPath = (docxApplyAll && currentOverlay.promptPath) ? currentOverlay.promptPath : '';
            newOverlay.provider = currentOverlay.provider || 'deepseek';
            newOverlay.model = currentOverlay.model || '';
            newOverlay.apiKey = currentOverlay.apiKey || '';

            // threads — копируем если галочка включена, иначе дефолт
            newOverlay.threads = applyToAll ? currentOverlay.threads : 20;

            lastTabId = newTabId;
        }

        if (lastTabId) {
            switchTab(lastTabId);
            renderTabs();

            const loadRes = await eel.overlay_load_srt(tabs[lastTabId].overlay.srtPath, lastTabId)();
            if (loadRes.success) {
                tabs[lastTabId].overlay.subsCount = loadRes.total_subs || 0;
                tabs[lastTabId].overlay.windowsCount = loadRes.windows_count || 0;
                overlaySyncFromTab();
                overlayLog(`Последний SRT загружен: ${loadRes.windows_count} окон`, "success");
            }
        }

        overlayLog(`Создано ${res.files.length} проектов из папки`, "success");
    } catch (e) {
        console.error(e);
        overlayLog("Критическая ошибка: " + e, "error");
    }
};

// === ЗАПУСК ВСЕХ ПРОЕКТОВ ПАРАЛЛЕЛЬНО ===
window.startOverlayAllProjects = async function () {
    overlaySaveToTab();

    // Собираем все image-проекты с готовыми настройками
    const imageTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        if (!t || t.category !== 'image') return false;
        const o = t.overlay;
        if (!o) return false;
        return o.srtPath && o.promptPath && o.outFolder && o.apiKey;
    });

    if (imageTabs.length === 0) {
        return alert("Нет готовых проектов!\nКаждый проект должен иметь: SRT, файл промпта (.docx / .txt / .md) и папку сохранения.");
    }

    const key = document.getElementById('overlay-api-key').value.trim();
    const provider = document.getElementById('overlay-provider').value || 'deepseek';
    const model = document.getElementById('overlay-model').value || '';
    if (!key) return alert("Введите API ключ выбранного AI-провайдера!");

    const btnAll = document.getElementById('btn-start-overlay-all');
    const btnThis = document.getElementById('btn-start-overlay-auto');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-base">sync</span> Запуск...';
    }
    if (btnThis) btnThis.disabled = true;

    overlayLog(`🚀 Запуск ${imageTabs.length} проектов параллельно...`, "success");

    // Проверяем ключ один раз
    try {
        const keyRes = await eel.overlay_validate_key(key, provider, model)();
        if (!keyRes.valid) {
            alert("Неверный ключ API: " + (keyRes.error || ""));
            if (btnAll) { btnAll.disabled = false; btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">rocket_launch</span> Начать все'; }
            if (btnThis) btnThis.disabled = false;
            return;
        }
    } catch (e) {
        alert("Ошибка проверки ключа: " + e);
        if (btnAll) { btnAll.disabled = false; btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">rocket_launch</span> Начать все'; }
        if (btnThis) btnThis.disabled = false;
        return;
    }

    // Запускаем все проекты параллельно
    const promises = imageTabs.map(tabId => runOverlayForTab(tabId));

    try {
        await Promise.all(promises);
        overlayLog(`✅ Все ${imageTabs.length} проектов завершены!`, "success");
        alert(`Готово! Обработано проектов: ${imageTabs.length}`);
    } catch (e) {
        overlayLog(`❌ Ошибка в batch-режиме: ${e}`, "error");
    } finally {
        if (btnAll) { btnAll.disabled = false; btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">rocket_launch</span> Начать все'; }
        if (btnThis) btnThis.disabled = false;
    }
};

// === Выполнение одного проекта (без UI, полностью из стейта) ===
async function runOverlayForTab(tabId) {
    const tabState = tabs[tabId];
    if (!tabState || !tabState.overlay) return;
        const tab = tabState.overlay;

    const projectName = tabState.name || tabId;
    const isActive = () => activeTabId === tabId;

    const logLine = (msg, type = 'info') => {
        const time = new Date().toLocaleTimeString();
        const colors = {
            'info': 'text-white/60',
            'success': 'text-[#10B981]',
            'error': 'text-red-400',
            'warning': 'text-yellow-400'
        };
        const c = colors[type] || colors['info'];
        const entryHtml = `<div class="${c}">[${time}] [${projectName}] ${msg}</div>`;

        if (typeof tab.logs !== 'string') tab.logs = '';
        tab.logs += entryHtml;

        // Если эта вкладка сейчас открыта — пишем и в DOM
        if (isActive()) {
            const lc = document.getElementById('overlay-log-container');
            if (lc) {
                if (lc.innerHTML.includes("Ожидание настройки")) lc.innerHTML = '';
                lc.innerHTML += entryHtml;
                lc.scrollTop = lc.scrollHeight;
            }
        }

        // Глобальный лог (всегда видно в текущем окне)
        overlayLog(`[${projectName}] ${msg}`, type);
    };

    tab.status = 'В процессе...';
    tab.statusClass = 'text-yellow-400';
    tab.progress = 0;
    tab.tokens = 0;
    tab.cost = 0;
    if (!tab.prompts) tab.prompts = [];

    if (isActive()) overlaySyncFromTab();

    let totalTokens = 0;
    let totalCost = 0.0;
    const PRICE_INPUT_1M = 0.14;
    const PRICE_OUTPUT_1M = 0.28;

    try {
        const keyRes = await eel.overlay_validate_key(tab.apiKey || '', tab.provider || 'deepseek', tab.model || '')();
        if (!keyRes.valid) throw new Error("Неверный AI ключ: " + (keyRes.error || ""));

        logLine("Загрузка системного промпта...", "info");
        logLine(`AI provider: ${(tab.provider || 'deepseek')} | model: ${tab.model || ''}`, "info");
        const promptRes = await eel.overlay_load_system_prompt(tab.promptPath, "prompts")();
        if (!promptRes.success) throw new Error("Файл промпта: " + promptRes.error);

        const loadRes = await eel.overlay_load_srt(tab.srtPath, tabId)();
        if (!loadRes.success) throw new Error("SRT: " + loadRes.error);

        const winRes = await eel.overlay_get_windows(tabId)();
        if (!winRes.success) throw new Error("окна: " + winRes.error);

        tab.windows = winRes.windows;
        tab.subsCount = loadRes.total_subs || 0;
        tab.windowsCount = loadRes.windows_count || 0;

        logLine(`Окон для генерации: ${tab.windows.length}`, "info");

        const total = tab.windows.length;
        let done = 0;
        const MAX_THREADS = parseInt(tab.threads) || 20;

        const fetchWithRetry = async (idx, retries = 3) => {
            for (let r = 0; r <= retries; r++) {
                const res = await eel.overlay_generate_prompt(idx, tabId)();
                if (res && res.success) return res;
                if (r < retries) await new Promise(x => setTimeout(x, (r + 1) * 2000));
                else return res;
            }
        };

        for (let i = 0; i < total; i += MAX_THREADS) {
            const batch = [];
            for (let j = 0; j < MAX_THREADS && (i + j) < total; j++) {
                const idx = i + j;
                const p = fetchWithRetry(idx).then(pr => {
                    if (pr && pr.success) {
                        tab.prompts[idx] = pr.prompt;
                        totalTokens += (pr.tokens_in || 0) + (pr.tokens_out || 0);
                        totalCost += (pr.tokens_in || 0) / 1e6 * PRICE_INPUT_1M + (pr.tokens_out || 0) / 1e6 * PRICE_OUTPUT_1M;
                    }
                    done++;
                    const pct = Math.round((done / total) * 100);
                    tab.progress = pct;
                    tab.tokens = totalTokens;
                    tab.cost = totalCost;

                    if (isActive()) {
                        const pf = document.getElementById('overlay-progress-fill');
                        const pt = document.getElementById('overlay-progress-text');
                        const tk = document.getElementById('overlay-tokens-count');
                        const ck = document.getElementById('overlay-cost-count');
                        if (pf) pf.style.width = pct + '%';
                        if (pt) pt.innerText = pct + '%';
                        if (tk) tk.innerText = totalTokens.toLocaleString();
                        if (ck) ck.innerText = '$' + totalCost.toFixed(4);
                    }
                });
                batch.push(p);
            }
            await Promise.all(batch);
        }

        // Экспорт
        let outPath = tab.outFolder.replace(/\\/g, '/');
        if (!outPath.endsWith('.txt')) {
            if (!outPath.endsWith('/')) outPath += '/';
            outPath += 'prompts_export.txt';
        }
        const expRes = await eel.overlay_export_prompts(outPath, tabId)();
        if (expRes.success) {
            logLine(`🎉 Сохранено: ${outPath}`, "success");
            tab.status = 'Завершено';
            tab.statusClass = 'text-[#10B981] font-bold';
        } else {
            logLine(`❌ Ошибка сохранения: ${expRes.error}`, "error");
            tab.status = 'Ошибка';
            tab.statusClass = 'text-red-400 font-bold';
        }
    } catch (err) {
        logLine(err.message || String(err), "error");
        tab.status = 'Ошибка';
        tab.statusClass = 'text-red-400 font-bold';
    }

    if (isActive()) overlaySyncFromTab();
}
