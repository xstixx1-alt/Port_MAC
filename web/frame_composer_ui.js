/* 
* Stocky non Stop — Frame Composer UI
* Автор: Азат | Telegram: @inomix | Email: inomixx@gmail.com
*/
// === FRAME COMPOSER UI ===

let composerLayerIdCounter = 1;
window.composerRenderingTabId = null;

function showComposerPage(el) {
    ['page-download', 'page-render', 'page-overlay', 'page-timing', 'page-composer', 'page-voicer', 'page-prompter'].forEach(id => {
        const e = document.getElementById(id);
        if (e) { e.classList.add('hidden'); e.style.display = 'none'; }
    });

    const target = document.getElementById('page-composer');
    if (target) {
        target.classList.remove('hidden');
        target.style.display = 'flex';
    }

    document.querySelectorAll('.submenu-item, .imgfactory-submenu-item, .voicer-submenu-item').forEach(i => {
        i.classList.remove('active', 'active-overlay', 'active-timing', 'active-composer', 'active-voicer');
    });
    if (el) el.classList.add('active-composer');

    const imgSubmenu = document.getElementById('imgfactory-submenu');
    const imgArrow = document.getElementById('imgfactory-arrow');
    if (imgSubmenu && !imgSubmenu.classList.contains('open')) {
        imgSubmenu.classList.add('open');
        if (imgArrow) imgArrow.textContent = 'expand_more';
    }

    currentMode = 'mode-composer';
    if (typeof switchToCategory === 'function') switchToCategory('image');
    if (typeof renderTabs === 'function') renderTabs();

    composerLoadGpuInfo();
    composerSyncFromTab();
    composerRenderLayers();
}

async function composerLoadGpuInfo(retryCount = 0) {
    if (window.__cachedGpuInfo) {
        updateComposerGpuUI(window.__cachedGpuInfo);
        return;
    }
    const MAX_RETRIES = 10;
    const RETRY_DELAY_MS = 500;
    try {
        if (!window.eel || !window.eel.composer_get_gpu_info) {
            if (retryCount < MAX_RETRIES) {
                setTimeout(() => composerLoadGpuInfo(retryCount + 1), RETRY_DELAY_MS);
                return;
            }
            updateComposerGpuUI({ type: 'cpu', name: 'Только Процессор (CPU)' });
            return;
        }
        const info = await eel.composer_get_gpu_info()();
        updateComposerGpuUI(info);
    } catch (e) {
        if (retryCount < MAX_RETRIES) {
            setTimeout(() => composerLoadGpuInfo(retryCount + 1), RETRY_DELAY_MS);
        } else {
            updateComposerGpuUI({ type: 'cpu', name: 'Только Процессор (CPU)' });
        }
    }
}

function updateComposerGpuUI(info) {
    const nameEl = document.getElementById('composer-gpu-name');
    const techEl = document.getElementById('composer-gpu-tech');
    const iconBg = document.getElementById('composer-gpu-icon-bg');
    const icon = document.getElementById('composer-gpu-icon');
    const block = document.getElementById('composer-gpu-block');
    if (!nameEl || !block) return;
    nameEl.innerText = info.name || "CPU";
    if (info.type === 'nvidia') {
        techEl.innerText = "🔥 CUDA / NVENC АКТИВНА";
        techEl.className = "text-[10px] text-[#22c55e] mt-0.5 font-mono uppercase tracking-widest font-bold";
        iconBg.className = "w-9 h-9 rounded-full bg-[#22c55e]/15 flex items-center justify-center border border-[#22c55e]/50 shadow-[0_0_12px_rgba(34,197,94,0.3)]";
        icon.className = "material-symbols-outlined !text-base text-[#22c55e]";
        icon.innerText = "developer_board";
        block.className = "px-4 py-2.5 bg-[#0d1f15] border border-[#22c55e]/30 rounded-xl flex items-center gap-3 transition-all duration-300 min-w-[280px] shadow-[0_0_15px_rgba(34,197,94,0.08)]";
    } else if (info.type === 'amd') {
        techEl.innerText = "🔴 AMF / RADEON АКТИВНА";
        techEl.className = "text-[10px] text-[#ef4444] mt-0.5 font-mono uppercase tracking-widest font-bold";
        iconBg.className = "w-9 h-9 rounded-full bg-[#ef4444]/15 flex items-center justify-center border border-[#ef4444]/50 shadow-[0_0_12px_rgba(239,68,68,0.3)]";
        icon.className = "material-symbols-outlined !text-base text-[#ef4444]";
        icon.innerText = "developer_board";
        block.className = "px-4 py-2.5 bg-[#1f0d0d] border border-[#ef4444]/30 rounded-xl flex items-center gap-3 transition-all duration-300 min-w-[280px] shadow-[0_0_15px_rgba(239,68,68,0.08)]";
    } else if (info.type === 'intel') {
        techEl.innerText = "🔵 QSV / INTEL АКТИВНА";
        techEl.className = "text-[10px] text-[#3b82f6] mt-0.5 font-mono uppercase tracking-widest font-bold";
        iconBg.className = "w-9 h-9 rounded-full bg-[#3b82f6]/15 flex items-center justify-center border border-[#3b82f6]/50 shadow-[0_0_12px_rgba(59,130,246,0.3)]";
        icon.className = "material-symbols-outlined !text-base text-[#3b82f6]";
        icon.innerText = "developer_board";
        block.className = "px-4 py-2.5 bg-[#0d141f] border border-[#3b82f6]/30 rounded-xl flex items-center gap-3 transition-all duration-300 min-w-[280px] shadow-[0_0_15px_rgba(59,130,246,0.08)]";
    } else {
        techEl.innerText = "🐢 ТОЛЬКО CPU (libx264)";
        techEl.className = "text-[10px] text-white/50 mt-0.5 font-mono uppercase tracking-widest font-bold";
        iconBg.className = "w-9 h-9 rounded-full bg-white/10 flex items-center justify-center border border-white/20";
        icon.className = "material-symbols-outlined !text-base text-white/50";
        icon.innerText = "memory";
        block.className = "px-4 py-2.5 bg-[#11111d] border border-[#2a2a3e] rounded-xl flex items-center gap-3 transition-all duration-300 min-w-[280px]";
    }
}

function _getComposer() {
    if (!activeTabId || !tabs || !tabs[activeTabId]) return null;
    var tab = tabs[activeTabId];
    if (!tab.composer) {
        tab.composer = {
            video: '', images_folder: '', video_info_text: '', images_info_text: '',
            isRendering: false, progress: 0, eta: '--:--', fps: '-- FPS',
            logs: '', lastLogHeader: 'Ожидание запуска рендера...',
            layers: [{ id: 1, size: 101, position: 'center', plan: '', exclude: '' }],
            settings: { speed: 'ultrafast', codec: 'auto', output: '' },
            layerIdCounter: 2,
            subs: {
                addSubs: false, subsPath: '', subsFont: 'Arial.ttf',
                subsFontSize: 24, subsColor: '#ffffff', subsStroke: 3,
                subsStrokeColor: '#000000', subsPosY: 85, applyAll: true,
                subsDelay: 1.5
            }
        };
    }
    if (!tab.composer.subs) {
        tab.composer.subs = {
            addSubs: false, subsPath: '', subsFont: 'Arial.ttf',
            subsFontSize: 24, subsColor: '#ffffff', subsStroke: 3,
            subsStrokeColor: '#000000', subsPosY: 85, applyAll: true,
            subsDelay: 1.5
        };
    }
    return tab.composer;
}

function composerSyncFromTab() {
    var comp = _getComposer();
    if (!comp) return;

    var vp = document.getElementById('composer-video-path');
    var imf = document.getElementById('composer-images-folder');
    var co = document.getElementById('composer-output');
    var speed = document.getElementById('composer-speed');
    var codec = document.getElementById('composer-codec');

    if (vp) vp.value = comp.video || '';
    if (imf) imf.value = comp.images_folder || '';
    if (co) co.value = comp.settings.output || '';
    if (speed) speed.value = comp.settings.speed || 'fast';
    if (codec) codec.value = comp.settings.codec || 'auto';

    // === СУБТИТРЫ ===
    const s = comp.subs;
    const dCheck = document.getElementById('comp-add-subs-checkbox');
    if (dCheck) dCheck.checked = s.addSubs;

    document.getElementById('comp-subs-path').value = s.subsPath || '';
    document.getElementById('comp-subs-font-hidden').value = s.subsFont || 'Arial.ttf';
    document.getElementById('comp-font-selected-text').textContent = (s.subsFont || 'Arial.ttf').replace('.ttf', '').replace('.otf', '');

    document.getElementById('comp-subs-font-size').value = s.subsFontSize;
    document.getElementById('comp-subs-font-size-slider').value = s.subsFontSize;
    document.getElementById('comp-subs-pos-y').value = s.subsPosY;
    document.getElementById('comp-subs-pos-y-slider').value = s.subsPosY;

    document.getElementById('comp-subs-color').value = s.subsColor;
    document.getElementById('comp-subs-stroke-color').value = s.subsStrokeColor;
    document.getElementById('comp-subs-stroke').value = s.subsStroke;
    document.getElementById('comp-subs-stroke-val').innerText = s.subsStroke + ' px';

    // Синхронизируем задержку
    const sDelay = s.subsDelay !== undefined ? parseFloat(s.subsDelay) : 1.5;
    const dInp = document.getElementById('comp-subs-delay');
    const dSld = document.getElementById('comp-subs-delay-slider');
    if (dInp) dInp.value = sDelay;
    if (dSld) dSld.value = sDelay;

    // Подтягиваем общий чекбокс Apply All для сдвига из главного стейта
    const applyShift = tabs[activeTabId].inputs.shiftApplyAll !== false;
    const compShiftCb = document.getElementById('comp-sync-shift-apply-all');
    if (compShiftCb) compShiftCb.checked = applyShift;

    const applySubsAll = document.getElementById('comp-subs-apply-all');
    if (applySubsAll) applySubsAll.checked = s.applyAll !== false;

    composerToggleSubsUI();

    var vInfo = document.getElementById('composer-video-info');
    var iInfo = document.getElementById('composer-images-info');
    if (vInfo) vInfo.innerText = comp.video_info_text || '';
    if (iInfo) iInfo.innerText = comp.images_info_text || '';

    ['composer-speed-select', 'composer-codec-select'].forEach(selId => {
        const sel = document.getElementById(selId);
        if (!sel) return;
        const targetValue = (selId === 'composer-speed-select') ? (comp.settings.speed || 'fast') : (comp.settings.codec || 'auto');
        const li = sel.querySelector(`li[data-value="${targetValue}"]`);
        if (li) {
            sel.setAttribute('data-value', targetValue);
            sel.querySelector('.composer-select-label').textContent = li.textContent;
            sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
            li.classList.add('selected');
        }
    });

    if (comp.isRendering || window.composerBatchRendering) {
        document.getElementById('composer-render-buttons').classList.add('hidden');
        document.getElementById('composer-cancel-btn').classList.remove('hidden');
        document.getElementById('composer-progress-block').classList.remove('hidden');

        var fill = document.getElementById('composer-progress-fill');
        var pct = document.getElementById('composer-progress-percent');
        var etaEl = document.getElementById('composer-progress-eta');
        var fpsEl = document.getElementById('composer-progress-fps');

        if (fill) fill.style.width = (comp.progress || 0) + '%';
        if (pct) pct.innerText = (comp.progress || 0).toFixed(1) + '%';
        if (etaEl) etaEl.innerText = 'ETA: ' + (comp.eta || '--:--');
        if (fpsEl) fpsEl.innerText = (comp.fps || '-- FPS');
    } else {
        document.getElementById('composer-render-buttons').classList.remove('hidden');
        document.getElementById('composer-cancel-btn').classList.add('hidden');
        document.getElementById('composer-progress-block').classList.add('hidden');
    }

    const logEl = document.getElementById('composer-log');
    const headerEl = document.getElementById('composer-log-header-text');
    if (logEl) logEl.innerHTML = comp.logs || '';
    if (headerEl) headerEl.innerHTML = comp.lastLogHeader || 'Ожидание запуска рендера...';
    const expanded = document.getElementById('composer-log-expanded-content');
    if (expanded) expanded.scrollTop = expanded.scrollHeight;

    composerLayerIdCounter = comp.layerIdCounter || 1;
    composerRenderLayers();
}

function composerSaveToTab() {
    var comp = _getComposer();
    if (!comp) return;

    var vp = document.getElementById('composer-video-path');
    var imf = document.getElementById('composer-images-folder');
    var co = document.getElementById('composer-output');
    var speed = document.getElementById('composer-speed');
    var codec = document.getElementById('composer-codec');

    if (vp) comp.video = vp.value;
    if (imf) comp.images_folder = imf.value;
    if (co) comp.settings.output = co.value;
    if (speed) comp.settings.speed = speed.value;
    if (codec) comp.settings.codec = codec.value;
    comp.layerIdCounter = composerLayerIdCounter;

    // === СУБТИТРЫ ===
    const dCheck = document.getElementById('comp-add-subs-checkbox');
    if (dCheck) {
        comp.subs.addSubs = dCheck.checked;
        comp.subs.subsPath = document.getElementById('comp-subs-path').value;
        comp.subs.subsFont = document.getElementById('comp-subs-font-hidden').value;
        comp.subs.subsFontSize = parseInt(document.getElementById('comp-subs-font-size').value);
        comp.subs.subsColor = document.getElementById('comp-subs-color').value;
        comp.subs.subsStrokeColor = document.getElementById('comp-subs-stroke-color').value;
        comp.subs.subsStroke = parseInt(document.getElementById('comp-subs-stroke').value);
        comp.subs.subsPosY = parseInt(document.getElementById('comp-subs-pos-y').value);
        let sDelayVal = parseFloat(document.getElementById('comp-subs-delay').value);
        comp.subs.subsDelay = !isNaN(sDelayVal) ? sDelayVal : 1.5;
        comp.subs.applyAll = document.getElementById('comp-subs-apply-all').checked;
    }

    var applyAllCb = document.getElementById('composer-apply-all');
    if (applyAllCb && applyAllCb.checked) {
        composerApplyToAll();
    }
}

function composerToggleApplyAll() {
    var cb = document.getElementById('composer-apply-all');
    if (!cb) return;
    if (cb.checked) {
        composerSaveToTab();
        composerApplyToAll();
    }
}

function composerApplyToAll() {
    var comp = _getComposer();
    if (!comp || !tabs || !activeTabId) return;

    Object.keys(tabs).forEach(function (id) {
        if (id === activeTabId) return;
        var t = tabs[id];

        if (t.category !== 'image') return;

        if (!t.composer) {
            t.composer = {
                video: '', images_folder: '', video_info_text: '', images_info_text: '',
                isRendering: false, progress: 0, eta: '--:--', fps: '-- FPS',
                logs: '', lastLogHeader: 'Ожидание запуска рендера...',
                layers: [{ id: 1, size: 101, position: 'center', plan: '', exclude: '' }],
                settings: { speed: 'ultrafast', codec: 'auto', output: '' },
                layerIdCounter: 2,
                subs: { addSubs: false, subsPath: '', subsFont: 'Arial.ttf', subsFontSize: 24, subsColor: '#ffffff', subsStroke: 3, subsStrokeColor: '#000000', subsPosY: 85, applyAll: true, subsDelay: 1.5 }
            };
        }
        t.composer.settings.speed = comp.settings.speed;
        t.composer.settings.codec = comp.settings.codec;

        if (comp.subs.applyAll) {
            t.composer.subs.addSubs = comp.subs.addSubs;
            t.composer.subs.subsPath = comp.subs.subsPath;
            t.composer.subs.subsFont = comp.subs.subsFont;
            t.composer.subs.subsFontSize = comp.subs.subsFontSize;
            t.composer.subs.subsColor = comp.subs.subsColor;
            t.composer.subs.subsStrokeColor = comp.subs.subsStrokeColor;
            t.composer.subs.subsStroke = comp.subs.subsStroke;
            t.composer.subs.subsPosY = comp.subs.subsPosY;
            t.composer.subs.subsDelay = comp.subs.subsDelay;
        }

        if (t.composer.layers.length === 0 && comp.layers.length > 0) {
            t.composer.layers = JSON.parse(JSON.stringify(comp.layers));
        }
    });
}

function composerRenderLayers() {
    var comp = _getComposer();
    var list = document.getElementById('composer-layers-list');
    if (!comp || !list) return;

    if (comp.layers.length === 0) {
        list.innerHTML = '<div class="text-white/30 text-center py-6">Нет слоёв. Добавьте первый.</div>';
        return;
    }

    list.innerHTML = comp.layers.map(function (l, idx) {
        return `
            <div class="bg-black/40 border ${idx === 0 ? 'border-[#EF4444]/30 shadow-[0_0_15px_rgba(239,68,68,0.05)]' : 'border-white/5'} rounded-2xl p-5 relative group" data-layer-id="${l.id}">
                <div class="absolute -left-3 -top-3 w-7 h-7 rounded-xl bg-[#08080c] border ${idx === 0 ? 'border-[#EF4444] text-[#EF4444]' : 'border-white/10 text-white/30'} flex items-center justify-center text-[11px] font-black shadow-lg">${idx + 1}</div>
                <button onclick="composerRemoveLayer(${l.id})" class="absolute right-3 top-3 w-6 h-6 flex items-center justify-center bg-black/40 rounded-lg text-white/20 hover:text-red-400 hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-all"><span class="material-symbols-outlined !text-[14px]">close</span></button>
                
                <div class="grid grid-cols-2 gap-5 mt-1">
                    <div>
                        <label class="text-[9px] font-bold text-white/40 uppercase tracking-widest block mb-2">Масштаб: <span id="size-val-${l.id}" class="text-white">${l.size}%</span></label>
                        <input type="range" min="5" max="110" value="${l.size}" oninput="composerUpdateLayer(${l.id},'size',this.value);document.getElementById('size-val-${l.id}').innerText=this.value+'%'" class="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[#EF4444]">
                    </div>
                    <div>
                        <label class="text-[9px] font-bold text-white/40 uppercase tracking-widest block mb-2">Точка привязки</label>
                        <select onchange="composerUpdateLayer(${l.id},'position',this.value)" class="w-full bg-black/60 border border-white/5 rounded-xl px-3 py-1.5 text-xs text-white focus:ring-1 focus:ring-[#EF4444] shadow-inner">
                            ${['center', 'left_top', 'right_top', 'left_bottom', 'right_bottom'].map(p =>
            `<option value="${p}" ${l.position === p ? 'selected' : ''}>${p.toUpperCase().replace('_', ' ')}</option>`
        ).join('')}
                        </select>
                    </div>
                </div>
                
                <div class="mt-5">
                    <div class="flex items-center justify-between mb-1.5">
                        <label class="text-[9px] font-bold text-white/40 uppercase tracking-widest flex items-center gap-1.5"><span class="material-symbols-outlined !text-[12px] text-[#EF4444]">movie_filter</span> Окна наложения</label>
                        <button onclick="composerLoadPlanFromFile(${l.id})" class="text-[9px] bg-white/5 hover:bg-white/10 text-white/60 px-2 py-1 rounded transition-colors uppercase font-bold tracking-widest shrink-0 border border-white/5 shadow-sm">Загрузить .txt</button>
                    </div>
                    <textarea oninput="composerUpdateLayer(${l.id},'plan',this.value)" class="w-full bg-black/60 border border-white/5 rounded-xl px-4 py-3 font-mono text-[11px] text-[#EF4444] min-h-[70px] custom-scrollbar focus:ring-1 focus:ring-[#EF4444] shadow-inner" placeholder="1;0:05;0:12\n2;0:15;0:20">${l.plan}</textarea>
                </div>
                
                <div class="mt-4">
                    <label class="text-[9px] font-bold text-white/40 uppercase tracking-widest block mb-1.5">🚫 Исключить картинки</label>
                    <input type="text" value="${l.exclude}" oninput="composerUpdateLayer(${l.id},'exclude',this.value)" class="w-full bg-black/60 border border-white/5 rounded-xl px-4 py-2 text-xs text-[#EF4444]/60 focus:ring-1 focus:ring-[#EF4444] shadow-inner placeholder:opacity-40" placeholder="Например: 2,5,7">
                </div>
            </div>
        `;
    }).join('');
}

function composerAddLayer() {
    var comp = _getComposer();
    if (!comp) return;
    comp.layers.push({ id: composerLayerIdCounter++, size: 101, position: 'center', plan: '', exclude: '' });
    comp.layerIdCounter = composerLayerIdCounter;
    composerRenderLayers();
}

function composerRemoveLayer(id) {
    var comp = _getComposer();
    if (!comp) return;
    comp.layers = comp.layers.filter(function (l) { return l.id !== id; });
    composerRenderLayers();
}

function composerUpdateLayer(id, field, value) {
    var comp = _getComposer();
    if (!comp) return;
    var layer = comp.layers.find(function (l) { return l.id === id; });
    if (layer) layer[field] = value;
}

async function composerPickVideo() {
    try {
        var r = await eel.composer_pick_video()();
        if (r.success) {
            var comp = _getComposer();
            const infoText = r.info.width + 'x' + r.info.height + ', ' + r.info.duration + 's';
            if (comp) { comp.video = r.path; comp.video_info_text = infoText; }
            document.getElementById('composer-video-path').value = r.path;
            document.getElementById('composer-video-info').innerText = infoText;
            const outputInput = document.getElementById('composer-output');
            if (outputInput && !outputInput.value.trim()) {
                const videoPath = r.path;
                const lastSlash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
                const dir = lastSlash >= 0 ? videoPath.substring(0, lastSlash + 1) : '';
                const fileName = lastSlash >= 0 ? videoPath.substring(lastSlash + 1) : videoPath;
                const dotIdx = fileName.lastIndexOf('.');
                const baseName = dotIdx > 0 ? fileName.substring(0, dotIdx) : fileName;
                const ext = dotIdx > 0 ? fileName.substring(dotIdx) : '.mp4';
                const autoName = dir + baseName + '_output' + ext;
                outputInput.value = autoName;
                if (comp) comp.settings.output = autoName;
            }
        }
    } catch (e) { console.error('[Composer] Pick video error:', e); }
}

async function composerPickImagesFolder() {
    try {
        var r = await eel.composer_pick_folder()();
        if (r.success) {
            var comp = _getComposer();
            const infoText = 'Найдено картинок: ' + r.count;
            if (comp) { comp.images_folder = r.path; comp.images_info_text = infoText; }
            document.getElementById('composer-images-folder').value = r.path;
            document.getElementById('composer-images-info').innerText = infoText;
        }
    } catch (e) { console.error('[Composer] Pick folder error:', e); }
}

async function composerLoadPlanFromFile(layerId) {
    try {
        let res = await eel.composer_pick_txt_file()();
        if (res && res.success) {
            composerUpdateLayer(layerId, 'plan', res.content);
            composerRenderLayers();
            composerSaveToTab();
        } else if (res && res.error) {
            alert("Ошибка чтения файла: " + res.error);
        }
    } catch (e) { console.error(e); }
}

async function _runComposerRender(tabId) {
    var comp = tabs[tabId].composer;
    if (!comp) return false;

    if (!comp.video) { alert('Выберите видео', "error"); return false; }
    if (!comp.images_folder) { alert('Выберите папку с картинками', "error"); return false; }
    if (comp.layers.length === 0) { alert('Добавьте хотя бы один слой', "error"); return false; }

    // 🔥 ПОДРОБНАЯ ДИАГНОСТИКА В ЛОГ (без DevTools)
    composerLog("════════════════════════════════════════════════════════");
    composerLog("🔍 ДИАГНОСТИКА ПЕРЕД РЕНДЕРОМ:");
    composerLog("════════════════════════════════════════════════════════");
    composerLog(`📁 Проект: ${tabs[tabId].name || tabId}`);
    composerLog(`🎬 Видео: ${comp.video}`);
    composerLog(`🖼️ Папка картинок: ${comp.images_folder}`);
    composerLog(`📊 Количество слоёв: ${comp.layers.length}`);
    composerLog("────────────────────────────────────────────────────────");
    composerLog("📝 СОСТОЯНИЕ СУБТИТРОВ:");

    if (!comp.subs) {
        composerLog(`   ⚠️ ОБЪЕКТ comp.subs ОТСУТСТВУЕТ! Субтитры точно не будут наложены.`);
    } else {
        composerLog(`   • Галочка "Субтитры поверх видео" (addSubs): ${comp.subs.addSubs ? '✅ ВКЛЮЧЕНА' : '❌ ВЫКЛЮЧЕНА'}`);
        composerLog(`   • Файл SRT (subsPath): "${comp.subs.subsPath || '(пусто)'}"`);
        composerLog(`   • Шрифт (subsFont): "${comp.subs.subsFont || 'не задан'}"`);
        composerLog(`   • Размер шрифта: ${comp.subs.subsFontSize || 'не задан'}`);
        composerLog(`   • Цвет текста: ${comp.subs.subsColor || 'не задан'}`);
        composerLog(`   • Цвет обводки: ${comp.subs.subsStrokeColor || 'не задан'}`);
        composerLog(`   • Толщина обводки: ${comp.subs.subsStroke || 'не задан'}`);
        composerLog(`   • Позиция Y: ${comp.subs.subsPosY || 'не задан'}%`);
        composerLog(`   • Сдвиг времени: ${comp.subs.subsDelay !== undefined ? comp.subs.subsDelay : 'не задан'} сек`);

        // Прогноз: будет ли запущен этап 2
        const willRun = comp.subs.addSubs && comp.subs.subsPath;
        if (willRun) {
            composerLog(`   ✅ ПРОГНОЗ: Этап 2 (наложение субтитров) БУДЕТ запущен после рендера картинок.`);
        } else if (comp.subs.addSubs && !comp.subs.subsPath) {
            composerLog(`   ⚠️ ПРОГНОЗ: Галочка включена, но НЕТ файла SRT — этап 2 НЕ запустится!`);
        } else {
            composerLog(`   ℹ️ ПРОГНОЗ: Этап 2 НЕ запустится (галочка субтитров выключена).`);
        }
    }
    composerLog("════════════════════════════════════════════════════════");

    if (comp.subs && comp.subs.addSubs && !comp.subs.subsPath) {
        alert("Вы включили субтитры, но не указали файл (.srt)!\n\nВыберите файл или снимите галочку 'Субтитры поверх видео'.", "error");
        return false;
    }

    var output = document.getElementById('composer-output').value.trim();
    if (!output) {
        const videoPath = comp.video;
        const lastSlash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
        const dir = lastSlash >= 0 ? videoPath.substring(0, lastSlash + 1) : '';
        const fileName = lastSlash >= 0 ? videoPath.substring(lastSlash + 1) : videoPath;
        const dotIdx = fileName.lastIndexOf('.');
        const baseName = dotIdx > 0 ? fileName.substring(0, dotIdx) : fileName;
        const ext = dotIdx > 0 ? fileName.substring(dotIdx) : '.mp4';
        output = dir + baseName + '_output' + ext;
        document.getElementById('composer-output').value = output;
    }

    comp.settings.output = output;
    comp.settings.speed = document.getElementById('composer-speed').value;
    comp.settings.codec = document.getElementById('composer-codec').value;

    var projectData = {
        video: comp.video,
        images_folder: comp.images_folder,
        output: output,
        speed: comp.settings.speed,
        codec: comp.settings.codec,
        global_shift: comp.subs.subsDelay || 0, // Передаем сдвиг в Питон
        layers: comp.layers.map(function (l) {
            return { size: parseInt(l.size), position: l.position, plan: l.plan, exclude: l.exclude };
        })
    };

    for (var i = 0; i < projectData.layers.length; i++) {
        try {
            var check = await eel.composer_validate_plan(projectData.layers[i].plan, projectData.images_folder, projectData.layers[i].exclude)();
            if (!check.success) { alert('⚠️ ОШИБКА В СЛОЕ ' + (i + 1) + ':\n\n' + check.error); return false; }
        } catch (e) { alert('Ошибка валидации плана: ' + e); return false; }
    }

    window.composerRenderingTabId = tabId;
    comp.isRendering = true;
    comp.progress = 0;
    comp.eta = '--:--';
    comp.fps = '-- FPS';
    comp.logs = '';
    comp.lastLogHeader = 'Рендер запущен...';

    if (activeTabId === tabId) composerSyncFromTab();

    try {
        var result = await eel.composer_render(projectData)();

        if (activeTabId === tabId) composerSyncFromTab();

        if (result.success) {
            composerLog("════════════════════════════════════════════════════════");
            composerLog(`✅ ЭТАП 1 ЗАВЕРШЁН УСПЕШНО!`);
            composerLog(`📄 Файл создан: ${result.output_file}`);
            composerLog(`📊 Размер: ${result.file_size_mb ? result.file_size_mb.toFixed(2) + ' MB' : 'неизвестно'}`);
            composerLog(`⏱️ Время рендера: ${result.render_time_sec ? result.render_time_sec.toFixed(1) + ' сек' : 'неизвестно'}`);
            composerLog("════════════════════════════════════════════════════════");

            // 🔥 Проверка перед этапом 2 — детально
            const subsCheckEnabled = comp.subs && comp.subs.addSubs;
            const subsPathExists = comp.subs && comp.subs.subsPath && comp.subs.subsPath.trim().length > 0;
            const willApplySubs = subsCheckEnabled && subsPathExists;

            composerLog(`🔍 ПРОВЕРКА УСЛОВИЙ ЭТАПА 2:`);
            composerLog(`   • Галочка субтитров включена: ${subsCheckEnabled ? '✅ ДА' : '❌ НЕТ'}`);
            composerLog(`   • Путь к SRT задан: ${subsPathExists ? '✅ ДА (' + comp.subs.subsPath + ')' : '❌ НЕТ'}`);
            composerLog(`   • РЕШЕНИЕ: Этап 2 ${willApplySubs ? '✅ БУДЕТ запущен' : '❌ ПРОПУЩЕН'}`);
            composerLog("════════════════════════════════════════════════════════");

            if (willApplySubs) {
                composerLog(`🎬 ▶️ ЗАПУСК ЭТАПА 2: НАЛОЖЕНИЕ СУБТИТРОВ...`);
                comp.lastLogHeader = '<span class="text-[#EF4444]">Накладываем субтитры...</span>';
                if (activeTabId === tabId) composerSyncFromTab();

                let additions = {
                    addSubs: true,
                    subsPath: comp.subs.subsPath,
                    subsFont: comp.subs.subsFont,
                    subsFontSize: comp.subs.subsFontSize,
                    subsColor: comp.subs.subsColor,
                    subsStroke: comp.subs.subsStroke,
                    subsStrokeColor: comp.subs.subsStrokeColor,
                    subsPosY: comp.subs.subsPosY,
                    subsDelay: comp.subs.subsDelay || 0,
                    subsAfterDisclaimer: false,
                    bitrate: 15000
                };

                composerLog(`📦 Параметры для Python:`);
                composerLog(`   ${JSON.stringify(additions, null, 2).replace(/\n/g, '\n   ')}`);

                try {
                    composerLog(`📡 Отправляю вызов в Python: composer_apply_subs(...)`);
                    let subRes = await eel.composer_apply_subs(tabId, result.output_file, additions)();
                    composerLog(`📊 Python вернул результат: ${subRes ? '✅ УСПЕХ' : '❌ ОШИБКА (False)'}`);

                    if (!subRes) {
                        composerLog(`⚠️ Этап 2 завершился с ошибкой. Смотри сообщения от Python выше.`);
                        alert("⚠️ Картинки наложены, но произошла ошибка при добавлении субтитров. Подробности в логе.", "warning");
                    } else {
                        composerLog(`🎉 ЭТАП 2 УСПЕШНО ЗАВЕРШЁН! Субтитры наложены на видео.`);
                    }
                } catch (subErr) {
                    composerLog(`❌ КРИТИЧЕСКОЕ ИСКЛЮЧЕНИЕ при вызове Python: ${subErr}`);
                    composerLog(`   Стек: ${subErr.stack || '(нет данных)'}`);
                    alert("❌ Ошибка наложения субтитров: " + subErr, "error");
                }
            } else {
                if (subsCheckEnabled && !subsPathExists) {
                    composerLog(`⚠️ ВНИМАНИЕ: Галочка субтитров включена, но путь к SRT пуст. Этап 2 пропущен!`);
                } else if (!subsCheckEnabled) {
                    composerLog(`ℹ️ Этап 2 пропущен — галочка субтитров выключена (это нормально).`);
                } else {
                    composerLog(`ℹ️ Этап 2 пропущен (нет данных о субтитрах).`);
                }
            }
            composerLog("════════════════════════════════════════════════════════");

            // 🔥 СНИМАЕМ БЛОКИРОВКУ ЛОГОВ ТОЛЬКО ПОСЛЕ СУБТИТРОВ 🔥
            if (tabs[tabId] && tabs[tabId].composer) {
                tabs[tabId].composer.isRendering = false;
            }
            window.composerRenderingTabId = null;
            if (activeTabId === tabId) composerSyncFromTab();

            if (!window.composerBatchRendering) {
                alert(`✅ Готово!\n\n<span class="text-white font-bold">Файл сохранён в:</span>\n<span class="text-[#EF4444] text-xs">${result.output_file}</span>\n\n<span class="text-white font-bold">Размер:</span> ${result.file_size_mb ? result.file_size_mb.toFixed(2) : 'неизвестно'} MB\n<span class="text-white font-bold">Время рендера:</span> ${result.render_time_sec ? result.render_time_sec.toFixed(1) : 'неизвестно'} сек.`);
            }
            return true;
        } else {
            // 🔥 ЕСЛИ ОШИБКА — ТОЖЕ СНИМАЕМ БЛОКИРОВКУ
            if (tabs[tabId] && tabs[tabId].composer) {
                tabs[tabId].composer.isRendering = false;
            }
            window.composerRenderingTabId = null;
            if (activeTabId === tabId) composerSyncFromTab();

            alert('❌ Ошибка:\n' + ((result.errors || [result.error]).join('\n')));
            return false;
        }
    } catch (e) {
        if (tabs[tabId] && tabs[tabId].composer) tabs[tabId].composer.isRendering = false;
        window.composerRenderingTabId = null;
        if (activeTabId === tabId) composerSyncFromTab();
        alert('❌ Ошибка рендера: ' + e);
        return false;
    }
}

window.composerBatchRendering = false;

async function composerStartRenderSingle() {
    composerSaveToTab();
    if (!activeTabId) return;
    window.composerBatchRendering = false;
    await _runComposerRender(activeTabId);
}

async function composerStartRenderAll() {
    composerSaveToTab();
    const imageTabs = Object.keys(tabs).filter(id => {
        const t = tabs[id];
        if (t.category !== 'image' || !t.composer) return false;
        return t.composer.video && t.composer.layers && t.composer.layers.some(l => l.plan.trim() !== '');
    });

    if (imageTabs.length === 0) return alert('Нет готовых проектов для рендера!');

    window.composerBatchRendering = true;
    let successCount = 0;
    if (activeTabId) composerSyncFromTab();

    for (let tabId of imageTabs) {
        if (!window.composerBatchRendering) break;
        switchTab(tabId);
        let ok = await _runComposerRender(tabId);
        if (ok) successCount++;
    }

    window.composerBatchRendering = false;
    if (activeTabId) composerSyncFromTab();

    if (successCount > 0 || imageTabs.length > 0) {
        alert(`✅ Пакетный рендер завершён!\nУспешно: ${successCount} из ${imageTabs.length}.`);
    }
}

async function composerCancel() {
    try { await eel.composer_cancel()(); } catch (e) { console.error(e); }
}

eel.expose(composerProgressUpdate);
function composerProgressUpdate(percent, eta, fps) {
    if (window.composerRenderingTabId && tabs[window.composerRenderingTabId]) {
        let rComp = tabs[window.composerRenderingTabId].composer;
        rComp.progress = percent; rComp.eta = eta; rComp.fps = fps;
    }
    if (activeTabId === window.composerRenderingTabId) {
        var fill = document.getElementById('composer-progress-fill');
        var pct = document.getElementById('composer-progress-percent');
        var etaEl = document.getElementById('composer-progress-eta');
        var fpsEl = document.getElementById('composer-progress-fps');
        if (fill) fill.style.width = percent + '%';
        if (pct) pct.innerText = percent.toFixed(1) + '%';
        if (etaEl) etaEl.innerText = 'ETA: ' + eta;
        if (fpsEl) fpsEl.innerText = fps.toFixed(0) + ' FPS';
    }
}

eel.expose(composerLog);
function composerLog(msg) {
    if (window.composerRenderingTabId && tabs[window.composerRenderingTabId]) {
        let rComp = tabs[window.composerRenderingTabId].composer;
        if (!rComp.logs) rComp.logs = '';

        const isError = msg.toLowerCase().includes("error") || msg.toLowerCase().includes("ошибка") || msg.toLowerCase().includes("invalid");
        const colorClass = isError ? "text-red-400 font-bold" : "text-white/60";
        const time = new Date().toLocaleTimeString();

        const entryHtml = `<div class="${colorClass}">[${time}] ${msg}</div>`;
        const headerHtml = `<span class="${colorClass}">[${time}] ${msg}</span>`;

        rComp.logs += entryHtml;
        rComp.lastLogHeader = headerHtml;

        if (activeTabId === window.composerRenderingTabId) {
            const log = document.getElementById('composer-log');
            const header = document.getElementById('composer-log-header-text');
            if (log) {
                log.innerHTML += entryHtml;
                const expanded = document.getElementById('composer-log-expanded-content');
                if (expanded) expanded.scrollTop = expanded.scrollHeight;
            }
            if (header) header.innerHTML = headerHtml;
        }
    }
}

window.copyComposerLog = function () {
    if (activeTabId && tabs[activeTabId] && tabs[activeTabId].composer) {
        const temp = document.createElement('div');
        temp.innerHTML = tabs[activeTabId].composer.logs || '';
        navigator.clipboard.writeText(temp.innerText);
        alert("Лог успешно скопирован в буфер обмена!");
    }
};

// 🔥 НОВАЯ ФУНКЦИЯ: СКАЧИВАНИЕ ЛОГА FRAME COMPOSER
window.downloadComposerLog = function () {
    if (!activeTabId || !tabs[activeTabId] || !tabs[activeTabId].composer) {
        alert("Нет активного проекта для скачивания лога!", "warning");
        return;
    }

    const comp = tabs[activeTabId].composer;
    const logsHtml = comp.logs || '';

    if (!logsHtml.trim()) {
        alert("Лог пуст. Сначала запустите рендер!", "warning");
        return;
    }

    // Преобразуем HTML в чистый текст
    const temp = document.createElement('div');
    temp.innerHTML = logsHtml;
    const text = temp.innerText;

    // Имя файла с датой
    const now = new Date();
    const dateStr = now.getFullYear() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') + '_' +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0');

    const projectName = (tabs[activeTabId].name || 'project').replace(/[\\/:*?"<>|]/g, '_');
    const filename = `frame_composer_${projectName}_${dateStr}.txt`;

    // Скачиваем файл
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    composerLog(`💾 Лог скачан: ${filename} (${text.length} символов)`);
    alert(`✅ Лог сохранён как:\n${filename}`, "success");
};

window.showComposerPage = showComposerPage;
window.composerAddLayer = composerAddLayer;
window.composerRemoveLayer = composerRemoveLayer;
window.composerUpdateLayer = composerUpdateLayer;
window.composerPickVideo = composerPickVideo;
window.composerPickImagesFolder = composerPickImagesFolder;
window.composerStartRenderSingle = composerStartRenderSingle;
window.composerStartRenderAll = composerStartRenderAll;
window.composerLoadPlanFromFile = composerLoadPlanFromFile;
window.composerCancel = composerCancel;
window.composerSyncFromTab = composerSyncFromTab;
window.composerSaveToTab = composerSaveToTab;
window.composerToggleApplyAll = composerToggleApplyAll;

window.composerToggleSelect = function (selectId) {
    document.querySelectorAll('.composer-select.open').forEach(s => {
        if (s.id !== selectId) {
            s.classList.remove('open');
            s.querySelector('.composer-select-options').classList.add('hidden');
        }
    });

    const sel = document.getElementById(selectId);
    if (!sel) return;
    const opts = sel.querySelector('.composer-select-options');
    sel.classList.toggle('open');
    opts.classList.toggle('hidden');
};

window.composerSelectOption = function (selectId, li) {
    const sel = document.getElementById(selectId);
    if (!sel) return;

    const value = li.getAttribute('data-value');
    const label = li.textContent;

    sel.setAttribute('data-value', value);
    sel.querySelector('.composer-select-label').textContent = label;

    sel.querySelectorAll('li').forEach(l => l.classList.remove('selected'));
    li.classList.add('selected');

    const hidden = document.getElementById(selectId.replace('-select', ''));
    if (hidden) hidden.value = value;

    sel.classList.remove('open');
    sel.querySelector('.composer-select-options').classList.add('hidden');

    if (typeof composerSaveToTab === 'function') composerSaveToTab();
};

document.addEventListener('click', function (e) {
    if (!e.target.closest('.composer-select')) {
        document.querySelectorAll('.composer-select.open').forEach(s => {
            s.classList.remove('open');
            s.querySelector('.composer-select-options').classList.add('hidden');
        });
    }
});

// === UI СУБТИТРОВ (FRAME COMPOSER) ===
window.composerToggleSubsUI = function () {
    const dCheck = document.getElementById('comp-add-subs-checkbox');
    const dEnabled = dCheck ? dCheck.checked : false;
    const dBlock = document.getElementById('comp-subs-settings-block');
    if (dBlock) {
        dBlock.style.opacity = dEnabled ? '1' : '0.3';
        dBlock.style.pointerEvents = dEnabled ? 'auto' : 'none';
    }
};

window.composerBrowseSrt = async function () {
    try {
        const res = await eel.voicer_browse_file('srt')();
        if (res && res.success && res.path) {
            document.getElementById('comp-subs-path').value = res.path;
            composerSaveToTab();
            composerLog(`Выбран файл субтитров: ${res.path}`);
        }
    } catch (e) { }
};

window.composerLoadSystemFonts = async function () {
    try {
        const fonts = await eel.get_system_fonts()();
        const list = document.getElementById('comp-font-options-list');
        if (!list || !fonts) return;
        list.innerHTML = fonts.map(f =>
            `<li onclick="composerSelectFont('${f}')" data-font="${f.toLowerCase()}" class="!py-1.5 !px-3 !text-[10px] truncate hover:bg-[#EF4444]/20 hover:text-[#EF4444] cursor-pointer transition-colors">${f}</li>`
        ).join('');
    } catch (e) { }
};

window.composerToggleFontDropdown = function (event) {
    event.stopPropagation();
    const opts = document.getElementById('comp-font-options-container');
    const sel = document.getElementById('comp-font-select-container');
    if (opts.classList.contains('hidden')) {
        opts.classList.remove('hidden');
        sel.classList.add('open');
        if (document.getElementById('comp-font-options-list').children.length === 0) composerLoadSystemFonts();
        document.getElementById('comp-font-search').focus();
    } else {
        opts.classList.add('hidden');
        sel.classList.remove('open');
    }
};

window.composerFilterFonts = function () {
    const input = document.getElementById('comp-font-search').value.toLowerCase();
    const items = document.querySelectorAll('#comp-font-options-list li');
    items.forEach(li => {
        const text = li.getAttribute('data-font');
        li.style.display = text.includes(input) ? '' : 'none';
    });
};

window.composerSelectFont = function (fontName) {
    document.getElementById('comp-font-selected-text').textContent = fontName.replace('.ttf', '').replace('.otf', '');
    document.getElementById('comp-subs-font-hidden').value = fontName;
    document.getElementById('comp-font-options-container').classList.add('hidden');
    document.getElementById('comp-font-select-container').classList.remove('open');
    composerSaveToTab();
};

document.addEventListener('click', function (e) {
    if (!e.target.closest('#comp-font-select-container')) {
        const opts = document.getElementById('comp-font-options-container');
        const sel = document.getElementById('comp-font-select-container');
        if (opts) opts.classList.add('hidden');
        if (sel) sel.classList.remove('open');
    }
});