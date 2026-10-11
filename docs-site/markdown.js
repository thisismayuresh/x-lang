/* Markdown renderer for the X documentation site.
   No dependencies. Reads docs-site/README.md (the file you edit) and turns
   it into the page: content, sidebar, and heading ids. Change README.md,
   reload, the site follows. Extra pages in docs-site/about/*.md are loaded
   with ?page=about/name.md. */

"use strict";

(function () {
    var REFERENCE_URL = "./README.md";
    var cachedText = null;
    var cachedResult = null;
    var cachedUrl = null;

    /* ---------- helpers ---------- */

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function slugify(text, seen) {
        var base = text.toLowerCase().trim()
            .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
            .replace(/[*_`~]/g, "")
            .replace(/[^\w\- ]+/g, "")
            .replace(/ +/g, "-");
        if (base === "") {
            base = "section";
        }
        if (seen) {
            if (seen[base] === undefined) {
                seen[base] = 0;
            } else {
                seen[base] += 1;
                base = base + "-" + seen[base];
            }
        }
        return base;
    }

    function resolveHref(url) {
        if (/^(https?:|mailto:|#|\?)/i.test(url)) {
            return url;
        }
        if (url.charAt(0) === "/") {
            return ".." + url;
        }
        // Sibling pages inside docs-site/ (playground.html, …) stay put;
        // repository-relative paths still climb out of the site folder.
        if (/^[^./][^:]*\.html?$/i.test(url)) {
            return url;
        }
        return "../" + url.replace(/^\.\//, "");
    }

    function parseInline(text) {
        var codeSpans = [];
        var out = escapeHtml(text);

        out = out.replace(/`([^`]+)`/g, function (_, code) {
            codeSpans.push(code);
            return "\u0000" + (codeSpans.length - 1) + "\u0000";
        });
        out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, function (_, alt, url) {
            return '<img src="' + resolveHref(url) + '" alt="' + alt + '">';
        });
        out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, label, url) {
            return '<a href="' + resolveHref(url) + '">' + label + "</a>";
        });
        out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        out = out.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");

        out = out.replace(/\u0000(\d+)\u0000/g, function (_, index) {
            return "<code>" + codeSpans[Number(index)] + "</code>";
        });
        return out;
    }

    /* ---------- block-level parser ---------- */

    function parse(markdown) {
        var idPrefix = "";
        var headings = [];
        var seen = {};
        var lines = markdown.split(/\r?\n/);
        var html = [];
        var i = 0;

        function heading(level, rawText) {
            var text = rawText.replace(/\s+#+\s*$/, "").trim();
            var id = idPrefix + slugify(text, seen);
            headings.push({ level: level, text: text, id: id });
            return "<h" + level + ' id="' + id + '">' + parseInline(text) +
                "</h" + level + ">";
        }

        function isFence(line) {
            return /^\s*```(?![`])/.test(line);
        }

        /* info string: "x", "output", "x filename.x", "bash", ... */
        function fenceInfo(line) {
            var match = line.match(/^\s*```(.*)$/);
            var info = match ? match[1].trim() : "";
            var parts = info.split(/\s+/);
            return {
                language: parts[0] || "",
                title: parts.length > 1 ? parts.slice(1).join(" ") : ""
            };
        }

        function renderFence(info, body) {
            if (info.language === "output") {
                return '<div class="output">' +
                    '<span class="output-label">Output</span>' +
                    "<pre>" + escapeHtml(body) + "</pre></div>";
            }
            var label = info.title || info.language || "code";
            var cls = info.language ? "language-" + info.language : "";
            return '<div class="code-block">' +
                '<div class="code-head"><span>' + escapeHtml(label) + "</span></div>" +
                '<pre><code class="' + cls + '">' + escapeHtml(body) + "</code></pre>" +
                "</div>";
        }

        function isTableRow(line) {
            return /\|/.test(line) && !/^\s*$/.test(line);
        }

        function isTableSep(line) {
            return /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && /-/.test(line);
        }

        function splitRow(line) {
            return line.trim().replace(/^\|/, "").replace(/\|$/, "")
                .split("|").map(function (cell) { return cell.trim(); });
        }

        function renderTable(headerLine, bodyLines) {
            var htmlParts = ["<table><thead><tr>"];
            splitRow(headerLine).forEach(function (cell) {
                htmlParts.push("<th>" + parseInline(cell) + "</th>");
            });
            htmlParts.push("</tr></thead><tbody>");
            bodyLines.forEach(function (line) {
                htmlParts.push("<tr>");
                splitRow(line).forEach(function (cell) {
                    htmlParts.push("<td>" + parseInline(cell) + "</td>");
                });
                htmlParts.push("</tr>");
            });
            htmlParts.push("</tbody></table>");
            return htmlParts.join("");
        }

        function listMarker(line) {
            var match = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
            if (!match) {
                return null;
            }
            return {
                indent: match[1].replace(/\t/g, "  ").length,
                ordered: /\d/.test(match[2]),
                text: match[3]
            };
        }

        function frameHtml(frame) {
            var tag = frame.ordered ? "ol" : "ul";
            var items = frame.items.map(function (text) {
                return "<li>" + parseInline(text) + "</li>";
            });
            return "<" + tag + ">" + items.join("") + "</" + tag + ">";
        }

        function emitFrame(frame) {
            var frag = frameHtml(frame);
            if (frame.parent) {
                frame.parent.items[frame.parent.items.length - 1] += frag;
            } else {
                html.push(frag);
            }
        }

        while (i < lines.length) {
            var line = lines[i];

            /* HTML comments (e.g. verify-skip markers) are consumed silently */
            if (/^\s*<!--/.test(line)) {
                if (!/-->/.test(line)) {
                    while (i < lines.length && !/-->\s*$/.test(lines[i])) {
                        i += 1;
                    }
                }
                i += 1;
                continue;
            }

            /* raw SVG / figure wrappers (architecture diagrams) pass through */
            if (/^\s*<(svg|figure)[\s>]/.test(line)) {
                var raw = [];
                var close = /^\s*<figure/.test(line) ? /<\/figure>/ : /<\/svg>/;
                while (i < lines.length) {
                    raw.push(lines[i]);
                    if (close.test(lines[i])) {
                        i += 1;
                        break;
                    }
                    i += 1;
                }
                html.push(raw.join("\n"));
                continue;
            }

            if (isFence(line)) {
                var info = fenceInfo(line);
                i += 1;
                var body = [];
                while (i < lines.length && !/^\s*```/.test(lines[i])) {
                    body.push(lines[i]);
                    i += 1;
                }
                i += 1;
                html.push(renderFence(info, body.join("\n")));
                continue;
            }

            var headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
            if (headingMatch) {
                html.push(heading(headingMatch[1].length, headingMatch[2]));
                i += 1;
                continue;
            }

            if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
                html.push("<hr>");
                i += 1;
                continue;
            }

            if (/^\s*>/.test(line)) {
                var quote = [];
                while (i < lines.length && /^\s*>/.test(lines[i])) {
                    quote.push(lines[i].replace(/^\s*>\s?/, ""));
                    i += 1;
                }
                html.push("<blockquote><p>" + parseInline(quote.join(" ")) +
                    "</p></blockquote>");
                continue;
            }

            if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
                var header = line;
                i += 2;
                var bodyRows = [];
                while (i < lines.length && isTableRow(lines[i]) &&
                        !/^\s*$/.test(lines[i])) {
                    bodyRows.push(lines[i]);
                    i += 1;
                }
                html.push(renderTable(header, bodyRows));
                continue;
            }

            if (listMarker(line)) {
                var stack = [];
                while (i < lines.length) {
                    var marker = listMarker(lines[i]);
                    if (marker) {
                        while (stack.length &&
                                stack[stack.length - 1].indent > marker.indent) {
                            emitFrame(stack.pop());
                        }
                        var top = stack[stack.length - 1];
                        if (!top || top.indent < marker.indent) {
                            stack.push({
                                indent: marker.indent,
                                ordered: marker.ordered,
                                items: [],
                                parent: stack[stack.length - 1] || null
                            });
                        } else if (top.ordered === marker.ordered) {
                            top.items.push(marker.text);
                        } else {
                            emitFrame(stack.pop());
                            stack.push({
                                indent: marker.indent,
                                ordered: marker.ordered,
                                items: [],
                                parent: stack[stack.length - 1] || null
                            });
                            stack[stack.length - 1].items.push(marker.text);
                        }
                        if (stack[stack.length - 1].items.length === 0) {
                            stack[stack.length - 1].items.push(marker.text);
                        }
                        i += 1;
                        continue;
                    }
                    if (stack.length && /^\s+\S/.test(lines[i])) {
                        var frame = stack[stack.length - 1];
                        frame.items[frame.items.length - 1] += " " + lines[i].trim();
                        i += 1;
                        continue;
                    }
                    break;
                }
                while (stack.length) {
                    emitFrame(stack.pop());
                }
                continue;
            }

            if (/^\s*$/.test(line)) {
                i += 1;
                continue;
            }

            var para = [];
            while (i < lines.length && !/^\s*$/.test(lines[i]) &&
                    !isFence(lines[i]) && !/^(#{1,6})\s/.test(lines[i]) &&
                    !listMarker(lines[i]) && !/^\s*>/.test(lines[i]) &&
                    !/^\s*(-{3,}|\*{3,})\s*$/.test(lines[i]) &&
                    !/^\s*<svg[\s>]/.test(lines[i])) {
                para.push(lines[i].trim());
                i += 1;
            }
            html.push("<p>" + parseInline(para.join(" ")) + "</p>");
        }

        return { html: html.join("\n"), headings: headings };
    }

    /* ---------- sidebar from headings ---------- */

    function buildNav(headings) {
        var container = document.getElementById("doc-nav");
        if (!container) {
            return;
        }
        container.innerHTML = "";
        var currentGroup = null;

        headings.forEach(function (entry) {
            if (entry.level < 2 || entry.level > 3) {
                return;
            }
            if (entry.level === 2) {
                var wrap = document.createElement("div");
                wrap.className = "nav-group";
                var parent = document.createElement("div");
                parent.className = "nav-parent";
                var link = document.createElement("a");
                link.href = "#" + entry.id;
                link.textContent = entry.text;
                parent.appendChild(link);
                wrap.appendChild(parent);
                currentGroup = document.createElement("ul");
                currentGroup.className = "nav-children";
                wrap.appendChild(currentGroup);
                container.appendChild(wrap);
            } else if (currentGroup) {
                var li = document.createElement("li");
                var sub = document.createElement("a");
                sub.href = "#" + entry.id;
                sub.textContent = entry.text;
                li.appendChild(sub);
                currentGroup.appendChild(li);
            }
        });

        /* drop groups that ended up with no children */
        Array.prototype.forEach.call(container.querySelectorAll(".nav-group"), function (g) {
            var kids = g.querySelector(".nav-children");
            if (!kids || !kids.children.length) {
                kids.parentNode.removeChild(kids);
            }
        });
    }

    /* ---------- public API ---------- */

    /* Which source file this page renders: README.md by default,
       or about/<name>.md when opened as ?page=about/<name>.md. */
    function pageUrl() {
        var match = /[?&]page=([A-Za-z0-9_][A-Za-z0-9_./-]*\.md)/.exec(window.location.search);
        if (!match || match[1].indexOf("..") !== -1) {
            return REFERENCE_URL;
        }
        return "./" + match[1];
    }

    function load() {
        var url = pageUrl();
        if (cachedResult && cachedUrl === url) {
            return Promise.resolve(cachedResult);
        }
        return fetch(url, { cache: "no-store" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.text();
            })
            .then(function (text) {
                cachedText = text;
                var container = document.getElementById("doc-view");
                var result = parse(text);
                container.innerHTML = result.html;
                buildNav(result.headings);
                cachedResult = result;
                cachedUrl = url;
                return result;
            });
    }

    window.XMarkdown = {
        parse: parse,
        parseInline: parseInline,
        slugify: slugify,
        escapeHtml: escapeHtml,
        load: load,
        pageUrl: pageUrl,
        referenceUrl: REFERENCE_URL
    };
})();
