(function () {
    "use strict";

    // ---- Constants ----
    var HEARTBEAT_INTERVAL_MS = 5000;

    // ---- Page detection ----
    var isIndex = !!window.__BUGSHOT_IMAGES__;
    var isDetail = !!window.__BUGSHOT_DETAIL__;
    var detail = window.__BUGSHOT_DETAIL__ || null;

    // ---- Heartbeat ----
    setInterval(function () {
        fetch("/api/heartbeat", { method: "POST" }).catch(function () {});
    }, HEARTBEAT_INTERVAL_MS);

    // ---- Browser close detection ----
    window.addEventListener("beforeunload", function () {
        navigator.sendBeacon("/api/closed");
    });

    // ---- Done button (index page) ----
    var doneBtn = document.getElementById("done-btn");
    if (doneBtn) {
        doneBtn.addEventListener("click", function () {
            if (confirm("Done reviewing? This will end the session.")) {
                fetch("/api/done", { method: "POST" })
                    .then(function () {
                        document.body.textContent = "";
                        var msg = document.createElement("div");
                        msg.style.cssText =
                            "display:flex;align-items:center;justify-content:center;" +
                            "height:100vh;color:#e0e0e0;font-size:18px;";
                        msg.textContent = "Session complete. You can close this tab.";
                        document.body.appendChild(msg);
                    });
            }
        });
    }

    // ---- Index page ----
    if (isIndex) {
        initIndex();
    }

    // ---- Detail page ----
    if (isDetail) {
        initDetail();
    }

    // ---- Keyboard shortcuts ----
    document.addEventListener("keydown", function (e) {
        var isTyping = document.activeElement &&
            (document.activeElement.tagName === "INPUT" ||
             document.activeElement.tagName === "TEXTAREA");

        if (isTyping) {
            if (e.key === "Escape") {
                document.activeElement.blur();
                e.preventDefault();
            }
            return;
        }

        if (isDetail) {
            if (e.key === "ArrowLeft" && detail.nav.prev) {
                window.location.href = detail.nav.prev;
                e.preventDefault();
            } else if (e.key === "ArrowRight" && detail.nav.next) {
                window.location.href = detail.nav.next;
                e.preventDefault();
            } else if (e.key === "Escape") {
                window.location.href = "/";
                e.preventDefault();
            } else if (e.key === "c") {
                var input = document.getElementById("comment-input");
                if (input) {
                    input.focus();
                    e.preventDefault();
                }
            }
        }
    });

    // ---- Index functions ----

    function initIndex() {
        var images = window.__BUGSHOT_IMAGES__;
        var gallery = document.getElementById("gallery");
        var sizeToggle = document.getElementById("size-toggle");

        // Render gallery items using DOM methods
        images.forEach(function (img) {
            var item = document.createElement("a");
            item.className = "gallery-item";
            item.href = "/view/" + img.encoded_name;

            if (img.type === "image") {
                var imgEl = document.createElement("img");
                imgEl.src = img.src;
                imgEl.alt = img.name;
                item.appendChild(imgEl);
            } else {
                // ANSI preview: server-rendered HTML from local .ansi files, safe to inject
                var previewDiv = document.createElement("div");
                previewDiv.className = "ansi-preview";
                var pre = document.createElement("pre");
                pre.innerHTML = img.preview_html; // safe: server-processed ANSI from local files
                previewDiv.appendChild(pre);
                item.appendChild(previewDiv);
            }

            var label = document.createElement("div");
            label.className = "item-label";
            label.textContent = img.name;
            item.appendChild(label);

            gallery.appendChild(item);
        });

        // Size toggle
        var isFullSize = false;
        sizeToggle.addEventListener("click", function () {
            isFullSize = !isFullSize;
            gallery.classList.toggle("thumbnail-mode", !isFullSize);
            gallery.classList.toggle("fullsize-mode", isFullSize);
            sizeToggle.textContent = isFullSize ? "Thumbnails" : "Full Size";
        });
    }

    // ---- Detail functions ----

    function initDetail() {
        var container = document.getElementById("image-container");
        var navArrows = document.querySelector(".nav-arrows");

        // Render image or ANSI content
        if (detail.contentType === "image") {
            var img = document.createElement("img");
            img.src = detail.imageSrc;
            img.alt = detail.filename;
            container.appendChild(img);
        } else {
            // ANSI content: server-rendered HTML from local .ansi files, safe to inject
            var ansiDiv = document.createElement("div");
            ansiDiv.className = "ansi-rendered";
            var pre = document.createElement("pre");
            pre.innerHTML = detail.ansiHtml; // safe: server-processed ANSI from local files
            ansiDiv.appendChild(pre);
            container.appendChild(ansiDiv);
        }

        // Render nav arrows using DOM methods
        if (detail.nav.prev) {
            var prevLink = document.createElement("a");
            prevLink.href = detail.nav.prev;
            prevLink.className = "btn";
            prevLink.id = "prev-btn";
            prevLink.textContent = "\u2190 " + detail.nav.prev_name;
            navArrows.appendChild(prevLink);
        }
        if (detail.nav.next) {
            var nextLink = document.createElement("a");
            nextLink.href = detail.nav.next;
            nextLink.className = "btn";
            nextLink.id = "next-btn";
            nextLink.textContent = detail.nav.next_name + " \u2192";
            navArrows.appendChild(nextLink);
        }

        // ---- Comments ----
        var commentForm = document.getElementById("comment-form");
        var commentInput = document.getElementById("comment-input");
        var commentsList = document.getElementById("comments-list");

        loadComments();

        commentForm.addEventListener("submit", function (e) {
            e.preventDefault();
            var body = commentInput.value.trim();
            if (!body) return;

            fetch("/api/comments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image: detail.filename, body: body }),
            })
                .then(function (r) { return r.json(); })
                .then(function (comment) {
                    commentInput.value = "";
                    appendComment(comment);
                });
        });

        function loadComments() {
            fetch("/api/comments?image=" + encodeURIComponent(detail.filename))
                .then(function (r) { return r.json(); })
                .then(function (comments) {
                    commentsList.textContent = "";
                    comments.forEach(appendComment);
                });
        }

        function appendComment(comment) {
            var item = document.createElement("div");
            item.className = "comment-item";
            item.dataset.id = comment.id;

            var bodyEl = document.createElement("span");
            bodyEl.className = "comment-body";
            bodyEl.textContent = comment.body;

            var actions = document.createElement("span");
            actions.className = "comment-actions";

            var editBtn = document.createElement("button");
            editBtn.textContent = "edit";
            editBtn.addEventListener("click", function () {
                var newBody = prompt("Edit comment:", comment.body);
                if (newBody !== null && newBody.trim()) {
                    fetch("/api/comments/" + comment.id, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ body: newBody.trim() }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (updated) {
                            bodyEl.textContent = updated.body;
                            comment.body = updated.body;
                        });
                }
            });

            var deleteBtn = document.createElement("button");
            deleteBtn.textContent = "delete";
            deleteBtn.addEventListener("click", function () {
                if (confirm("Delete this comment?")) {
                    fetch("/api/comments/" + comment.id, { method: "DELETE" })
                        .then(function () {
                            item.remove();
                        });
                }
            });

            actions.appendChild(editBtn);
            actions.appendChild(deleteBtn);
            item.appendChild(bodyEl);
            item.appendChild(actions);
            commentsList.appendChild(item);
        }
    }
})();
