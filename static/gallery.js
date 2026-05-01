(function () {
    "use strict";

    var HEARTBEAT_INTERVAL_MS = 5000;
    var INDEX_PATH = "/";
    var SHORTCUT_KEY_SIZE = "s";
    var SHORTCUT_KEY_NEXT = "n";
    var SHORTCUT_KEY_NEXT_ALTERNATE = ".";
    var SHORTCUT_KEY_PREVIOUS = "p";
    var SHORTCUT_KEY_PREVIOUS_ALTERNATE = ",";
    var SHORTCUT_KEY_INDEX = "i";
    var SHORTCUT_KEY_QUIT = "q";
    var SHORTCUT_KEY_FOCUS_COMMENT = "/";
    var SHORTCUT_KEY_COPY_FILENAME = "c";
    var SHORTCUT_KEY_ENTER = "Enter";
    var SHORTCUT_KEY_GO_TO = "g";
    var SHORTCUT_KEY_TOGGLE_UNCHANGED = "u";
    var SHORTCUT_KEY_MODE_NEXT = "m";
    var SHORTCUT_KEY_MODE_PREV = "M";
    var VIZDIFF_MODE_KEY = "bugshot:vizdiff:mode";
    var VIZDIFF_MODES = ["side-by-side", "swipe", "onion", "diff"];
    var SHORTCUT_KEY_CYCLE_TOOL = "d";
    var TOOL_OFF = "off";
    var TOOL_RECT = "rect";
    var TOOL_ELLIPSE = "ellipse";
    var TOOL_PATH = "path";
    // Tool order drives the cycle-tool shortcut. Insert future tools here and
    // the segmented control + cycle behavior will pick them up automatically.
    var TOOL_ORDER = [TOOL_OFF, TOOL_RECT, TOOL_ELLIPSE, TOOL_PATH];
    // Per-tool CSS class applied to the region overlay. Drives the cursor shown
    // over the asset (off → default, rect/ellipse → crosshair, freehand → pen).
    // The "off" tool intentionally has no class so pointer-events stay none
    // and clicks pass through to the underlying asset.
    var TOOL_OVERLAY_CLASS = {
        rect: "tool-mode-rect",
        ellipse: "tool-mode-ellipse",
        path: "tool-mode-path"
    };
    var ALL_TOOL_OVERLAY_CLASSES = [
        "tool-mode-rect",
        "tool-mode-ellipse",
        "tool-mode-path"
    ];
    var REGION_LINE_COLOR = "rgba(64, 200, 240, 0.95)";
    var REGION_FILL_COLOR = "rgba(64, 200, 240, 0.18)";
    // Subdued styling for committed regions when nothing is being highlighted.
    // Hover-highlight (bugshot-qh9) restores REGION_LINE_COLOR / REGION_FILL_COLOR
    // for the matched region only.
    var REGION_LINE_COLOR_DIM = "rgba(64, 200, 240, 0.42)";
    var REGION_FILL_COLOR_DIM = "rgba(64, 200, 240, 0.07)";
    var REGION_DEFAULT_LINE_WIDTH = 2;
    var REGION_HIGHLIGHT_LINE_WIDTH = 3;
    // Hit-test tolerance (in screen pixels) for path-style regions. Converted to
    // normalized units against the larger image dimension at hit-test time.
    var PATH_HIT_PAD_PIXELS = 8;
    var REGION_PENDING_DASH = [6, 4];
    var REGION_COMMITTED_DASH = [];
    var MIN_RECT_NORMALIZED_SIZE = 0.005;
    var MIN_ELLIPSE_NORMALIZED_RADIUS = 0.0025;
    var MIN_PATH_POINT_COUNT = 2;
    var SELECTION_BADGE_FILL = "rgba(64, 200, 240, 0.95)";
    var SELECTION_BADGE_STROKE = "rgba(11, 20, 24, 0.85)";
    var SELECTION_BADGE_TEXT_COLOR = "#0b1418";
    var SELECTION_BADGE_FONT_PX = 14;
    var SELECTION_BADGE_PADDING_X = 6;
    var SELECTION_BADGE_PADDING_Y = 3;
    var SELECTION_BADGE_RADIUS = 4;
    var SELECTION_BADGE_OFFSET = 2;
    var DIGIT_KEYS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
    var VIZDIFF_FILTER_KEY = "bugshot:vizdiff:filters";
    var VIZDIFF_DEFAULT_FILTERS = {
        changed: true,
        added: true,
        removed: true,
        unchanged: false
    };
    var VIZDIFF_CLASS_ORDER = ["changed", "added", "removed", "unchanged"];
    var THEME_STORAGE_KEY = "bugshot-theme";
    var THEME_ORDER = [
        { id: "mono-light", label: "Light", tone: "light", swapColor: "#161311" },
        { id: "mono-dark", label: "Dark", tone: "dark", swapColor: "#f1eee9" },
        { id: "paper", label: "Paper", tone: "light", swapColor: "#211915" },
        { id: "ocean", label: "Ocean", tone: "dark", swapColor: "#eef4ff" },
        { id: "moss", label: "Moss", tone: "dark", swapColor: "#eef5e8" }
    ];

    var isIndex = !!window.__BUGSHOT_UNITS__;
    var isDetail = !!window.__BUGSHOT_DETAIL__;
    var detailPage = window.__BUGSHOT_DETAIL__ || null;
    var currentUnit = detailPage ? detailPage.unit : null;
    var currentTheme = loadThemeId();
    var isInternalNavigation = false;
    var jumpModal = null;
    var jumpModalInput = null;
    var jumpModalError = null;
    var serverStatusBanner = null;
    var serverStatusText = null;
    var isServerReachable = true;
    var serverActionButtons = [];
    var copyFilenameStatusTimeout = null;
    var vizdiffActive = false;
    var vizdiffFilters = null;
    var vizdiffUnits = null;
    var vizdiffDetailActive = false;
    // Region-drawing state for the detail page's current unit. Null on the
    // index page or before initDetail runs. Exposed at module scope so the
    // top-level keydown handler can drive ArrowUp/ArrowDown comment-list
    // navigation through the same highlight machinery (qh9) that hover uses.
    var currentRegionState = null;

    applyTheme(currentTheme, false);
    initServerStatusBanner();
    initThemeControls();
    checkServerHeartbeat();
    setInterval(checkServerHeartbeat, HEARTBEAT_INTERVAL_MS);

    window.addEventListener("beforeunload", function () {
        if (!isInternalNavigation) {
            navigator.sendBeacon("/api/closed");
        }
    });

    bindDoneButton(document.getElementById("done-btn"));
    bindDoneButton(document.getElementById("detail-done-btn"));

    if (isIndex) {
        initIndex();
    }

    if (isDetail) {
        initDetail();
    }

    initJumpModal();

    document.addEventListener("keydown", function (event) {
        if (isJumpModalOpen()) {
            handleJumpModalKeydown(event);
            return;
        }

        var activeElement = document.activeElement;
        var isTyping = activeElement &&
            (activeElement.tagName === "INPUT" || activeElement.tagName === "TEXTAREA");
        var hasModifier = event.ctrlKey || event.metaKey || event.altKey;

        if (isTyping) {
            if (event.key === "Escape") {
                activeElement.blur();
                event.preventDefault();
            }
            return;
        }

        if (event.key === SHORTCUT_KEY_SIZE && isIndex) {
            toggleIndexSize();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_TOGGLE_UNCHANGED && isIndex && vizdiffActive) {
            toggleVizdiffUnchangedFilter();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_MODE_NEXT && isDetail && vizdiffDetailActive) {
            cycleVizdiffMode(1);
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_MODE_PREV && isDetail && vizdiffDetailActive) {
            cycleVizdiffMode(-1);
            event.preventDefault();
        } else if (DIGIT_KEYS.indexOf(event.key) !== -1) {
            navigateToImageByShortcut(event.key);
            event.preventDefault();
        } else if ((event.key === SHORTCUT_KEY_NEXT || event.key === SHORTCUT_KEY_ENTER) && isIndex) {
            navigateToFirstImage();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_PREVIOUS && isIndex) {
            navigateToLastImage();
            event.preventDefault();
        } else if (
            isDetail &&
            detailPage.nav.next &&
            (
                event.key === SHORTCUT_KEY_NEXT ||
                (!hasModifier && event.key === SHORTCUT_KEY_NEXT_ALTERNATE)
            )
        ) {
            navigateTo(detailPage.nav.next);
            event.preventDefault();
        } else if (
            isDetail &&
            detailPage.nav.prev &&
            (
                event.key === SHORTCUT_KEY_PREVIOUS ||
                (!hasModifier && event.key === SHORTCUT_KEY_PREVIOUS_ALTERNATE)
            )
        ) {
            navigateTo(detailPage.nav.prev);
            event.preventDefault();
        } else if (
            event.key === SHORTCUT_KEY_COPY_FILENAME &&
            isDetail &&
            !hasModifier
        ) {
            copyFilenameToClipboard();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_GO_TO) {
            openJumpModal();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_INDEX) {
            navigateTo(INDEX_PATH);
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_QUIT) {
            if (!isServerReachable) {
                showServerDown("Bugshot server is unreachable. Reconnect before finishing review.");
                event.preventDefault();
                return;
            }
            if (confirm("Done reviewing? This will end the session.")) {
                completeSession();
            }
            event.preventDefault();
        } else if (
            event.key === SHORTCUT_KEY_CYCLE_TOOL &&
            isDetail &&
            unitSupportsRegionDrawing(currentUnit)
        ) {
            cycleActiveTool();
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_FOCUS_COMMENT && isDetail) {
            focusCommentInput();
            event.preventDefault();
        } else if (event.key === "ArrowDown" && isDetail && !hasModifier) {
            focusAdjacentComment(1);
            event.preventDefault();
        } else if (event.key === "ArrowUp" && isDetail && !hasModifier) {
            focusAdjacentComment(-1);
            event.preventDefault();
        }
    });

    function bindDoneButton(button) {
        if (!button) {
            return;
        }

        serverActionButtons.push(button);
        button.addEventListener("click", function () {
            if (!isServerReachable) {
                showServerDown("Bugshot server is unreachable. Reconnect before finishing review.");
                return;
            }
            if (confirm("Done reviewing? This will end the session.")) {
                completeSession();
            }
        });
    }

    function initServerStatusBanner() {
        serverStatusBanner = document.createElement("div");
        serverStatusBanner.className = "server-status-banner is-hidden";
        serverStatusBanner.setAttribute("role", "status");

        serverStatusText = document.createElement("span");
        serverStatusBanner.appendChild(serverStatusText);
        document.body.insertBefore(serverStatusBanner, document.body.firstChild);
    }

    function initThemeControls() {
        [document.getElementById("index-theme-controls"), document.getElementById("detail-theme-controls")]
            .filter(Boolean)
            .forEach(function (container) {
                container.textContent = "";
                container.classList.add("theme-controls-ready");
                THEME_ORDER.forEach(function (theme) {
                    var button = document.createElement("button");
                    button.type = "button";
                    button.className = "theme-button";
                    button.dataset.themeId = theme.id;
                    button.title = theme.label;
                    button.setAttribute("aria-label", theme.label);
                    button.textContent = theme.label;
                    button.addEventListener("click", function () {
                        applyTheme(theme.id, true);
                    });
                    container.appendChild(button);
                });
            });

        syncThemeButtons();
    }

    function loadThemeId() {
        try {
            return localStorage.getItem(THEME_STORAGE_KEY) || THEME_ORDER[1].id;
        } catch (error) {
            return THEME_ORDER[1].id;
        }
    }

    function applyTheme(themeId, persist) {
        if (!findTheme(themeId)) {
            themeId = THEME_ORDER[1].id;
        }

        currentTheme = themeId;
        document.body.dataset.theme = themeId;
        syncThemeButtons();
        rerenderSvgAssets();

        if (!persist) {
            return;
        }

        try {
            localStorage.setItem(THEME_STORAGE_KEY, themeId);
        } catch (error) {
        }
    }

    function syncThemeButtons() {
        Array.prototype.slice.call(document.querySelectorAll(".theme-button")).forEach(function (button) {
            var isActive = button.dataset.themeId === currentTheme;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
    }

    function findTheme(themeId) {
        for (var index = 0; index < THEME_ORDER.length; index += 1) {
            if (THEME_ORDER[index].id === themeId) {
                return THEME_ORDER[index];
            }
        }
        return null;
    }

    function currentThemeDefinition() {
        return findTheme(currentTheme) || THEME_ORDER[1];
    }

    function checkServerHeartbeat() {
        fetch("/api/heartbeat", { method: "POST" })
            .then(requireOkResponse)
            .then(function () {
                setServerReachable(true);
            })
            .catch(function () {
                showServerDown("Bugshot server is unreachable. New comments cannot be saved until it responds again.");
            });
    }

    function setServerReachable(isReachable) {
        isServerReachable = isReachable;
        serverActionButtons.forEach(function (button) {
            button.disabled = !isReachable;
        });

        if (isReachable) {
            serverStatusBanner.classList.add("is-hidden");
            serverStatusText.textContent = "";
        }
    }

    function showServerDown(message) {
        setServerReachable(false);
        serverStatusText.textContent = message;
        serverStatusBanner.classList.remove("is-hidden");
    }

    function requireOkResponse(response) {
        if (!response.ok) {
            throw new Error("Request failed with status " + response.status);
        }
        return response;
    }

    function fetchJson(url, options) {
        return fetch(url, options)
            .then(requireOkResponse)
            .then(function (response) {
                setServerReachable(true);
                return response.json();
            });
    }

    function initJumpModal() {
        jumpModal = document.createElement("div");
        jumpModal.className = "jump-modal is-hidden";
        jumpModal.innerHTML =
            '<div class="jump-modal-card" role="dialog" aria-modal="true" aria-labelledby="jump-modal-title">' +
            '<div class="jump-modal-title" id="jump-modal-title">Go to unit</div>' +
            '<div class="jump-modal-copy">Type any unit number and press Enter.</div>' +
            '<form class="jump-modal-form" id="jump-modal-form">' +
            '<input class="jump-modal-input" id="jump-modal-input" inputmode="numeric" autocomplete="off" />' +
            '<button type="submit" class="btn">Go</button>' +
            "</form>" +
            '<div class="jump-modal-error" id="jump-modal-error"></div>' +
            "</div>";
        document.body.appendChild(jumpModal);

        jumpModalInput = document.getElementById("jump-modal-input");
        jumpModalError = document.getElementById("jump-modal-error");

        jumpModal.addEventListener("click", function (event) {
            if (event.target === jumpModal) {
                closeJumpModal();
            }
        });

        document.getElementById("jump-modal-form").addEventListener("submit", function (event) {
            event.preventDefault();
            submitJumpModal();
        });
    }

    function completeSession() {
        fetch("/api/done", { method: "POST" })
            .then(requireOkResponse)
            .then(function () {
                setServerReachable(true);
                window.close();

                document.body.textContent = "";
                var message = document.createElement("div");
                message.style.cssText =
                    "display:flex;align-items:center;justify-content:center;" +
                    "height:100vh;color:var(--text-color);font-size:18px;";
                message.textContent = "Session complete. You can close this tab.";
                document.body.appendChild(message);
            })
            .catch(function () {
                showServerDown("Bugshot server is unreachable. Review was not marked complete.");
            });
    }

    function initIndex() {
        var units = window.__BUGSHOT_UNITS__;
        vizdiffUnits = units;
        vizdiffActive = units.some(function (u) { return !!u.vizdiff; });

        if (vizdiffActive) {
            vizdiffFilters = loadVizdiffFilters(units);
            renderVizdiffFilterBar();
        }

        renderIndexTiles();
    }

    function renderIndexTiles() {
        var units = vizdiffUnits || window.__BUGSHOT_UNITS__;
        var gallery = document.getElementById("gallery");
        gallery.replaceChildren();

        var visible = vizdiffActive
            ? applyVizdiffFilters(units, vizdiffFilters)
            : units;

        visible.forEach(function (unitInfo) {
            var item = document.createElement("a");
            item.className = "gallery-item";
            item.href = "/view/" + unitInfo.encoded_id;
            if (unitInfo.vizdiff) {
                item.dataset.cls = unitInfo.vizdiff.classification;
            }
            bindInternalNavigation(item);

            if (unitInfo.vizdiff) {
                var badge = document.createElement("span");
                badge.className = "tile-badge";
                badge.dataset.cls = unitInfo.vizdiff.classification;
                badge.textContent = unitInfo.vizdiff.classification.toUpperCase();
                item.appendChild(badge);
            }

            appendAssetPreview(item, unitInfo.primary_asset, true);

            var label = document.createElement("div");
            label.className = "item-label";
            label.textContent = unitInfo.label;
            item.appendChild(label);

            var meta = document.createElement("div");
            meta.className = "item-meta";
            meta.textContent = describeUnit(unitInfo);
            item.appendChild(meta);

            gallery.appendChild(item);
        });
    }

    function loadVizdiffFilters(units) {
        var stored = null;
        try {
            stored = JSON.parse(localStorage.getItem(VIZDIFF_FILTER_KEY) || "null");
        } catch (e) {
            stored = null;
        }
        var filters = stored && typeof stored === "object"
            ? Object.assign({}, VIZDIFF_DEFAULT_FILTERS, stored)
            : Object.assign({}, VIZDIFF_DEFAULT_FILTERS);

        var counts = countVizdiffByClass(units);
        if (counts.changed === 0 && counts.added === 0 && counts.removed === 0) {
            filters = { changed: true, added: true, removed: true, unchanged: true };
        }
        return filters;
    }

    function persistVizdiffFilters() {
        try {
            localStorage.setItem(VIZDIFF_FILTER_KEY, JSON.stringify(vizdiffFilters));
        } catch (e) {
            // localStorage unavailable; no-op.
        }
    }

    function countVizdiffByClass(units) {
        var counts = { changed: 0, added: 0, removed: 0, unchanged: 0 };
        units.forEach(function (u) {
            if (u.vizdiff && counts.hasOwnProperty(u.vizdiff.classification)) {
                counts[u.vizdiff.classification] += 1;
            }
        });
        return counts;
    }

    function applyVizdiffFilters(units, filters) {
        var visible = units.filter(function (u) {
            if (!u.vizdiff) {
                return true;
            }
            return !!filters[u.vizdiff.classification];
        });
        visible.sort(function (a, b) {
            var au = a.vizdiff && a.vizdiff.classification === "unchanged" ? 1 : 0;
            var bu = b.vizdiff && b.vizdiff.classification === "unchanged" ? 1 : 0;
            if (au !== bu) {
                return au - bu;
            }
            return (a.label || "").localeCompare(b.label || "");
        });
        return visible;
    }

    function renderVizdiffFilterBar() {
        var bar = document.getElementById("filter-bar");
        if (!bar) {
            return;
        }
        bar.hidden = false;
        bar.replaceChildren();

        var counts = countVizdiffByClass(vizdiffUnits);
        VIZDIFF_CLASS_ORDER.forEach(function (cls) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "filter-chip";
            chip.dataset.cls = cls;
            chip.dataset.active = String(!!vizdiffFilters[cls]);

            var label = document.createElement("span");
            label.className = "label";
            label.textContent = cls.toUpperCase();
            chip.appendChild(label);

            var count = document.createElement("span");
            count.className = "count";
            count.textContent = String(counts[cls] || 0);
            chip.appendChild(count);

            chip.addEventListener("click", function () {
                vizdiffFilters[cls] = !vizdiffFilters[cls];
                chip.dataset.active = String(!!vizdiffFilters[cls]);
                persistVizdiffFilters();
                renderIndexTiles();
            });
            bar.appendChild(chip);
        });
    }

    function toggleVizdiffUnchangedFilter() {
        if (!vizdiffFilters) {
            return;
        }
        vizdiffFilters.unchanged = !vizdiffFilters.unchanged;
        persistVizdiffFilters();
        var chip = document.querySelector('.filter-chip[data-cls="unchanged"]');
        if (chip) {
            chip.dataset.active = String(!!vizdiffFilters.unchanged);
        }
        renderIndexTiles();
    }

    function initVizdiffDetailModes(unit) {
        var vd = unit && unit.vizdiff;
        if (!vd || !vd.base_asset || !vd.head_asset) {
            return;
        }
        var baseAsset = assetByName(unit, vd.base_asset);
        if (!baseAsset) {
            return;
        }
        if (baseAsset.type === "ansi") {
            // ANSI units only support side-by-side rendering of the existing
            // asset cards; the canvas modes have no pixel grid to subtract.
            return;
        }

        vizdiffDetailActive = true;
        var modeBar = document.getElementById("mode-bar");
        var pane = document.getElementById("viewer-pane");
        if (!modeBar || !pane) {
            return;
        }
        modeBar.hidden = false;
        pane.hidden = false;

        var overlayToggle = document.getElementById("overlay-toggle");
        if (overlayToggle) {
            overlayToggle.checked = false;
            overlayToggle.addEventListener("change", function () {
                renderVizdiffMode(loadVizdiffMode(), unit);
            });
        }

        Array.prototype.forEach.call(
            modeBar.querySelectorAll(".mode-button"),
            function (btn) {
                btn.addEventListener("click", function () {
                    setVizdiffMode(btn.dataset.mode, unit);
                });
            }
        );

        setVizdiffMode(loadVizdiffMode(), unit);
    }

    function loadVizdiffMode() {
        try {
            var stored = localStorage.getItem(VIZDIFF_MODE_KEY);
            if (stored && VIZDIFF_MODES.indexOf(stored) !== -1) {
                return stored;
            }
        } catch (e) {
            // ignored
        }
        return "side-by-side";
    }

    function setVizdiffMode(mode, unit) {
        if (VIZDIFF_MODES.indexOf(mode) === -1) {
            mode = "side-by-side";
        }
        try {
            localStorage.setItem(VIZDIFF_MODE_KEY, mode);
        } catch (e) {
            // ignored
        }
        Array.prototype.forEach.call(
            document.querySelectorAll(".mode-button"),
            function (btn) {
                btn.dataset.active = String(btn.dataset.mode === mode);
            }
        );
        renderVizdiffMode(mode, unit);
    }

    function cycleVizdiffMode(delta) {
        var current = loadVizdiffMode();
        var idx = VIZDIFF_MODES.indexOf(current);
        if (idx === -1) {
            idx = 0;
        }
        var next = (idx + delta + VIZDIFF_MODES.length) % VIZDIFF_MODES.length;
        setVizdiffMode(VIZDIFF_MODES[next], currentUnit);
    }

    function renderVizdiffMode(mode, unit) {
        var pane = document.getElementById("viewer-pane");
        if (!pane) {
            return;
        }
        pane.replaceChildren();
        var base = assetByName(unit, unit.vizdiff.base_asset);
        var head = assetByName(unit, unit.vizdiff.head_asset);
        switch (mode) {
            case "side-by-side":
                renderVizdiffSideBySide(pane, base, head);
                break;
            case "swipe":
                renderVizdiffSwipe(pane, base, head);
                break;
            case "onion":
                renderVizdiffOnion(pane, base, head);
                break;
            case "diff":
                renderVizdiffDiff(pane, base, head);
                break;
        }
    }

    function assetByName(unit, name) {
        if (!unit || !name) {
            return null;
        }
        for (var i = 0; i < unit.assets.length; i++) {
            if (unit.assets[i].name === name) {
                return unit.assets[i];
            }
        }
        return null;
    }

    function buildSideFigure(label, asset) {
        var fig = document.createElement("figure");
        fig.className = "vizdiff-figure";
        var cap = document.createElement("figcaption");
        cap.textContent = label;
        fig.appendChild(cap);
        var img = document.createElement("img");
        img.src = asset.src;
        img.alt = asset.name;
        fig.appendChild(img);
        return fig;
    }

    function renderVizdiffSideBySide(pane, base, head) {
        var wrap = document.createElement("div");
        wrap.className = "vizdiff-side-by-side";
        wrap.appendChild(buildSideFigure("Base", base));
        wrap.appendChild(buildSideFigure("Head", head));
        pane.appendChild(wrap);
        if (overlayEnabled()) {
            applyOverlayToFigure(wrap.lastChild, base, head);
        }
    }

    function overlayEnabled() {
        var toggle = document.getElementById("overlay-toggle");
        return !!(toggle && toggle.checked);
    }

    function applyOverlayToFigure(figure, base, head) {
        loadImagePair(base, head, function (baseImg, headImg) {
            if (baseImg.naturalWidth !== headImg.naturalWidth ||
                baseImg.naturalHeight !== headImg.naturalHeight) {
                return;
            }
            var canvas = document.createElement("canvas");
            canvas.className = "vizdiff-overlay-canvas";
            canvas.width = headImg.naturalWidth;
            canvas.height = headImg.naturalHeight;
            paintOverlay(canvas, baseImg, headImg);
            figure.appendChild(canvas);
        });
    }

    function paintOverlay(canvas, baseImg, headImg) {
        var ctx = canvas.getContext("2d");
        ctx.drawImage(headImg, 0, 0);
        var headData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        ctx.drawImage(baseImg, 0, 0);
        var baseData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        var out = ctx.createImageData(canvas.width, canvas.height);
        for (var i = 0; i < headData.data.length; i += 4) {
            var dr = Math.abs(headData.data[i] - baseData.data[i]);
            var dg = Math.abs(headData.data[i + 1] - baseData.data[i + 1]);
            var db = Math.abs(headData.data[i + 2] - baseData.data[i + 2]);
            var diff = dr + dg + db;
            if (diff > 6) {
                out.data[i] = 239;
                out.data[i + 1] = 68;
                out.data[i + 2] = 68;
                out.data[i + 3] = 160;
            }
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.putImageData(out, 0, 0);
    }

    function renderVizdiffSwipe(pane, base, head) {
        var wrap = document.createElement("div");
        wrap.className = "vizdiff-swipe-wrap";
        var stage = document.createElement("div");
        stage.className = "vizdiff-swipe-stage";

        var baseImg = document.createElement("img");
        baseImg.className = "vizdiff-swipe-base";
        baseImg.src = base.src;
        baseImg.alt = base.name;

        var headImg = document.createElement("img");
        headImg.className = "vizdiff-swipe-head";
        headImg.src = head.src;
        headImg.alt = head.name;

        var handle = document.createElement("div");
        handle.className = "vizdiff-swipe-handle";

        stage.appendChild(baseImg);
        stage.appendChild(headImg);
        stage.appendChild(handle);
        wrap.appendChild(stage);

        var note = document.createElement("p");
        note.className = "vizdiff-mode-note";
        note.textContent = "Drag the handle to swipe between base (left) and head (right).";
        wrap.appendChild(note);

        pane.appendChild(wrap);

        var split = 0.5;
        function applySplit() {
            var pct = (split * 100).toFixed(2) + "%";
            headImg.style.clipPath = "inset(0 0 0 " + pct + ")";
            handle.style.left = pct;
        }
        applySplit();

        function onMove(clientX) {
            var rect = stage.getBoundingClientRect();
            if (rect.width <= 0) {
                return;
            }
            split = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            applySplit();
        }
        handle.addEventListener("pointerdown", function (event) {
            event.preventDefault();
            handle.setPointerCapture(event.pointerId);
            function onPointerMove(e) {
                onMove(e.clientX);
            }
            function onPointerUp(e) {
                handle.releasePointerCapture(event.pointerId);
                handle.removeEventListener("pointermove", onPointerMove);
                handle.removeEventListener("pointerup", onPointerUp);
            }
            handle.addEventListener("pointermove", onPointerMove);
            handle.addEventListener("pointerup", onPointerUp);
        });
    }

    function renderVizdiffOnion(pane, base, head) {
        var wrap = document.createElement("div");
        wrap.className = "vizdiff-onion-wrap";
        var stage = document.createElement("div");
        stage.className = "vizdiff-onion-stage";

        var baseImg = document.createElement("img");
        baseImg.className = "vizdiff-onion-base";
        baseImg.src = base.src;
        baseImg.alt = base.name;

        var headImg = document.createElement("img");
        headImg.className = "vizdiff-onion-head";
        headImg.src = head.src;
        headImg.alt = head.name;

        stage.appendChild(baseImg);
        stage.appendChild(headImg);

        var controls = document.createElement("div");
        controls.className = "vizdiff-onion-controls";
        var label = document.createElement("label");
        label.textContent = "Head opacity";
        var slider = document.createElement("input");
        slider.type = "range";
        slider.min = "0";
        slider.max = "100";
        slider.value = "50";
        slider.addEventListener("input", function () {
            headImg.style.opacity = String(slider.value / 100);
        });
        headImg.style.opacity = "0.5";
        controls.appendChild(label);
        controls.appendChild(slider);

        wrap.appendChild(stage);
        wrap.appendChild(controls);
        pane.appendChild(wrap);
    }

    function renderVizdiffDiff(pane, base, head) {
        var wrap = document.createElement("div");
        wrap.className = "vizdiff-diff-wrap";
        var canvas = document.createElement("canvas");
        canvas.className = "vizdiff-diff-canvas";
        wrap.appendChild(canvas);

        var note = document.createElement("p");
        note.className = "vizdiff-mode-note";
        note.textContent = "Pixels glow where base and head differ.";
        wrap.appendChild(note);
        pane.appendChild(wrap);

        loadImagePair(base, head, function (baseImg, headImg) {
            if (baseImg.naturalWidth !== headImg.naturalWidth ||
                baseImg.naturalHeight !== headImg.naturalHeight) {
                note.textContent =
                    "Diff image unavailable: base and head dimensions differ.";
                return;
            }
            canvas.width = baseImg.naturalWidth;
            canvas.height = baseImg.naturalHeight;
            paintDiffCanvas(canvas, baseImg, headImg);
        });
    }

    function paintDiffCanvas(canvas, baseImg, headImg) {
        var ctx = canvas.getContext("2d");
        ctx.drawImage(baseImg, 0, 0);
        var baseData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        ctx.drawImage(headImg, 0, 0);
        var headData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        var out = ctx.createImageData(canvas.width, canvas.height);
        for (var i = 0; i < headData.data.length; i += 4) {
            var dr = Math.abs(headData.data[i] - baseData.data[i]);
            var dg = Math.abs(headData.data[i + 1] - baseData.data[i + 1]);
            var db = Math.abs(headData.data[i + 2] - baseData.data[i + 2]);
            out.data[i] = Math.min(255, dr * 4);
            out.data[i + 1] = Math.min(255, dg * 4);
            out.data[i + 2] = Math.min(255, db * 4);
            out.data[i + 3] = 255;
        }
        ctx.putImageData(out, 0, 0);
    }

    function loadImagePair(base, head, callback) {
        var baseImg = new Image();
        var headImg = new Image();
        var loaded = 0;
        function maybeReady() {
            loaded += 1;
            if (loaded === 2) {
                callback(baseImg, headImg);
            }
        }
        baseImg.onload = maybeReady;
        headImg.onload = maybeReady;
        baseImg.onerror = function () { /* skip */ };
        headImg.onerror = function () { /* skip */ };
        baseImg.src = base.src;
        headImg.src = head.src;
    }

    function appendAssetPreview(container, asset, isPreview) {
        if (asset.type === "image") {
            var imageElement = document.createElement("img");
            imageElement.src = asset.src;
            imageElement.alt = asset.name;
            container.appendChild(imageElement);
            return;
        }

        if (asset.type === "svg") {
            container.appendChild(createSvgPreview(asset, isPreview));
            return;
        }

        var previewDiv = document.createElement("div");
        previewDiv.className = isPreview ? "ansi-preview" : "ansi-rendered";
        var previewPre = document.createElement("pre");
        previewPre.innerHTML = asset.rendered_html;
        previewDiv.appendChild(previewPre);
        container.appendChild(previewDiv);
    }

    function createSvgPreview(asset, isPreview) {
        var wrapper = document.createElement("div");
        wrapper.className = isPreview ? "svg-preview" : "svg-rendered";
        wrapper.dataset.svgMarkup = asset.svg_markup || "";
        wrapper.dataset.primaryColor = asset.primary_color || "";
        wrapper.dataset.fallbackSrc = asset.src || "";
        renderSvgIntoWrapper(wrapper);
        return wrapper;
    }

    function renderSvgIntoWrapper(wrapper) {
        var svgMarkup = wrapper.dataset.svgMarkup || "";
        var fallbackSrc = wrapper.dataset.fallbackSrc || "";
        wrapper.textContent = "";

        if (!svgMarkup) {
            renderSvgFallback(wrapper, fallbackSrc);
            return;
        }

        var parser = new DOMParser();
        var doc = parser.parseFromString(svgMarkup, "image/svg+xml");
        var root = doc.documentElement;

        if (!root || root.nodeName.toLowerCase() === "parsererror") {
            renderSvgFallback(wrapper, fallbackSrc);
            return;
        }

        var primaryColor = wrapper.dataset.primaryColor || "";
        var swapColor = themeSwapColor(primaryColor);
        if (swapColor) {
            rewriteSvgPrimaryColor(root, primaryColor, swapColor);
        }

        root.classList.add("svg-asset");
        wrapper.appendChild(document.importNode(root, true));
    }

    function renderSvgFallback(wrapper, src) {
        var fallback = document.createElement("img");
        fallback.src = src;
        fallback.alt = "SVG asset";
        wrapper.appendChild(fallback);
    }

    function themeSwapColor(primaryColor) {
        if (!primaryColor) {
            return null;
        }

        var theme = currentThemeDefinition();
        var luminance = colorLuminance(primaryColor);
        if (luminance === null) {
            return null;
        }

        if (theme.tone === "light" && luminance >= 0.68) {
            return theme.swapColor;
        }

        if (theme.tone === "dark" && luminance <= 0.38) {
            return theme.swapColor;
        }

        return null;
    }

    function colorLuminance(hexColor) {
        var match = /^#?([0-9a-f]{6})$/i.exec(hexColor);
        if (!match) {
            return null;
        }

        var value = match[1];
        var channels = [
            parseInt(value.slice(0, 2), 16) / 255,
            parseInt(value.slice(2, 4), 16) / 255,
            parseInt(value.slice(4, 6), 16) / 255
        ];

        for (var index = 0; index < channels.length; index += 1) {
            channels[index] = channels[index] <= 0.03928
                ? channels[index] / 12.92
                : Math.pow((channels[index] + 0.055) / 1.055, 2.4);
        }

        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    }

    function rewriteSvgPrimaryColor(root, primaryColor, swapColor) {
        Array.prototype.slice.call(root.querySelectorAll("*")).concat([root]).forEach(function (node) {
            rewriteSvgPresentationAttributes(node, primaryColor, swapColor);
        });
        root.setAttribute("color", swapColor);
    }

    function rewriteSvgPresentationAttributes(node, primaryColor, swapColor) {
        ["fill", "stroke"].forEach(function (attrName) {
            var attrValue = node.getAttribute(attrName);
            if (normalizeColor(attrValue) === primaryColor) {
                node.setAttribute(attrName, "currentColor");
            }
        });

        var styleValue = node.getAttribute("style");
        if (!styleValue) {
            return;
        }

        var rewritten = styleValue.split(";").map(function (declaration) {
            if (declaration.indexOf(":") === -1) {
                return declaration;
            }
            var parts = declaration.split(":");
            var key = parts[0].trim();
            var value = parts.slice(1).join(":").trim();
            if ((key === "fill" || key === "stroke") && normalizeColor(value) === primaryColor) {
                return key + ": currentColor";
            }
            return declaration;
        }).join(";");

        node.setAttribute("style", rewritten);
    }

    function normalizeColor(value) {
        if (!value) {
            return null;
        }

        var normalized = String(value).trim().toLowerCase();
        if (/^#[0-9a-f]{3}$/.test(normalized)) {
            return "#" + normalized.charAt(1) + normalized.charAt(1) +
                normalized.charAt(2) + normalized.charAt(2) +
                normalized.charAt(3) + normalized.charAt(3);
        }
        if (/^#[0-9a-f]{6}$/.test(normalized)) {
            return normalized;
        }
        return null;
    }

    function rerenderSvgAssets() {
        Array.prototype.slice.call(document.querySelectorAll(".svg-preview, .svg-rendered")).forEach(function (wrapper) {
            renderSvgIntoWrapper(wrapper);
        });
    }

    function describeUnit(unitInfo) {
        var pieces = [];
        pieces.push(unitInfo.asset_count === 1 ? "1 asset" : unitInfo.asset_count + " assets");
        if (unitInfo.metadata_count) {
            pieces.push(unitInfo.metadata_count === 1 ? "1 metadata file" : unitInfo.metadata_count + " metadata files");
        }
        return pieces.join(" · ");
    }

    function navigateToFirstImage() {
        var units = getAvailableImages();
        if (!units.length) {
            return;
        }
        navigateTo("/view/" + units[0].encoded_id);
    }

    function navigateToLastImage() {
        var units = getAvailableImages();
        if (!units.length) {
            return;
        }

        navigateTo("/view/" + units[units.length - 1].encoded_id);
    }

    function unitSupportsRegionDrawing(unit) {
        if (!unit || !unit.assets || unit.assets.length !== 1) {
            return false;
        }
        var assetType = unit.assets[0].type;
        return assetType === "image" || assetType === "svg";
    }

    // Pure hit-test helpers operate on normalized [0, 1] coordinates so they
    // are independent of overlay/image dimensions. The path tolerance is also
    // in normalized units; callers translate from screen pixels.
    function hitTestRect(px, py, region) {
        return px >= region.x && px <= region.x + region.w &&
               py >= region.y && py <= region.y + region.h;
    }

    function hitTestEllipse(px, py, region) {
        if (!region.rx || !region.ry) {
            return false;
        }
        var dx = (px - region.cx) / region.rx;
        var dy = (py - region.cy) / region.ry;
        return dx * dx + dy * dy <= 1;
    }

    function distancePointToSegment(px, py, x1, y1, x2, y2) {
        var dx = x2 - x1;
        var dy = y2 - y1;
        var lenSq = dx * dx + dy * dy;
        var t = 0;
        if (lenSq > 0) {
            t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
            if (t < 0) { t = 0; } else if (t > 1) { t = 1; }
        }
        var ex = px - (x1 + t * dx);
        var ey = py - (y1 + t * dy);
        return Math.sqrt(ex * ex + ey * ey);
    }

    function hitTestPath(px, py, region, tolerance) {
        var pts = region.points || [];
        if (pts.length < 2) {
            return false;
        }
        for (var i = 0; i < pts.length - 1; i++) {
            if (distancePointToSegment(
                    px, py,
                    pts[i][0], pts[i][1],
                    pts[i + 1][0], pts[i + 1][1]
                ) <= tolerance) {
                return true;
            }
        }
        // The path is rendered with closePath() in paintRegion, so include the
        // implicit closing segment in hit-testing for visual parity.
        var first = pts[0];
        var last = pts[pts.length - 1];
        return distancePointToSegment(
            px, py,
            last[0], last[1],
            first[0], first[1]
        ) <= tolerance;
    }

    function hitTestRegions(px, py, regions, pathTolerance) {
        // Topmost (last drawn) wins on overlap.
        for (var i = regions.length - 1; i >= 0; i--) {
            var r = regions[i];
            if (r.type === TOOL_RECT && hitTestRect(px, py, r)) { return r; }
            if (r.type === TOOL_ELLIPSE && hitTestEllipse(px, py, r)) { return r; }
            if (r.type === TOOL_PATH && hitTestPath(px, py, r, pathTolerance)) { return r; }
        }
        return null;
    }

    function setHighlightedSelection(state, selectionId) {
        if (state.highlightedSelectionId === selectionId) {
            return;
        }
        state.highlightedSelectionId = selectionId;
        syncHighlightedComment(selectionId);
        renderDrawState(state);
    }

    function syncHighlightedComment(selectionId) {
        var hovered = document.querySelectorAll(".comment-item.is-hovered");
        for (var i = 0; i < hovered.length; i++) {
            hovered[i].classList.remove("is-hovered");
        }
        if (selectionId == null) {
            return;
        }
        var match = document.querySelector(
            '.comment-item[data-selection-id="' + selectionId + '"]'
        );
        if (match) {
            match.classList.add("is-hovered");
        }
    }

    // ArrowUp/ArrowDown navigation through the comment list. Reuses the qh9
    // hover-highlight code path: setHighlightedSelection drives both
    // .is-hovered on the matching comment row and the canvas paint via
    // renderDrawState. Image-level rows (no data-selection-id) clear the
    // canvas highlight and we add .is-hovered manually so the focused row
    // still gets the visual treatment.
    //
    // Wrap behavior: enabled. Pressing ArrowDown on the last row jumps to
    // the first; ArrowUp on the first jumps to the last. Matches the feel
    // of the existing 1-9/0 numeric jump shortcuts on the index page.
    function focusAdjacentComment(direction) {
        var commentsList = document.getElementById("comments-list");
        if (!commentsList) {
            return;
        }
        var rows = Array.prototype.slice.call(
            commentsList.querySelectorAll(".comment-item")
        );
        if (rows.length === 0) {
            return;
        }
        var currentIndex = -1;
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].classList.contains("is-hovered")) {
                currentIndex = i;
                break;
            }
        }
        var nextIndex;
        if (direction > 0) {
            nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % rows.length;
        } else {
            nextIndex = currentIndex === -1
                ? rows.length - 1
                : (currentIndex - 1 + rows.length) % rows.length;
        }
        var row = rows[nextIndex];
        var selectionAttr = row.dataset.selectionId;
        var selectionId = selectionAttr ? parseInt(selectionAttr, 10) : null;
        if (currentRegionState) {
            setHighlightedSelection(currentRegionState, selectionId);
        } else {
            // Region drawing unavailable for this unit: no canvas to paint,
            // but we still drive the comment-row hover state directly so
            // navigation works on multi-asset / ANSI / non-image units.
            var hovered = commentsList.querySelectorAll(".comment-item.is-hovered");
            for (var j = 0; j < hovered.length; j++) {
                hovered[j].classList.remove("is-hovered");
            }
        }
        if (selectionId == null) {
            // Image-level row: setHighlightedSelection(state, null) cleared
            // .is-hovered from every row; restore it on the focused row.
            row.classList.add("is-hovered");
        }
        if (typeof row.scrollIntoView === "function") {
            row.scrollIntoView({ block: "nearest" });
        }
    }

    function setupRegionDrawing(unit, assetsContainer) {
        var state = {
            activeTool: TOOL_OFF,
            pendingRegion: null,
            existingRegions: [],
            overlay: null,
            ctx: null,
            drawState: null,
            imageElement: null,
            highlightedSelectionId: null,
            assetCard: null,
        };

        if (!unitSupportsRegionDrawing(unit)) {
            return state;
        }

        var toolbar = document.getElementById("detail-tools");
        if (!toolbar) {
            return state;
        }
        toolbar.hidden = false;

        var card = assetsContainer.querySelector(".asset-card");
        var image = card ? card.querySelector("img") : null;
        if (!card || !image) {
            return state;
        }

        card.classList.add("has-region-overlay");
        state.imageElement = image;
        state.assetCard = card;
        state.overlay = document.createElement("canvas");
        state.overlay.className = "region-overlay";
        card.appendChild(state.overlay);

        function syncCanvasSize() {
            var natW = image.naturalWidth || image.width;
            var natH = image.naturalHeight || image.height;
            if (!natW || !natH) {
                return;
            }
            state.overlay.width = natW;
            state.overlay.height = natH;
            state.overlay.style.width = image.clientWidth + "px";
            state.overlay.style.height = image.clientHeight + "px";
            // The overlay is position:absolute inside .asset-card. The card has
            // padding and a title row above the image, so inset:0 alone leaves
            // the overlay misaligned — extending into the title at top and
            // falling short of the image bottom. Pin it to the image's box.
            state.overlay.style.left = image.offsetLeft + "px";
            state.overlay.style.top = image.offsetTop + "px";
            state.ctx = state.overlay.getContext("2d");
            redraw(state);
        }

        if (image.complete && image.naturalWidth > 0) {
            syncCanvasSize();
        } else {
            image.addEventListener("load", syncCanvasSize);
        }
        window.addEventListener("resize", syncCanvasSize);

        state.overlay.addEventListener("mousedown", function (event) { onMouseDown(state, event); });
        state.overlay.addEventListener("mousemove", function (event) { onMouseMove(state, event); });
        state.overlay.addEventListener("mouseup", function (event) { onMouseUp(state, event); });
        state.overlay.addEventListener("mouseleave", function (event) { onMouseUp(state, event); });

        // Card-level hover drives the bidirectional hover-highlight (qh9). The
        // overlay has pointer-events:none in the OFF tool, so events arrive
        // on the card. In drawing modes the overlay captures events first;
        // we early-out below so drawing isn't disturbed.
        card.addEventListener("mousemove", function (event) { onCardHover(state, event); });
        card.addEventListener("mouseleave", function () { onCardLeave(state); });

        Array.prototype.slice.call(toolbar.querySelectorAll(".btn-tool")).forEach(function (btn) {
            btn.addEventListener("click", function () {
                setActiveTool(state, btn.getAttribute("data-tool"));
            });
        });

        var cancel = document.getElementById("cancel-pending-region");
        if (cancel) {
            cancel.addEventListener("click", function () {
                state.pendingRegion = null;
                hidePendingIndicator();
                redraw(state);
            });
        }

        return state;
    }

    function setActiveTool(state, tool) {
        state.activeTool = tool;
        var toolbar = document.getElementById("detail-tools");
        var toolButtons = toolbar ? toolbar.querySelectorAll(".btn-tool") : [];
        Array.prototype.slice.call(toolButtons).forEach(function (btn) {
            var isActive = btn.getAttribute("data-tool") === tool;
            btn.setAttribute("aria-pressed", isActive ? "true" : "false");
            btn.setAttribute("aria-checked", isActive ? "true" : "false");
        });
        if (!state.overlay) {
            return;
        }
        ALL_TOOL_OVERLAY_CLASSES.forEach(function (cls) {
            state.overlay.classList.remove(cls);
        });
        var nextClass = TOOL_OVERLAY_CLASS[tool];
        if (nextClass) {
            state.overlay.classList.add(nextClass);
        }
    }

    function clampUnit(value) {
        if (value < 0) return 0;
        if (value > 1) return 1;
        return value;
    }

    function pointFromEvent(state, event) {
        var rect = state.overlay.getBoundingClientRect();
        return [
            clampUnit((event.clientX - rect.left) / rect.width),
            clampUnit((event.clientY - rect.top) / rect.height),
        ];
    }

    function pointFromImageEvent(state, event) {
        if (!state.imageElement) {
            return null;
        }
        var rect = state.imageElement.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            return null;
        }
        var x = (event.clientX - rect.left) / rect.width;
        var y = (event.clientY - rect.top) / rect.height;
        if (x < 0 || x > 1 || y < 0 || y > 1) {
            return null;
        }
        return [x, y];
    }

    function onCardHover(state, event) {
        if (state.activeTool !== TOOL_OFF) {
            // Drawing modes own the cursor and the overlay events; don't
            // interfere with an in-progress draw.
            return;
        }
        var p = pointFromImageEvent(state, event);
        if (!p) {
            onCardLeave(state);
            return;
        }
        var rect = state.imageElement.getBoundingClientRect();
        var pathTol = PATH_HIT_PAD_PIXELS / Math.max(rect.width, rect.height, 1);
        var hit = hitTestRegions(p[0], p[1], state.existingRegions, pathTol);
        if (hit) {
            if (state.assetCard) {
                state.assetCard.classList.add("region-hover-active");
            }
            setHighlightedSelection(state, hit.selection_id || null);
        } else {
            if (state.assetCard) {
                state.assetCard.classList.remove("region-hover-active");
            }
            setHighlightedSelection(state, null);
        }
    }

    function onCardLeave(state) {
        if (state.assetCard) {
            state.assetCard.classList.remove("region-hover-active");
        }
        setHighlightedSelection(state, null);
    }

    function onMouseDown(state, event) {
        if (state.activeTool === TOOL_OFF) {
            return;
        }
        event.preventDefault();
        var p = pointFromEvent(state, event);
        if (state.activeTool === TOOL_RECT) {
            state.drawState = { type: TOOL_RECT, origin: p, current: p };
        } else if (state.activeTool === TOOL_ELLIPSE) {
            state.drawState = { type: TOOL_ELLIPSE, origin: p, current: p };
        } else {
            state.drawState = { type: TOOL_PATH, points: [p] };
        }
        renderDrawState(state);
    }

    function onMouseMove(state, event) {
        if (!state.drawState) {
            return;
        }
        var p = pointFromEvent(state, event);
        if (state.drawState.type === TOOL_RECT || state.drawState.type === TOOL_ELLIPSE) {
            state.drawState.current = p;
        } else {
            state.drawState.points.push(p);
        }
        renderDrawState(state);
    }

    function onMouseUp(state, _event) {
        if (!state.drawState) {
            return;
        }
        commitDrawState(state);
        state.drawState = null;
    }

    function renderDrawState(state) {
        if (!state.drawState) {
            redraw(state);
            return;
        }
        redraw(state);
        var preview = previewFromDrawState(state.drawState);
        if (preview) {
            paintRegion(state, preview, REGION_PENDING_DASH);
        }
    }

    function previewFromDrawState(drawState) {
        if (drawState.type === TOOL_RECT) {
            var x = Math.min(drawState.origin[0], drawState.current[0]);
            var y = Math.min(drawState.origin[1], drawState.current[1]);
            var w = Math.abs(drawState.current[0] - drawState.origin[0]);
            var h = Math.abs(drawState.current[1] - drawState.origin[1]);
            return { type: TOOL_RECT, x: x, y: y, w: w, h: h };
        }
        if (drawState.type === TOOL_ELLIPSE) {
            var cx = (drawState.origin[0] + drawState.current[0]) / 2;
            var cy = (drawState.origin[1] + drawState.current[1]) / 2;
            var rx = Math.abs(drawState.current[0] - drawState.origin[0]) / 2;
            var ry = Math.abs(drawState.current[1] - drawState.origin[1]) / 2;
            return { type: TOOL_ELLIPSE, cx: cx, cy: cy, rx: rx, ry: ry };
        }
        return { type: TOOL_PATH, points: drawState.points.slice() };
    }

    function commitDrawState(state) {
        var drawState = state.drawState;
        if (!drawState) {
            return;
        }
        if (drawState.type === TOOL_RECT) {
            var preview = previewFromDrawState(drawState);
            if (preview.w < MIN_RECT_NORMALIZED_SIZE || preview.h < MIN_RECT_NORMALIZED_SIZE) {
                return;
            }
            state.pendingRegion = preview;
        } else if (drawState.type === TOOL_ELLIPSE) {
            var ellipsePreview = previewFromDrawState(drawState);
            if (
                ellipsePreview.rx < MIN_ELLIPSE_NORMALIZED_RADIUS ||
                ellipsePreview.ry < MIN_ELLIPSE_NORMALIZED_RADIUS
            ) {
                return;
            }
            state.pendingRegion = ellipsePreview;
        } else {
            if (drawState.points.length < MIN_PATH_POINT_COUNT) {
                return;
            }
            state.pendingRegion = { type: TOOL_PATH, points: drawState.points.slice() };
        }
        showPendingIndicator(state.pendingRegion);
        redraw(state);
    }

    function redraw(state) {
        if (!state.ctx || !state.overlay) {
            return;
        }
        state.ctx.clearRect(0, 0, state.overlay.width, state.overlay.height);
        var highlightId = state.highlightedSelectionId;
        state.existingRegions.forEach(function (region) {
            var isHighlighted = highlightId != null &&
                region.selection_id === highlightId;
            paintRegion(state, region, REGION_COMMITTED_DASH, isHighlighted);
        });
        if (state.pendingRegion) {
            paintRegion(state, state.pendingRegion, REGION_PENDING_DASH, true);
        }
    }

    function paintRegion(state, region, dash, isEmphasized) {
        var ctx = state.ctx;
        var w = state.overlay.width;
        var h = state.overlay.height;
        var isCommitted = dash === REGION_COMMITTED_DASH;
        var dimmed = isCommitted && !isEmphasized;
        ctx.save();
        ctx.lineWidth = isEmphasized && isCommitted
            ? REGION_HIGHLIGHT_LINE_WIDTH
            : REGION_DEFAULT_LINE_WIDTH;
        ctx.strokeStyle = dimmed ? REGION_LINE_COLOR_DIM : REGION_LINE_COLOR;
        ctx.fillStyle = dimmed ? REGION_FILL_COLOR_DIM : REGION_FILL_COLOR;
        ctx.setLineDash(dash);
        if (region.type === TOOL_RECT) {
            ctx.beginPath();
            ctx.rect(region.x * w, region.y * h, region.w * w, region.h * h);
            ctx.fill();
            ctx.stroke();
        } else if (region.type === TOOL_ELLIPSE) {
            ctx.beginPath();
            ctx.ellipse(
                region.cx * w,
                region.cy * h,
                region.rx * w,
                region.ry * h,
                0,
                0,
                Math.PI * 2
            );
            ctx.fill();
            ctx.stroke();
        } else if (region.type === TOOL_PATH) {
            var points = region.points || [];
            if (points.length > 0) {
                ctx.beginPath();
                ctx.moveTo(points[0][0] * w, points[0][1] * h);
                for (var i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i][0] * w, points[i][1] * h);
                }
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
            }
        }
        ctx.restore();

        if (dash === REGION_COMMITTED_DASH && region.selection_id) {
            var anchor = selectionBadgeAnchor(region, w, h);
            if (anchor) {
                paintSelectionBadge(state, anchor[0], anchor[1], region.selection_id);
            }
        }
    }

    function selectionBadgeAnchor(region, w, h) {
        if (region.type === TOOL_RECT) {
            return [region.x * w, region.y * h];
        }
        if (region.type === TOOL_ELLIPSE) {
            // Anchor at the top-left of the ellipse's bounding box so the badge
            // sits in the same place as it would for an enclosing rect.
            return [(region.cx - region.rx) * w, (region.cy - region.ry) * h];
        }
        if (region.type === TOOL_PATH && region.points && region.points.length) {
            return [region.points[0][0] * w, region.points[0][1] * h];
        }
        return null;
    }

    function selectionBadgeScale(state) {
        if (!state.imageElement || !state.imageElement.clientWidth) {
            return 1;
        }
        var ratio = state.overlay.width / state.imageElement.clientWidth;
        return ratio > 1 ? ratio : 1;
    }

    function paintSelectionBadge(state, anchorX, anchorY, selectionId) {
        var ctx = state.ctx;
        var scale = selectionBadgeScale(state);
        var fontPx = SELECTION_BADGE_FONT_PX * scale;
        var paddingX = SELECTION_BADGE_PADDING_X * scale;
        var paddingY = SELECTION_BADGE_PADDING_Y * scale;
        var radius = SELECTION_BADGE_RADIUS * scale;
        var offset = SELECTION_BADGE_OFFSET * scale;
        var label = String(selectionId);

        ctx.save();
        ctx.setLineDash([]);
        ctx.font = "600 " + fontPx + "px sans-serif";
        ctx.textBaseline = "middle";
        ctx.textAlign = "left";
        var textWidth = ctx.measureText(label).width;
        var badgeWidth = textWidth + paddingX * 2;
        var badgeHeight = fontPx + paddingY * 2;

        var maxX = state.overlay.width - badgeWidth;
        var maxY = state.overlay.height - badgeHeight;
        var bx = anchorX + offset;
        var by = anchorY + offset;
        if (bx > maxX) { bx = maxX; }
        if (by > maxY) { by = maxY; }
        if (bx < 0) { bx = 0; }
        if (by < 0) { by = 0; }

        ctx.fillStyle = SELECTION_BADGE_FILL;
        ctx.strokeStyle = SELECTION_BADGE_STROKE;
        ctx.lineWidth = Math.max(1, scale);
        traceRoundedRect(ctx, bx, by, badgeWidth, badgeHeight, radius);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = SELECTION_BADGE_TEXT_COLOR;
        ctx.fillText(label, bx + paddingX, by + badgeHeight / 2);
        ctx.restore();
    }

    function traceRoundedRect(ctx, x, y, w, h, r) {
        var radius = Math.min(r, w / 2, h / 2);
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.arcTo(x + w, y, x + w, y + h, radius);
        ctx.arcTo(x + w, y + h, x, y + h, radius);
        ctx.arcTo(x, y + h, x, y, radius);
        ctx.arcTo(x, y, x + w, y, radius);
        ctx.closePath();
    }

    function showPendingIndicator(region) {
        var indicator = document.getElementById("pending-region-indicator");
        var typeLabel = document.getElementById("pending-region-type");
        if (indicator) {
            indicator.hidden = false;
        }
        if (typeLabel && region) {
            typeLabel.textContent = region.type;
        }
    }

    function hidePendingIndicator() {
        var indicator = document.getElementById("pending-region-indicator");
        if (indicator) {
            indicator.hidden = true;
        }
    }

    function cycleActiveTool() {
        var pressed = document.querySelector(".btn-tool[aria-pressed='true']");
        var current = pressed ? pressed.getAttribute("data-tool") : TOOL_OFF;
        var idx = TOOL_ORDER.indexOf(current);
        var next = TOOL_ORDER[(idx + 1) % TOOL_ORDER.length];
        var nextButton = document.querySelector(".btn-tool[data-tool='" + next + "']");
        if (nextButton) {
            nextButton.click();
        }
    }

    function initDetail() {
        var assetsContainer = document.getElementById("unit-assets");
        var metadataContainer = document.getElementById("unit-metadata");
        var previousSlot = document.getElementById("prev-slot");
        var nextSlot = document.getElementById("next-slot");
        var indexButton = document.getElementById("index-btn");
        var copyFilenameButton = document.getElementById("copy-filename-btn");

        currentUnit.assets.forEach(function (asset) {
            assetsContainer.appendChild(createAssetCard(asset));
        });

        initVizdiffDetailModes(currentUnit);
        // The detail legend hardcodes a 'd cycle tool' entry server-side so
        // we can toggle it here using the same predicate that gates the 'd'
        // keypress and the region-drawing setup. This avoids advertising the
        // shortcut on units (multi-asset, ANSI, non-image) where pressing
        // 'd' is a no-op.
        var regionLegendEntry = document.getElementById("legend-region-drawing");
        if (regionLegendEntry) {
            regionLegendEntry.hidden = !unitSupportsRegionDrawing(currentUnit);
        }
        var regionState = setupRegionDrawing(currentUnit, assetsContainer);
        currentRegionState = regionState;

        previousSlot.appendChild(
            createNavigationButton({
                id: "prev-btn",
                label: "Previous",
                destination: detailPage.nav.prev,
                detailName: detailPage.nav.prev_label,
                direction: "previous",
            })
        );

        nextSlot.appendChild(
            createNavigationButton({
                id: "next-btn",
                label: "Next",
                destination: detailPage.nav.next,
                detailName: detailPage.nav.next_label,
                direction: "next",
            })
        );

        if (indexButton) {
            bindInternalNavigation(indexButton);
        }

        if (copyFilenameButton) {
            copyFilenameButton.addEventListener("click", copyFilenameToClipboard);
        }

        var commentForm = document.getElementById("comment-form");
        var commentInput = document.getElementById("comment-input");
        var commentSubmit = commentForm.querySelector("button[type='submit']");
        var commentsList = document.getElementById("comments-list");
        var selectionIdCounter = 0;
        var commentStatus = document.createElement("div");
        commentStatus.className = "comment-status";
        commentForm.insertAdjacentElement("afterend", commentStatus);

        if (commentSubmit) {
            serverActionButtons.push(commentSubmit);
            commentSubmit.disabled = !isServerReachable;
        }

        renderMetadata(metadataContainer, currentUnit.metadata);
        loadComments();

        commentForm.addEventListener("submit", function (event) {
            event.preventDefault();
            commentStatus.textContent = "";
            if (!isServerReachable) {
                showServerDown("Bugshot server is unreachable. This comment was not saved.");
                commentStatus.textContent = "Comment was not saved because the server is unreachable.";
                return;
            }

            var body = commentInput.value.trim();
            if (!body) {
                return;
            }

            var submittedRegion = regionState.pendingRegion || null;
            var payload = { unit_id: currentUnit.id, body: body };
            if (submittedRegion) {
                payload.region = submittedRegion;
            }

            fetchJson("/api/comments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
                .then(function (comment) {
                    commentInput.value = "";
                    commentStatus.textContent = "";
                    appendComment(comment);
                    if (submittedRegion) {
                        if (comment.region && comment.region.selection_id) {
                            submittedRegion.selection_id = comment.region.selection_id;
                        }
                        regionState.existingRegions.push(submittedRegion);
                        if (regionState.pendingRegion === submittedRegion) {
                            regionState.pendingRegion = null;
                            hidePendingIndicator();
                        }
                        redraw(regionState);
                    }
                })
                .catch(function () {
                    showServerDown("Bugshot server is unreachable. This comment was not saved.");
                    commentStatus.textContent = "Comment was not saved. Keep the text here and try again after reconnecting.";
                });
        });

        function loadComments() {
            fetchJson("/api/comments?unit_id=" + encodeURIComponent(currentUnit.id))
                .then(function (comments) {
                    commentsList.textContent = "";
                    commentStatus.textContent = "";
                    selectionIdCounter = 0;
                    comments.forEach(appendComment);
                    regionState.existingRegions = comments
                        .map(function (c) { return c.region; })
                        .filter(function (r) { return r != null; });
                    redraw(regionState);
                })
                .catch(function () {
                    showServerDown("Bugshot server is unreachable. Existing comments could not be loaded.");
                    commentStatus.textContent = "Existing comments could not be loaded.";
                });
        }

        function appendComment(comment) {
            var item = document.createElement("div");
            item.className = "comment-item";
            item.dataset.id = comment.id;

            var badge = document.createElement("span");
            badge.className = "region-badge";
            if (comment.region) {
                if (!comment.region.selection_id) {
                    selectionIdCounter += 1;
                    comment.region.selection_id = selectionIdCounter;
                }
                var selectionId = comment.region.selection_id;
                badge.textContent = "Selection " + selectionId;
                item.dataset.selectionId = selectionId;
                // Bidirectional hover-highlight (qh9): hovering the comment
                // emphasizes the matching region on the canvas. The reverse
                // direction (canvas → comment) is wired in onCardHover.
                item.addEventListener("mouseenter", function () {
                    setHighlightedSelection(regionState, selectionId);
                });
                item.addEventListener("mouseleave", function () {
                    setHighlightedSelection(regionState, null);
                });
            } else {
                badge.textContent = "⬚ image";
            }
            item.appendChild(badge);

            var bodyElement = document.createElement("span");
            bodyElement.className = "comment-body";
            bodyElement.textContent = comment.body;

            var actions = document.createElement("span");
            actions.className = "comment-actions";

            var editButton = document.createElement("button");
            editButton.textContent = "edit";
            editButton.addEventListener("click", function () {
                var nextBody = prompt("Edit comment:", comment.body);
                if (nextBody !== null && nextBody.trim()) {
                    fetchJson("/api/comments/" + comment.id, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ body: nextBody.trim() }),
                    })
                        .then(function (updated) {
                            commentStatus.textContent = "";
                            bodyElement.textContent = updated.body;
                            comment.body = updated.body;
                        })
                        .catch(function () {
                            showServerDown("Bugshot server is unreachable. Comment edit was not saved.");
                            commentStatus.textContent = "Comment edit was not saved.";
                        });
                }
            });

            var deleteButton = document.createElement("button");
            deleteButton.textContent = "delete";
            deleteButton.addEventListener("click", function () {
                if (confirm("Delete this comment?")) {
                    fetch("/api/comments/" + comment.id, { method: "DELETE" })
                        .then(requireOkResponse)
                        .then(function () {
                            setServerReachable(true);
                            commentStatus.textContent = "";
                            item.remove();
                        })
                        .catch(function () {
                            showServerDown("Bugshot server is unreachable. Comment was not deleted.");
                            commentStatus.textContent = "Comment was not deleted.";
                        });
                }
            });

            actions.appendChild(editButton);
            actions.appendChild(deleteButton);
            item.appendChild(bodyElement);
            item.appendChild(actions);
            commentsList.appendChild(item);
        }
    }

    function createAssetCard(asset) {
        var card = document.createElement("section");
        card.className = "asset-card";

        var title = document.createElement("div");
        title.className = "asset-title";
        title.textContent = asset.name;
        card.appendChild(title);

        appendAssetPreview(card, asset, false);
        return card;
    }

    function renderMetadata(container, metadataItems) {
        if (!container) {
            return;
        }

        container.textContent = "";
        if (!metadataItems.length) {
            container.classList.add("is-hidden");
            return;
        }

        container.classList.remove("is-hidden");

        metadataItems.forEach(function (item) {
            var card = document.createElement("section");
            card.className = "metadata-card";

            var title = document.createElement("div");
            title.className = "metadata-title";
            title.textContent = item.name;
            card.appendChild(title);

            if (item.parse_error) {
                var warning = document.createElement("div");
                warning.className = "metadata-warning";
                warning.textContent = item.parse_error;
                card.appendChild(warning);
            }

            if (isRenderableMetadataTable(item.content)) {
                card.appendChild(renderMetadataTable(item.content));
            } else {
                var body = document.createElement("pre");
                body.className = "metadata-body";
                body.textContent = item.display_text;
                card.appendChild(body);
            }

            container.appendChild(card);
        });
    }

    function isRenderableMetadataTable(content) {
        return content && typeof content === "object" && !Array.isArray(content);
    }

    function renderMetadataTable(content) {
        var table = document.createElement("table");
        table.className = "metadata-table";

        var head = document.createElement("thead");
        var headRow = document.createElement("tr");
        ["Field", "Value"].forEach(function (text) {
            var cell = document.createElement("th");
            cell.textContent = text;
            headRow.appendChild(cell);
        });
        head.appendChild(headRow);
        table.appendChild(head);

        var body = document.createElement("tbody");
        Object.keys(content).forEach(function (key) {
            var row = document.createElement("tr");

            var keyCell = document.createElement("th");
            keyCell.className = "metadata-key";
            keyCell.textContent = key;
            row.appendChild(keyCell);

            var valueCell = document.createElement("td");
            valueCell.className = "metadata-value";
            appendMetadataValue(valueCell, content[key]);
            row.appendChild(valueCell);

            body.appendChild(row);
        });
        table.appendChild(body);
        return table;
    }

    function appendMetadataValue(cell, value) {
        if (value === null || typeof value === "undefined") {
            cell.textContent = "";
            return;
        }

        if (typeof value === "object") {
            var jsonValue = document.createElement("pre");
            jsonValue.className = "metadata-cell-json";
            jsonValue.textContent = JSON.stringify(value, null, 2);
            cell.appendChild(jsonValue);
            return;
        }

        cell.textContent = String(value);
    }

    function bindInternalNavigation(link) {
        link.addEventListener("click", function () {
            isInternalNavigation = true;
        });
    }

    function createNavigationButton(config) {
        if (!config.destination) {
            var disabledButton = document.createElement("span");
            disabledButton.className = "btn btn-disabled";
            disabledButton.id = config.id;
            disabledButton.textContent = config.label;
            disabledButton.setAttribute("aria-disabled", "true");
            return disabledButton;
        }

        var link = document.createElement("a");
        link.href = config.destination;
        link.className = "btn";
        link.id = config.id;

        if (config.direction === "previous") {
            link.textContent = "\u2190 " + config.detailName;
        } else {
            link.textContent = config.detailName + " \u2192";
        }

        bindInternalNavigation(link);
        return link;
    }

    function navigateTo(path) {
        isInternalNavigation = true;
        window.location.href = path;
    }

    function getAvailableImages() {
        if (isIndex) {
            return window.__BUGSHOT_UNITS__ || [];
        }
        if (isDetail) {
            return detailPage.units || [];
        }
        return [];
    }

    function navigateToImageByShortcut(key) {
        var units = getAvailableImages();
        if (!units.length) {
            return;
        }

        if (key === "0") {
            navigateTo("/view/" + units[units.length - 1].encoded_id);
            return;
        }

        var imageNumber = parseInt(key, 10);
        navigateToImageNumber(imageNumber);
    }

    function navigateToImageNumber(imageNumber) {
        var units = getAvailableImages();
        if (!units.length) {
            return false;
        }
        if (!Number.isInteger(imageNumber) || imageNumber < 1 || imageNumber > units.length) {
            return false;
        }

        navigateTo("/view/" + units[imageNumber - 1].encoded_id);
        return true;
    }

    function isJumpModalOpen() {
        return jumpModal && !jumpModal.classList.contains("is-hidden");
    }

    function openJumpModal() {
        if (!jumpModal) {
            return;
        }
        jumpModal.classList.remove("is-hidden");
        jumpModalInput.value = "";
        jumpModalError.textContent = "";
        jumpModalInput.focus();
        jumpModalInput.select();
    }

    function closeJumpModal() {
        if (!jumpModal) {
            return;
        }
        jumpModal.classList.add("is-hidden");
        jumpModalError.textContent = "";
    }

    function submitJumpModal() {
        var rawValue = jumpModalInput.value.trim();
        var imageNumber = parseInt(rawValue, 10);

        if (!rawValue || !/^\d+$/.test(rawValue)) {
            jumpModalError.textContent = "Enter a valid unit number.";
            return;
        }

        if (!navigateToImageNumber(imageNumber)) {
            jumpModalError.textContent = "That unit number does not exist.";
            return;
        }
    }

    function handleJumpModalKeydown(event) {
        if (event.key === "Escape") {
            closeJumpModal();
            event.preventDefault();
            return;
        }

        if (event.key !== SHORTCUT_KEY_ENTER) {
            return;
        }

        submitJumpModal();
        event.preventDefault();
    }

    function copyFilenameToClipboard() {
        if (!isDetail || !currentUnit) {
            return;
        }

        writeClipboardText(currentUnit.id)
            .then(function () {
                showCopyFilenameStatus("Copied", false);
            })
            .catch(function () {
                showCopyFilenameStatus("Copy failed", true);
            });
    }

    function writeClipboardText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text).catch(function () {
                return fallbackCopyText(text);
            });
        }

        return fallbackCopyText(text);
    }

    function fallbackCopyText(text) {
        return new Promise(function (resolve, reject) {
            var textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.setAttribute("readonly", "");
            textArea.style.position = "fixed";
            textArea.style.left = "-9999px";
            textArea.style.top = "0";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                if (document.execCommand("copy")) {
                    resolve();
                } else {
                    reject(new Error("Copy command failed"));
                }
            } catch (error) {
                reject(error);
            } finally {
                document.body.removeChild(textArea);
            }
        });
    }

    function showCopyFilenameStatus(message, isError) {
        var status = document.getElementById("copy-filename-status");
        if (!status) {
            return;
        }

        status.textContent = message;
        status.classList.toggle("is-error", isError);

        if (copyFilenameStatusTimeout) {
            clearTimeout(copyFilenameStatusTimeout);
        }

        copyFilenameStatusTimeout = setTimeout(function () {
            status.textContent = "";
            status.classList.remove("is-error");
        }, 2000);
    }

    function toggleIndexSize() {
        if (!isIndex) {
            return;
        }

        var gallery = document.getElementById("gallery");
        var sizeToggle = document.getElementById("size-toggle");
        var isFullSize = gallery.classList.contains("fullsize-mode");
        var nextFullSizeState = !isFullSize;

        gallery.classList.toggle("thumbnail-mode", !nextFullSizeState);
        gallery.classList.toggle("fullsize-mode", nextFullSizeState);
        sizeToggle.textContent = nextFullSizeState ? "Thumbnails" : "Full Size";
    }

    function focusCommentInput() {
        var input = document.getElementById("comment-input");
        if (input) {
            input.focus();
        }
    }
})();
