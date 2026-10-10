/* X documentation — plain JavaScript, no dependencies.
   Fixed shell: theme, mobile menu, syntax highlighting, copy buttons,
   table of contents, and scroll highlighting. All content comes from
   README.md (see markdown.js); edit that file, never this one. */

"use strict";

/* ---------- Theme ---------- */

var STORAGE_KEY = "x-docs-theme";

function systemPrefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var button = document.getElementById("theme-toggle");
    if (button) {
        button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
    }
}

function initTheme() {
    var stored = null;
    try {
        stored = localStorage.getItem(STORAGE_KEY);
    } catch (error) {
        stored = null;
    }
    applyTheme(stored || (systemPrefersDark() ? "dark" : "light"));

    var button = document.getElementById("theme-toggle");
    if (!button) {
        return;
    }
    button.addEventListener("click", function () {
        var next = document.documentElement.getAttribute("data-theme") === "dark"
            ? "light" : "dark";
        applyTheme(next);
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (error) {
            /* private mode: theme still applies for this visit */
        }
    });
}

/* ---------- Mobile menu ---------- */

function initMobileMenu() {
    var menuButton = document.getElementById("menu-toggle");
    var sidebar = document.getElementById("sidebar");
    var overlay = document.getElementById("overlay");
    if (!menuButton || !sidebar || !overlay) {
        return;
    }

    function close() {
        sidebar.classList.remove("open");
        overlay.classList.remove("show");
        menuButton.setAttribute("aria-expanded", "false");
    }

    menuButton.addEventListener("click", function () {
        var open = sidebar.classList.toggle("open");
        overlay.classList.toggle("show", open);
        menuButton.setAttribute("aria-expanded", String(open));
    });
    overlay.addEventListener("click", close);
    sidebar.addEventListener("click", function (event) {
        if (event.target.tagName === "A") {
            close();
        }
    });
}

/* ---------- Status and errors ---------- */

function setStatus(text) {
    var node = document.getElementById("doc-status");
    if (node) {
        node.textContent = text;
    }
}

function showFetchError() {
    var box = document.getElementById("fetch-error");
    if (box) {
        box.classList.add("visible");
    }
}

/* ---------- On-this-page table of contents ---------- */

function buildToc() {
    var container = document.getElementById("doc-toc");
    if (!container) {
        return;
    }
    var entries = [];
    document.querySelectorAll("#doc-view h2[id], #doc-view h3[id]").forEach(function (h) {
        entries.push({
            id: h.id,
            text: h.textContent.trim(),
            level: h.tagName === "H3" ? 3 : 2
        });
    });
    if (!entries.length) {
        container.style.display = "none";
        return;
    }

    var list = document.createElement("ul");
    entries.forEach(function (entry) {
        var li = document.createElement("li");
        li.className = entry.level === 3 ? "toc-h3" : "toc-h2";
        var a = document.createElement("a");
        a.href = "#" + entry.id;
        a.textContent = entry.text;
        li.appendChild(a);
        list.appendChild(li);
    });

    container.innerHTML = "";
    var title = document.createElement("div");
    title.className = "toc-title";
    title.textContent = "On this page";
    container.appendChild(title);
    container.appendChild(list);
}

/* ---------- Scroll spy ---------- */

var activeSpy = null;

function startScrollSpy() {
    if (activeSpy) {
        activeSpy.disconnect();
        activeSpy = null;
    }
    if (!("IntersectionObserver" in window)) {
        return;
    }
    var targets = document.querySelectorAll("#doc-view h2[id], #doc-view h3[id]");
    if (!targets.length) {
        return;
    }

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) {
                return;
            }
            var id = entry.target.id;
            document.querySelectorAll(".sidebar a.active, .doc-toc a.active")
                .forEach(function (link) {
                    link.classList.remove("active");
                });
            document.querySelectorAll('.sidebar a[href="#' + id + '"], ' +
                    '.doc-toc a[href="#' + id + '"]')
                .forEach(function (link) {
                    link.classList.add("active");
                });
        });
    }, { rootMargin: "-12% 0px -72% 0px" });

    targets.forEach(function (target) {
        observer.observe(target);
    });
    activeSpy = observer;
}

/* ---------- Syntax highlighting for X ---------- */

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

var X_KEYWORDS = [
    "abstract", "as", "async", "await", "break", "case", "catch", "class",
    "const", "continue", "default", "do", "else", "enum", "export",
    "extends", "finally", "for", "function", "if", "import", "in",
    "interface", "let", "match", "namespace", "new", "of", "private",
    "protected", "public", "return", "static", "super", "switch", "this",
    "throw", "try", "virtual", "while", "with", "override", "final",
    "implements", "null", "true", "false"
];

var X_PRIMITIVES = [
    "integer", "float", "string", "boolean", "var", "any", "void", "int"
];

var KEYWORD_SET = {};
X_KEYWORDS.forEach(function (word) {
    KEYWORD_SET[word] = true;
});

var PRIMITIVE_SET = {};
X_PRIMITIVES.forEach(function (word) {
    PRIMITIVE_SET[word] = true;
});

var WORD_RE = /^[A-Za-z_][A-Za-z0-9_]*/;

function highlightX(source) {
    var patterns = [
        { cls: "tok-com", re: /^\/\/[^\n]*/ },
        { cls: "tok-com", re: /^\/\*[\s\S]*?\*\// },
        { cls: "tok-str", re: /^`(?:\\.|[^`\\])*`/ },
        { cls: "tok-str", re: /^"(?:\\.|[^"\\\n])*"/ },
        { cls: "tok-str", re: /^'(?:\\.|[^'\\\n])*'/ },
        { cls: "tok-dec", re: /^@[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*/ },
        { cls: "tok-num", re: /^\b\d+(?:\.\d+)?\b/ },
        { cls: "tok-kw", re: WORD_RE, set: KEYWORD_SET },
        { cls: "tok-fn", re: /^[A-Za-z_][A-Za-z0-9_]*(?=\s*\()/ },
        { cls: "tok-type", re: WORD_RE, set: PRIMITIVE_SET },
        { cls: "tok-type", re: /^[A-Z][A-Za-z0-9_]*(?:\.[A-Z][A-Za-z0-9_]*)*/ }
    ];

    var out = "";
    var i = 0;

    while (i < source.length) {
        var rest = source.slice(i);
        var matched = null;

        for (var p = 0; p < patterns.length; p++) {
            var pattern = patterns[p];
            var match = rest.match(pattern.re);
            if (!match) {
                continue;
            }
            if (pattern.set && !pattern.set[match[0]]) {
                continue;
            }
            matched = { text: match[0], cls: pattern.cls };
            break;
        }

        if (matched) {
            out += '<span class="' + matched.cls + '">' + escapeHtml(matched.text) + "</span>";
            i += matched.text.length;
        } else {
            out += escapeHtml(source[i]);
            i += 1;
        }
    }
    return out;
}

function initHighlighting() {
    document.querySelectorAll("code.language-x").forEach(function (block) {
        if (block.getAttribute("data-highlighted") === "1") {
            return;
        }
        block.innerHTML = highlightX(block.textContent);
        block.setAttribute("data-highlighted", "1");
    });
}

/* ---------- Copy buttons ---------- */

function initCopyButtons() {
    if (!navigator.clipboard) {
        return;
    }
    document.querySelectorAll(".code-block").forEach(function (block) {
        var head = block.querySelector(".code-head");
        var code = block.querySelector("pre code");
        if (!head || !code || head.querySelector(".copy-btn")) {
            return;
        }

        var button = document.createElement("button");
        button.type = "button";
        button.className = "copy-btn";
        button.textContent = "Copy";
        button.addEventListener("click", function () {
            navigator.clipboard.writeText(code.textContent).then(function () {
                button.textContent = "Copied";
                setTimeout(function () {
                    button.textContent = "Copy";
                }, 1200);
            });
        });
        head.appendChild(button);
    });
}

/* ---------- Render once README.md arrives ---------- */

function refresh() {
    initHighlighting();
    initCopyButtons();
    buildToc();
    startScrollSpy();
}

/* ---------- Boot ---------- */

document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initMobileMenu();

    var source = window.XMarkdown.pageUrl().replace(/^\.\//, "");
    setStatus("Loading " + source + "\u2026");
    window.XMarkdown.load()
        .then(function () {
            setStatus("Source: " + source);
            if (source !== "README.md") {
                var h1 = document.querySelector("#doc-view h1");
                if (h1) {
                    document.title = h1.textContent + " \u2014 X language documentation";
                }
                var nav = document.getElementById("doc-nav");
                var home = document.createElement("div");
                home.className = "nav-group nav-home";
                var parent = document.createElement("div");
                parent.className = "nav-parent";
                var link = document.createElement("a");
                link.href = "./";
                link.textContent = "\u2190 Main documentation";
                parent.appendChild(link);
                home.appendChild(parent);
                nav.insertBefore(home, nav.firstChild);
            }
            refresh();
            if (window.location.hash) {
                var target = document.getElementById(window.location.hash.slice(1));
                if (target) {
                    target.scrollIntoView({ block: "start" });
                }
            }
        })
        .catch(function () {
            setStatus("Could not load " + source);
            showFetchError();
        });
});
