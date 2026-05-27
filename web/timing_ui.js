/* 
* Stocky non Stop — Timing Placer UI
* Автор: Азат | @inomix
*/
// === TIMING PLACER UI ===

function timingPageIsActive() {
    const page = document.getElementById('page-timing');
    if (!page) return false;
    return !page.classList.contains('hidden') && page.style.display !== 'none';
}

let activeTimingTabId = "default";

// Показ страницы Timing Placer (вызывается из меню)
function showTimingPage(el) {
    ['page-download', 'page-render', 'page-overlay', 'page-timing', 'page-composer', 'page-voicer', 'page-prompter'].forEach(id => {
        const e = document.getElementById(id);
        if (e) { e.classList.add('hidden'); e.style.display = 'none'; }
    });
    const target = document.getElementById('page-timing');
    if (target) {
        target.classList.remove('hidden');
        target.style.display = 'flex';
    }

    document.querySelectorAll('.submenu-item, .imgfactory-submenu-item, .voicer-submenu-item').forEach(x => {
        x.classList.remove('active', 'active-overlay', 'active-timing', 'active-composer', 'active-voicer');
    });
    if (el) el.classList.add('active-timing');

    // Авто-раскрытие Image Factory подменю
    const imgSubmenu = document.getElementById('imgfactory-submenu');
    const imgArrow = document.getElementById('imgfactory-arrow');
    if (imgSubmenu && !imgSubmenu.classList.contains('open')) {
        imgSubmenu.classList.add('open');
        if (imgArrow) imgArrow.textContent = 'expand_more';
    }

    currentMode = 'mode-timing';
    if (typeof switchToCategory === 'function') switchToCategory('image');
    if (typeof renderTabs === 'function') renderTabs();
    activeTimingTabId = activeTabId || 'default';

    // Восстанавливаем состояние UI из вкладки
    timingSyncFromTab();

    // Автоподгрузка API-ключа из config.json
    setTimeout(async () => {
        try {
            const conf = await eel.get_config()();
            const keyInput = document.getElementById('timing-api-key');
            const tab = tabs[activeTabId] && tabs[activeTabId].timing ? tabs[activeTabId].timing : null;
            const provider = (tab && tab.provider) || (conf && conf.ai_provider) || "deepseek";
            const aiKey = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : "";
            const aiModel = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : "";
            const providerInput = document.getElementById('timing-provider');
            if (providerInput) providerInput.value = provider;
            if (window.renderAiModelOptions) window.renderAiModelOptions("timing", provider, aiModel, conf);
            if (keyInput && !keyInput.value && aiKey) {
                keyInput.value = aiKey;
                timingSaveToTab();
                timingSaveKey();
            }
            if (keyInput && !keyInput._timingBound) {
                const guarded = () => { if (timingPageIsActive()) timingSaveKey(); };
                keyInput.addEventListener('change', guarded);
                keyInput.addEventListener('blur', guarded);
                keyInput._timingBound = true;
            }
        } catch (e) { }
    }, 200);
}

// === СИНХРОНИЗАЦИЯ И ИЗОЛЯЦИЯ ВКЛАДОК TIMING ===
window.timingSaveToTab = function () {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    const t = tabs[activeTabId].timing;
    if (!t) return;

    t.apiKey = document.getElementById('timing-api-key').value;
    t.provider = document.getElementById('timing-provider').value || 'deepseek';
    t.model = document.getElementById('timing-model').value || '';
    t.threads = parseInt(document.getElementById('timing-threads').value) || 20;
    t.blockSize = parseInt(document.getElementById('timing-block-size').value) || 30;
    t.deadZone = parseInt(document.getElementById('timing-deadzone').value) || 13;
    t.promptsPath = document.getElementById('timing-prompts-path').value;
    t.srtPath = document.getElementById('timing-srt-path').value;
    t.docxPath = document.getElementById('timing-prompt-path').value;

    // 🔥 ДОБАВЛЕНО: Автоматически применяем ко всем вкладкам, если чекбоксы включены
    const applyMain = document.getElementById('timing-apply-all')?.checked; // Главный (для потоков)
    const applyBlockSize = document.getElementById('timing-blocksize-apply-all')?.checked;
    const applyDeadZone = document.getElementById('timing-deadzone-apply-all')?.checked;
    const applyDocx = document.getElementById('timing-docx-apply-all')?.checked;

    Object.keys(tabs).forEach(id => {
        if (id !== activeTabId && tabs[id].category === 'image' && tabs[id].timing) {
            if (applyMain) {
                tabs[id].timing.threads = t.threads;
                tabs[id].timing.apiKey = t.apiKey; // Ключ API логично синхронизировать всегда
            }
            if (applyBlockSize) {
                tabs[id].timing.blockSize = t.blockSize;
            }
            if (applyDeadZone) {
                tabs[id].timing.deadZone = t.deadZone;
            }
            if (applyDocx && t.docxPath) {
                tabs[id].timing.docxPath = t.docxPath;
            }
        }
    });
};

window.timingApplyBlockSizeToAll = function () {
    timingSaveToTab();
};

window.timingApplyDeadZoneToAll = function () {
    timingSaveToTab();
};

window.timingStepDeadZone = function (step) {
    const el = document.getElementById('timing-deadzone');
    if (!el) return;
    let val = parseInt(el.value) || 0;
    val += step;
    if (val < parseInt(el.min)) val = parseInt(el.min);
    if (val > parseInt(el.max)) val = parseInt(el.max);
    el.value = val;
    timingSaveToTab();
};

window.timingSyncFromTab = function () {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return;
    const t = tabs[activeTabId].timing;
    if (!t) return;

    document.getElementById('timing-api-key').value = t.apiKey || '';
    document.getElementById('timing-provider').value = t.provider || 'deepseek';

    // Если у вкладки нет своего ключа — подтягиваем из config.json
    if (!t.apiKey) {
        eel.get_config()(function (conf) {
            const provider = t.provider || (conf && conf.ai_provider) || 'deepseek';
            const aiKey = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : '';
            if (aiKey) {
                t.apiKey = aiKey;
                t.provider = provider;
                t.model = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : '';
                const inp = document.getElementById('timing-api-key');
                if (inp && activeTabId && tabs[activeTabId] && tabs[activeTabId].timing === t) {
                    inp.value = aiKey;
                    if (window.renderAiModelOptions) window.renderAiModelOptions("timing", provider, t.model, conf);
                    if (timingPageIsActive()) timingSaveKey(); // сразу проверяем
                }
            }
        });
    }
    eel.get_config()(function (conf) {
        if (window.renderAiModelOptions) window.renderAiModelOptions("timing", t.provider || 'deepseek', t.model || '', conf);
    });
    document.getElementById('timing-threads').value = t.threads || 20;
    const bsVal = t.blockSize || 30;
    document.getElementById('timing-block-size').value = bsVal;
    const bsLi = document.querySelector(`#timing-blocksize-options li[data-value="${bsVal}"]`);
    if (bsLi) {
        document.getElementById('timing-blocksize-selected-text').textContent = bsLi.textContent;
        document.querySelectorAll('#timing-blocksize-options li').forEach(l => l.classList.remove('selected'));
        bsLi.classList.add('selected');
    }
    document.getElementById('timing-deadzone').value = t.deadZone || 13;
    document.getElementById('timing-prompts-path').value = t.promptsPath || '';
    document.getElementById('timing-srt-path').value = t.srtPath || '';
    document.getElementById('timing-prompt-path').value = t.docxPath || '';

    const logContainer = document.getElementById('timing-log-container');
    if (logContainer) {
        if (typeof t.logs === 'string' && t.logs.length > 0) {
            logContainer.innerHTML = t.logs;
            logContainer.scrollTop = logContainer.scrollHeight;
        } else {
            logContainer.innerHTML = '<div class="italic opacity-30">Ожидание запуска Timing Placer...</div>';
        }
    }

    const wList = document.getElementById('timing-windows-list');
    if (wList) {
        if (typeof t.windowsHtml === 'string' && t.windowsHtml.length > 0) {
            wList.innerHTML = t.windowsHtml;
        } else {
            wList.innerHTML = `<div class="text-white/10 text-center font-bold uppercase tracking-widest text-sm flex flex-col items-center gap-2 py-10"><span class="material-symbols-outlined text-4xl">inventory_2</span>Здесь появятся найденные размещения картинок</div>`;
        }
    }

    const statusEl = document.getElementById('timing-global-status');
    if (statusEl) {
        statusEl.innerText = t.status || 'Ожидание...';
        statusEl.className = t.statusClass || 'text-white font-bold';
    }

    document.getElementById('timing-windows-total').innerText = t.total || 0;
    document.getElementById('timing-matched-count').innerText = t.matched || 0;
    document.getElementById('timing-tokens-count').innerText = t.tokens || 0;
    const costNum = Number(t.cost) || 0;
    document.getElementById('timing-cost-count').innerText = '$' + costNum.toFixed(4);
};

window.timingToggleApplyAll = function () {
    timingSaveToTab();
    const cb = document.getElementById('timing-apply-all');
    if (cb && cb.checked) {
        timingApplyToAll();
    }
};

window.timingApplyToAll = function () {
    if (!activeTabId || !tabs) return;
    const src = tabs[activeTabId].timing;
    if (!src) return;
    const applyAllCb = document.getElementById('timing-apply-all');
    if (!applyAllCb || !applyAllCb.checked) return;
    Object.keys(tabs).forEach(function (id) {
        if (id === activeTabId) return;
        const t = tabs[id];
        if (t.category !== 'image' || !t.timing) return;
        t.timing.threads = src.threads;
    });
};

// === КАСТОМНЫЙ SELECT ДЛЯ TIMING PLACER ===
window.timingToggleSelect = function (selectId) {
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

window.timingSelectOption = function (selectId, li) {
    const sel = document.getElementById(selectId);
    if (!sel) return;

    const value = li.getAttribute('data-value');
    const label = li.textContent;

    // Обновляем текст
    document.getElementById('timing-blocksize-selected-text').textContent = label;

    // Обновляем классы
    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');

    // Пишем в скрытый инпут и сохраняем
    const hidden = document.getElementById('timing-block-size');
    if (hidden) {
        hidden.value = value;
        timingSaveToTab(); // Сохраняем стейт
    }

    // Закрываем меню
    sel.classList.remove('open');
    sel.querySelector('.select-options').classList.add('hidden');
};

// Закрытие при клике мимо
document.addEventListener('click', function (e) {
    if (!e.target.closest('#timing-blocksize-select')) {
        const sel = document.getElementById('timing-blocksize-select');
        if (sel && sel.classList.contains('open')) {
            sel.classList.remove('open');
            sel.querySelector('.select-options').classList.add('hidden');
        }
    }
});

function timingLog(msg, type = 'info', tabId = null) {
    // Если tabId не передан, пишем в активный таб
    const targetTabId = tabId || activeTabId;
    if (!targetTabId || !tabs || !tabs[targetTabId]) return;
    const tab = tabs[targetTabId];
    if (!tab.timing) return;

    let colorClass = "text-white/60";
    if (type === "error") colorClass = "text-red-400";
    if (type === "success") colorClass = "text-green-400";
    if (type === "warning") colorClass = "text-yellow-400";

    const time = new Date().toLocaleTimeString();
    const entry = `<div class="${colorClass} font-mono mb-1">[${time}] ${msg}</div>`;

    if (typeof tab.timing.logs !== 'string') tab.timing.logs = '';
    tab.timing.logs += entry;

    if (activeTabId === targetTabId) {
        const lc = document.getElementById('timing-log-container');
        if (lc) {
            if (lc.innerHTML.includes("Ожидание запуска Timing Placer")) lc.innerHTML = "";
            lc.innerHTML += entry;
            lc.scrollTop = lc.scrollHeight;
        }
    }
}

// === DIALOGS ===
function timingBrowsePrompts() {
    eel.timing_browse_file("prompts")(function (res) {
        if (res.success) {
            document.getElementById('timing-prompts-path').value = res.path;
            timingSaveToTab();
        } else if (res.error !== "Отменено пользователем") alert(res.error);
    });
}

function timingBrowseSrt() {
    eel.timing_browse_file("srt")(function (res) {
        if (res.success) {
            document.getElementById('timing-srt-path').value = res.path;
            timingSaveToTab();
        } else if (res.error !== "Отменено пользователем") alert(res.error);
    });
}

function timingBrowseDocx() {
    eel.timing_browse_file("docx")(function (res) {
        if (res.success) {
            document.getElementById('timing-prompt-path').value = res.path;
            timingSaveToTab();

            const docxApplyCb = document.getElementById('timing-docx-apply-all');
            if (docxApplyCb && docxApplyCb.checked) {
                timingPropagateDocx(res.path);
                timingLog(`✓ Системный промпт применён ко всем проектам Image Factory`, "info");
            }
        } else if (res.error !== "Отменено пользователем") alert(res.error);
    });
}

// Копирует только docx во все image-проекты Timing
function timingPropagateDocx(docxPath) {
    if (!tabs) return;
    Object.keys(tabs).forEach(function (id) {
        const t = tabs[id];
        if (t.category !== 'image') return;
        if (!t.timing) {
            t.timing = {
                apiKey: '', promptsPath: '', srtPath: '', docxPath: '', folderPath: '',
                threads: 20, logs: '', status: 'Ожидание...', statusClass: 'text-white font-bold',
                tokens: 0, cost: 0, total: 0, matched: 0
            };
        }
        t.timing.docxPath = docxPath;
    });
}

window.timingLoadFolder = async function () {
    try {
        const folderRes = await eel.timing_browse_folder()();
        if (!folderRes.success) {
            if (folderRes.error !== "Отменено пользователем") alert(folderRes.error);
            return;
        }
        if (!folderRes.path) return;

        timingLog(`Сканирую папку на наличие пар prompts_export.txt + .srt...`, "info");
        const res = await eel.timing_scan_folder(folderRes.path)();
        if (!res.success) return timingLog("Ошибка сканирования: " + res.error, "error");

        if (!res.pairs || res.pairs.length === 0) {
            return timingLog("В выбранной папке и подпапках нет необходимых пар файлов!", "warning");
        }

        timingLog(`Найдено ${res.pairs.length} пар файлов. Создаю проекты...`, "info");

        let lastTabId = null;
        timingSaveToTab();
        const currentTiming = tabs[activeTabId].timing;
        const applyToAll = document.getElementById('timing-apply-all')?.checked;
        const docxApplyAll = document.getElementById('timing-docx-apply-all')?.checked;

        // 🔥 ДОБАВЛЕНО ЧТЕНИЕ СТАТУСОВ ЧЕКБОКСОВ
        const blockApplyAll = document.getElementById('timing-blocksize-apply-all')?.checked;
        const deadZoneApplyAll = document.getElementById('timing-deadzone-apply-all')?.checked;

        for (let pair of res.pairs) {
            const newTabId = createTab(null, pair.name, 'image');
            const newTiming = tabs[newTabId].timing;

            newTiming.promptsPath = pair.prompts;
            newTiming.srtPath = pair.srt;
            newTiming.folderPath = pair.folder;
            newTiming.apiKey = currentTiming.apiKey;  // ВСЕГДА копируем ключ
            newTiming.provider = currentTiming.provider || 'deepseek';
            newTiming.model = currentTiming.model || '';
            newTiming.threads = applyToAll ? (currentTiming.threads || 20) : 20;
            newTiming.docxPath = (docxApplyAll && currentTiming.docxPath) ? currentTiming.docxPath : '';

            // 🔥 ПРИМЕНЯЕМ РАЗМЕР БЛОКА И МЕРТВУЮ ЗОНУ ПРИ СОЗДАНИИ ВКЛАДКИ
            newTiming.blockSize = blockApplyAll ? (currentTiming.blockSize || 30) : 30;
            newTiming.deadZone = deadZoneApplyAll ? (currentTiming.deadZone || 13) : 13;

            lastTabId = newTabId;
        }

        if (lastTabId) {
            switchTab(lastTabId);
            renderTabs();
            timingSyncFromTab();
            if (timingPageIsActive()) {
                setTimeout(() => { if (document.getElementById('timing-api-key').value) timingSaveKey(); }, 100);
            }
        }

        timingLog(`Создано ${res.pairs.length} проектов из папки`, "success");
    } catch (e) {
        console.error(e);
        timingLog("Критическая ошибка: " + e, "error");
    }
};

// === ЗАПУСК ===

function startTimingSingle() {
    timingSaveToTab();
    const tab = tabs[activeTabId].timing;

    if (!tab.promptsPath || !tab.srtPath) { alert("Выберите prompts_export.txt и .srt!"); return; }
    if (!tab.apiKey) { alert("Заполните API ключ выбранного AI-провайдера!"); return; }

    tab.status = "Запуск...";
    tab.statusClass = "text-yellow-400";
    if (activeTabId) timingSyncFromTab();

    eel.timing_start_single(activeTabId, tab.promptsPath, tab.srtPath, tab.docxPath, tab.apiKey, parseInt(tab.threads) || 20, parseInt(tab.blockSize) || 30, parseInt(tab.deadZone) || 13, tab.provider || 'deepseek', tab.model || '')(function (res) {
        if (res && !res.success) {
            tab.status = "Ошибка";
            tab.statusClass = "text-red-400 font-bold";
            timingLog(`Ошибка запуска: ${res.error}`, "error");
            if (activeTabId) timingSyncFromTab();
        }
    });
}

window.startTimingBatch = async function () {
    timingSaveToTab();

    const ready = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        if (!t || t.category !== 'image') return false;
        const tm = t.timing;
        return tm && tm.promptsPath && tm.srtPath && tm.docxPath && tm.apiKey;
    });

    if (!ready.length) return alert("Нет готовых Timing-проектов! Каждый проект должен иметь: API-ключ, SRT, prompts_export.txt и файл промпта (.docx / .txt / .md)");

    timingLog(`🚀 Запуск ${ready.length} проектов параллельно...`, "success");

    const btnAll = document.getElementById('btn-start-timing-all');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-base">sync</span> Запуск...';
    }

    const promises = ready.map(id => runTimingForTab(id));

    try {
        await Promise.all(promises);
        timingLog(`✅ Все ${ready.length} проектов завершены!`, "success");
        alert(`Готово! Обработано проектов: ${ready.length}`);
    } catch (e) {
        timingLog(`❌ Ошибка в batch-режиме: ${e}`, "error");
    } finally {
        if (btnAll) {
            btnAll.disabled = false;
            btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">rocket_launch</span> Начать все';
        }
    }
};

async function runTimingForTab(tabId) {
    const tabState = tabs[tabId];
    if (!tabState || !tabState.timing) return;
    const tab = tabState.timing;
    const projectName = tabState.name || tabId;

    tab.status = "Запуск...";
    tab.statusClass = "text-yellow-400";
    if (activeTabId === tabId) timingSyncFromTab();

    // Мы используем тот же серверный Promise, поэтому просто вызовем single_worker
    return new Promise((resolve, reject) => {
        // Мы можем подписаться на сообщения 'complete', но eel не дает возвращать promise из асинхронного callback в python.
        // Используем встроенный eel callback чтобы узнать, что он хотя бы стартовал (если он синхронный),
        // Но функция timing_start_single на бекенде - асинхронная внутри себя, она возвращает success почти сразу, а _worker крутится.
        // Для ожидания можно закидывать всё в timing_start_all:
        resolve(); // Ожидание реализовано иначе 
    });
}
// Мы перепишем startTimingBatch, чтобы использовать python'овский timing_start_all
window.startTimingBatch = async function () {
    timingSaveToTab();

    const ready = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        if (!t || t.category !== 'image') return false;
        const tm = t.timing;
        return tm && tm.promptsPath && tm.srtPath && tm.docxPath && tm.apiKey;
    });

    if (!ready.length) return alert("Нет готовых Timing-проектов! Каждый проект должен иметь: API-ключ, SRT, prompts_export.txt и файл промпта (.docx / .txt / .md)");

    timingLog(`🚀 Запуск ${ready.length} проектов параллельно...`, "success");

    const btnAll = document.getElementById('btn-start-timing-all');
    if (btnAll) {
        btnAll.disabled = true;
        btnAll.innerHTML = '<span class="material-symbols-outlined animate-spin !text-base">sync</span> Запуск...';
    }

    const jobs = ready.map(id => {
        const t = tabs[id].timing;
        t.status = "В процессе...";
        t.statusClass = "text-yellow-400";
        if (activeTabId === id) timingSyncFromTab();

        return {
            tab_id: id,
            prompts: t.promptsPath,
            srt: t.srtPath,
            docx: t.docxPath,
            api_key: t.apiKey,
            provider: t.provider || 'deepseek',
            model: t.model || '',
            threads: t.threads || 20,
            block_size: t.blockSize || 30,
            dead_zone: t.deadZone || 13
        };
    });

    try {
        const res = await eel.timing_start_all(jobs)();
        if (!res.success) {
            timingLog(`Ошибка batch запуска: ${res.error}`, "error");
        } else {
            timingLog(`Все ${jobs.length} потоков отправлены на бэкенд. Ожидание завершения в логах!`, "success");
        }
    } catch (e) {
        timingLog(`Ошибка в batch-режиме: ${e}`, "error");
    } finally {
        if (btnAll) {
            btnAll.disabled = false;
            btnAll.innerHTML = '<span class="material-symbols-outlined !text-base">rocket_launch</span> Начать все';
        }
    }
};


function cancelTiming() {
    // В теории эта функция больше не используется для отмены (кнопка удалена), 
    // но если нужно отменить - можно раскомментировать вызов бэкенда
    // document.getElementById('timing-global-status').textContent = "Отмена...";
    // eel.timing_cancel(activeTimingTabId)();
}

eel.expose(timing_progress);
function timing_progress(tabId, data) {
    const tab = tabs[tabId];
    if (!tab || !tab.timing) return;

    if (data.message) {
        let ptype = "info";
        if (data.status === "error") ptype = "error";
        if (data.status === "success") ptype = "success";
        if (data.status === "info" && data.message.includes("Окно")) ptype = "warning";

        timingLog(data.message, ptype, tabId);

        if (data.message && data.message.includes('matched ID=')) {
            const m = data.message.match(/\[WINDOW (\d+)\] matched ID=(\d+) start=([^ ]+) end=([^ ]+) phrase='(.+)'/);
            if (m) {
                const cardHtml = `
                    <div class="bg-[#11111a] border border-[#F59E0B]/20 rounded-xl p-3 flex flex-col gap-1 shrink-0">
                        <div class="flex justify-between items-center">
                            <span class="text-[10px] font-bold text-[#F59E0B] uppercase tracking-widest">🖼 Картинка #${m[2]} (Окно ${m[1]})</span>
                            <span class="text-[10px] text-white/40 font-mono">${m[3]} → ${m[4]}</span>
                        </div>
                        <div class="text-[11px] text-white/60 italic">«${m[5]}»</div>
                    </div>
                `;

                if (typeof tab.timing.windowsHtml !== 'string') tab.timing.windowsHtml = '';
                tab.timing.windowsHtml += cardHtml;

                if (activeTabId === tabId) {
                    const list = document.getElementById('timing-windows-list');
                    if (list) {
                        if (list.querySelector('.text-white\\/10')) list.innerHTML = '';
                        list.insertAdjacentHTML('beforeend', cardHtml);
                        list.scrollTop = list.scrollHeight;
                    }
                }
            }
        }
    }

    if (data.tokens !== undefined) tab.timing.tokens = data.tokens;
    if (data.cost !== undefined) tab.timing.cost = data.cost;
    if (data.total !== undefined) tab.timing.total = data.total;
    if (data.matched !== undefined) tab.timing.matched = data.matched;

    if (data.message && (data.message.includes("Завершено") || data.message.includes("успешно завершена"))) {
        tab.timing.status = "Готово!";
        tab.timing.statusClass = "text-[#10B981] font-bold";
    }

    if (activeTabId === tabId) timingSyncFromTab();
}

// === Экспорт функций в window (нужно для onclick в HTML) ===
window.showTimingPage = showTimingPage;
window.timingBrowsePrompts = timingBrowsePrompts;
window.timingBrowseSrt = timingBrowseSrt;
window.timingBrowseDocx = timingBrowseDocx;
window.timingLoadFolder = timingLoadFolder;
window.startTimingSingle = startTimingSingle;
window.startTimingBatch = startTimingBatch;
window.cancelTiming = cancelTiming;
window.timingSaveToTab = timingSaveToTab;
window.timingSyncFromTab = timingSyncFromTab;
window.timingToggleApplyAll = timingToggleApplyAll;

window.copyTimingLog = function () {
    const lc = document.getElementById('timing-log-container');
    if (!lc) return;
    navigator.clipboard.writeText(lc.innerText);
    timingLog("Лог скопирован в буфер обмена.", "info");
};

window.downloadTimingLog = function () {
    const lc = document.getElementById('timing-log-container');
    if (!lc) return;
    const blob = new Blob([lc.innerText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'timing_placer_log.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
};

async function timingSaveKey() {
    if (!timingPageIsActive()) return;
    const keyInput = document.getElementById('timing-api-key');
    const key = keyInput.value.trim();
    const provider = document.getElementById('timing-provider').value || 'deepseek';
    const model = document.getElementById('timing-model').value || '';
    if (!key) {
        keyInput.style.borderColor = 'rgba(255,255,255,0.05)';
        return;
    }
    keyInput.style.borderColor = '#F59E0B'; // жёлтый — проверка
    try {
        const keyRes = await eel.overlay_validate_key(key, provider, model)();
        if (keyRes.valid) {
            keyInput.style.borderColor = '#10B981'; // зелёный
            timingLog(`AI подключен: ${keyRes.provider_label || provider} / ${keyRes.model || model}`, "success");
            timingSaveToTab();
        } else {
            keyInput.style.borderColor = '#EF4444'; // красный
            timingLog("Ошибка ключа API: " + (keyRes.error || 'недействителен'), "error");
        }
    } catch (e) {
        keyInput.style.borderColor = '#EF4444';
        timingLog("Ошибка проверки ключа: " + e, "error");
    }
}
window.timingSaveKey = timingSaveKey;
window.timingProviderChanged = function () {
    const t = tabs[activeTabId] && tabs[activeTabId].timing;
    eel.get_config()(function (conf) {
        const provider = document.getElementById('timing-provider').value || 'deepseek';
        const key = window.getAiKeyByProvider ? window.getAiKeyByProvider(conf, provider) : '';
        const model = window.getAiModelByProvider ? window.getAiModelByProvider(conf, provider) : '';
        if (t) {
            t.provider = provider;
            t.apiKey = key;
            t.model = model;
        }
        document.getElementById('timing-api-key').value = key;
        if (window.renderAiModelOptions) window.renderAiModelOptions("timing", provider, model, conf);
    });
};
