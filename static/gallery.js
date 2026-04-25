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
    var DIGIT_KEYS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
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
        } else if (event.key === SHORTCUT_KEY_FOCUS_COMMENT && isDetail) {
            focusCommentInput();
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
        var gallery = document.getElementById("gallery");

        units.forEach(function (unitInfo) {
            var item = document.createElement("a");
            item.className = "gallery-item";
            item.href = "/view/" + unitInfo.encoded_id;
            bindInternalNavigation(item);

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

            fetchJson("/api/comments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ unit_id: currentUnit.id, body: body }),
            })
                .then(function (comment) {
                    commentInput.value = "";
                    commentStatus.textContent = "";
                    appendComment(comment);
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
                    comments.forEach(appendComment);
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
