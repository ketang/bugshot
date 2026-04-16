(function () {
    "use strict";

    var HEARTBEAT_INTERVAL_MS = 5000;
    var INDEX_PATH = "/";
    var SHORTCUT_KEY_SIZE = "s";
    var SHORTCUT_KEY_NEXT = "n";
    var SHORTCUT_KEY_PREVIOUS = "p";
    var SHORTCUT_KEY_INDEX = "i";
    var SHORTCUT_KEY_QUIT = "q";
    var SHORTCUT_KEY_FOCUS_COMMENT = "/";

    var isIndex = !!window.__BUGSHOT_IMAGES__;
    var isDetail = !!window.__BUGSHOT_DETAIL__;
    var detail = window.__BUGSHOT_DETAIL__ || null;
    var isInternalNavigation = false;

    setInterval(function () {
        fetch("/api/heartbeat", { method: "POST" }).catch(function () {});
    }, HEARTBEAT_INTERVAL_MS);

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

    document.addEventListener("keydown", function (event) {
        var activeElement = document.activeElement;
        var isTyping = activeElement &&
            (activeElement.tagName === "INPUT" || activeElement.tagName === "TEXTAREA");

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
        } else if (event.key === SHORTCUT_KEY_NEXT && isDetail && detail.nav.next) {
            navigateTo(detail.nav.next);
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_PREVIOUS && isDetail && detail.nav.prev) {
            navigateTo(detail.nav.prev);
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_INDEX) {
            navigateTo(INDEX_PATH);
            event.preventDefault();
        } else if (event.key === SHORTCUT_KEY_QUIT) {
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

        button.addEventListener("click", function () {
            if (confirm("Done reviewing? This will end the session.")) {
                completeSession();
            }
        });
    }

    function completeSession() {
        fetch("/api/done", { method: "POST" })
            .then(function () {
                document.body.textContent = "";
                var message = document.createElement("div");
                message.style.cssText =
                    "display:flex;align-items:center;justify-content:center;" +
                    "height:100vh;color:#e0e0e0;font-size:18px;";
                message.textContent = "Session complete. You can close this tab.";
                document.body.appendChild(message);
            });
    }

    function initIndex() {
        var images = window.__BUGSHOT_IMAGES__;
        var gallery = document.getElementById("gallery");

        images.forEach(function (imageInfo) {
            var item = document.createElement("a");
            item.className = "gallery-item";
            item.href = "/view/" + imageInfo.encoded_name;
            bindInternalNavigation(item);

            if (imageInfo.type === "image") {
                var imageElement = document.createElement("img");
                imageElement.src = imageInfo.src;
                imageElement.alt = imageInfo.name;
                item.appendChild(imageElement);
            } else {
                var previewDiv = document.createElement("div");
                previewDiv.className = "ansi-preview";
                var previewPre = document.createElement("pre");
                previewPre.innerHTML = imageInfo.preview_html;
                previewDiv.appendChild(previewPre);
                item.appendChild(previewDiv);
            }

            var label = document.createElement("div");
            label.className = "item-label";
            label.textContent = imageInfo.name;
            item.appendChild(label);

            gallery.appendChild(item);
        });
    }

    function initDetail() {
        var container = document.getElementById("image-container");
        var previousSlot = document.getElementById("prev-slot");
        var nextSlot = document.getElementById("next-slot");
        var indexButton = document.getElementById("index-btn");

        if (detail.contentType === "image") {
            var imageElement = document.createElement("img");
            imageElement.src = detail.imageSrc;
            imageElement.alt = detail.filename;
            container.appendChild(imageElement);
        } else {
            var ansiDiv = document.createElement("div");
            ansiDiv.className = "ansi-rendered";
            var ansiPre = document.createElement("pre");
            ansiPre.innerHTML = detail.ansiHtml;
            ansiDiv.appendChild(ansiPre);
            container.appendChild(ansiDiv);
        }

        if (detail.nav.prev) {
            var previousLink = document.createElement("a");
            previousLink.href = detail.nav.prev;
            previousLink.className = "btn";
            previousLink.id = "prev-btn";
            previousLink.textContent = "\u2190 " + detail.nav.prev_name;
            bindInternalNavigation(previousLink);
            previousSlot.appendChild(previousLink);
        }

        if (detail.nav.next) {
            var nextLink = document.createElement("a");
            nextLink.href = detail.nav.next;
            nextLink.className = "btn";
            nextLink.id = "next-btn";
            nextLink.textContent = detail.nav.next_name + " \u2192";
            bindInternalNavigation(nextLink);
            nextSlot.appendChild(nextLink);
        }

        if (indexButton) {
            bindInternalNavigation(indexButton);
        }

        var commentForm = document.getElementById("comment-form");
        var commentInput = document.getElementById("comment-input");
        var commentsList = document.getElementById("comments-list");

        loadComments();

        commentForm.addEventListener("submit", function (event) {
            event.preventDefault();
            var body = commentInput.value.trim();
            if (!body) {
                return;
            }

            fetch("/api/comments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image: detail.filename, body: body }),
            })
                .then(function (response) { return response.json(); })
                .then(function (comment) {
                    commentInput.value = "";
                    appendComment(comment);
                });
        });

        function loadComments() {
            fetch("/api/comments?image=" + encodeURIComponent(detail.filename))
                .then(function (response) { return response.json(); })
                .then(function (comments) {
                    commentsList.textContent = "";
                    comments.forEach(appendComment);
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
                    fetch("/api/comments/" + comment.id, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ body: nextBody.trim() }),
                    })
                        .then(function (response) { return response.json(); })
                        .then(function (updated) {
                            bodyElement.textContent = updated.body;
                            comment.body = updated.body;
                        });
                }
            });

            var deleteButton = document.createElement("button");
            deleteButton.textContent = "delete";
            deleteButton.addEventListener("click", function () {
                if (confirm("Delete this comment?")) {
                    fetch("/api/comments/" + comment.id, { method: "DELETE" })
                        .then(function () {
                            item.remove();
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

    function bindInternalNavigation(link) {
        link.addEventListener("click", function () {
            isInternalNavigation = true;
        });
    }

    function navigateTo(path) {
        isInternalNavigation = true;
        window.location.href = path;
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
