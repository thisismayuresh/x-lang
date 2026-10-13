/* X playground UI: multi-file editor, formatter, Pyodide worker host, splitter. */

/* global CodeMirror, X_PLAYGROUND_EXAMPLES */

"use strict";

(function () {
  var RUN_TIMEOUT_MS = 15000;
  var MAX_FILES = 5;
  var DEFAULT_ENTRY = "main.x";

  var editor = null;
  var worker = null;
  var workerReady = false;
  var pendingRunId = 0;
  var activeRunId = 0;
  var runTimer = null;
  var bootMessageId = "boot";
  var project = { files: [{ name: DEFAULT_ENTRY, content: "" }], active: 0 };
  var suppressChange = false;

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  /* Fatal / infrastructure errors (worker crash, WASM boot failure, …).
     User program errors stay in the output pane; this bar is only for
     "the playground itself is broken". */
  function setFatal(message) {
    if (!els.fatal) {
      return;
    }
    els.fatal.textContent = message || "";
    if (message) {
      els.fatal.hidden = false;
      try {
        console.error("[playground]", message);
      } catch (ignore) { /* no console */ }
    } else {
      els.fatal.hidden = true;
    }
  }

  function clearFatal() {
    setFatal("");
  }

  function setThemeOnEditor(theme) {
    if (!editor) {
      return;
    }
    editor.setOption("theme", theme === "dark" ? "material" : "default");
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark"
      ? "dark"
      : "light";
  }

  function initThemeToggle() {
    var toggle = $("theme-toggle");
    if (!toggle) {
      return;
    }
    function label() {
      var dark = currentTheme() === "dark";
      toggle.textContent = dark ? "Light mode" : "Dark mode";
      setThemeOnEditor(dark ? "dark" : "light");
    }
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {
        localStorage.setItem("x-docs-theme", next);
      } catch (error) { /* private mode */ }
      label();
    });
    label();
  }

  /* ---------- project / multi-file state ---------- */

  function activeFile() {
    return project.files[project.active] || project.files[0];
  }

  function syncActiveFromEditor() {
    if (!editor || !project.files[project.active]) {
      return;
    }
    project.files[project.active].content = editor.getValue();
  }

  function safeFileName(raw) {
    var base = String(raw || "").split(/[\\/]/).pop().trim();
    base = base.replace(/[^A-Za-z0-9._-]/g, "_");
    if (!base || base === "." || base === "..") {
      base = "file.x";
    }
    if (!/\.x$/i.test(base)) {
      base += ".x";
    }
    return base.slice(0, 64);
  }

  function uniqueName(preferred) {
    var name = safeFileName(preferred);
    var taken = {};
    project.files.forEach(function (f) { taken[f.name] = true; });
    if (!taken[name]) {
      return name;
    }
    var stem = name.replace(/\.x$/i, "");
    var n = 2;
    while (taken[stem + "-" + n + ".x"]) {
      n += 1;
    }
    return stem + "-" + n + ".x";
  }

  function renderFileBar() {
    var bar = els.fileBar;
    if (!bar) {
      return;
    }
    bar.textContent = "";

    var folder = document.createElement("span");
    folder.className = "file-bar-folder";
    folder.textContent = "playground/";
    bar.appendChild(folder);

    project.files.forEach(function (file, index) {
      var tab = document.createElement("button");
      tab.type = "button";
      tab.className = "file-tab" + (index === project.active ? " active" : "");
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", index === project.active ? "true" : "false");
      tab.title = file.name + (index === 0 ? " (entry)" : "");
      tab.textContent = file.name;

      tab.addEventListener("click", function () {
        switchFile(index);
      });

      if (project.files.length > 1 && index !== 0) {
        var close = document.createElement("span");
        close.className = "file-close";
        close.textContent = "×";
        close.title = "Close " + file.name;
        close.addEventListener("click", function (event) {
          event.stopPropagation();
          closeFile(index);
        });
        tab.appendChild(close);
      }

      bar.appendChild(tab);
    });

    var add = document.createElement("button");
    add.type = "button";
    add.className = "file-add";
    add.textContent = "+ File";
    add.title = project.files.length >= MAX_FILES
      ? "Maximum " + MAX_FILES + " files"
      : "Add a file (max " + MAX_FILES + ")";
    add.disabled = project.files.length >= MAX_FILES;
    add.addEventListener("click", function () { addFile(); });
    bar.appendChild(add);

    if (els.activeFileName) {
      els.activeFileName.textContent = activeFile().name;
    }
  }

  function switchFile(index) {
    if (index === project.active || !project.files[index]) {
      return;
    }
    syncActiveFromEditor();
    project.active = index;
    suppressChange = true;
    editor.setValue(project.files[index].content || "");
    editor.clearGutter("errors");
    suppressChange = false;
    renderFileBar();
    editor.focus();
  }

  function addFile() {
    if (project.files.length >= MAX_FILES) {
      return;
    }
    syncActiveFromEditor();
    var name = uniqueName("util.x");
    project.files.push({ name: name, content: "// " + name + "\nexport string function hello() {\n    return \"hi\";\n}\n" });
    project.active = project.files.length - 1;
    suppressChange = true;
    editor.setValue(activeFile().content);
    suppressChange = false;
    renderFileBar();
    editor.focus();
  }

  function closeFile(index) {
    if (index === 0 || project.files.length <= 1 || !project.files[index]) {
      return;
    }
    project.files.splice(index, 1);
    if (project.active >= project.files.length) {
      project.active = project.files.length - 1;
    } else if (project.active === index) {
      project.active = Math.max(0, index - 1);
    }
    suppressChange = true;
    editor.setValue(activeFile().content || "");
    editor.clearGutter("errors");
    suppressChange = false;
    renderFileBar();
  }

  function collectFilesForRun() {
    syncActiveFromEditor();
    return project.files.map(function (file) {
      return { name: file.name, content: file.content || "" };
    });
  }

  function entryFileName() {
    var main = project.files.filter(function (f) { return f.name === DEFAULT_ENTRY; })[0];
    return (main || project.files[0]).name;
  }

  /* ---------- examples ---------- */

  function populateExamples() {
    var select = els.examples;
    if (!select || !window.X_PLAYGROUND_EXAMPLES) {
      return;
    }
    window.X_PLAYGROUND_EXAMPLES.forEach(function (example, index) {
      var option = document.createElement("option");
      option.value = String(index);
      option.textContent = example.label;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      var example = window.X_PLAYGROUND_EXAMPLES[Number(select.value)];
      if (!example) {
        return;
      }
      loadExample(example);
    });
  }

  function loadExample(example) {
    var files = Array.isArray(example.files) && example.files.length
      ? example.files.slice(0, MAX_FILES).map(function (file, i) {
          return {
            name: safeFileName(file.name || (i === 0 ? DEFAULT_ENTRY : "file-" + (i + 1) + ".x")),
            content: file.content || ""
          };
        })
      : [{ name: DEFAULT_ENTRY, content: example.code }];
    project = { files: files, active: 0 };
    suppressChange = true;
    editor.setValue(activeFile().content);
    editor.clearGutter("errors");
    suppressChange = false;
    renderFileBar();
    editor.focus();
  }

  function loadInitialCode() {
    if (window.X_PLAYGROUND_EXAMPLES && window.X_PLAYGROUND_EXAMPLES[0]) {
      loadExample(window.X_PLAYGROUND_EXAMPLES[0]);
    }
  }

  /* ---------- status / output ---------- */

  function setStatus(text, tone) {
    els.status.textContent = text;
    els.status.setAttribute("data-tone", tone || "idle");
  }

  function clearLinters() {
    if (editor) {
      editor.clearGutter("errors");
    }
  }

  function markErrorLine(line) {
    if (!line || line < 1) {
      return;
    }
    var marker = document.createElement("div");
    marker.className = "error-marker";
    marker.title = "Error on this line";
    editor.setGutterMarker(line - 1, "errors", marker);
  }

  /* ---------- rustc-style diagnostics ----------
     Mirrors xlang/diagnostics.py::render_diagnostic so the browser shows
     the same block the CLI prints: header, --> location, code frame with
     a ^^^ caret, then = note: / = help: follow-ups. */

  function fileContentFor(name) {
    var files = project.files || [];
    for (var i = 0; i < files.length; i++) {
      if (files[i].name === name) {
        return files[i].content || "";
      }
    }
    return editor ? editor.getValue() : "";
  }

  function expandTabs(text) {
    var out = "";
    for (var i = 0; i < text.length; i++) {
      if (text[i] === "\t") {
        var width = 4 - (out.length % 4);
        out += " ".repeat(width);
      } else {
        out += text[i];
      }
    }
    return out;
  }

  function hintLines(notes, helps, gutter) {
    var lines = [];
    var prefix = gutter ? gutter + " " : "";
    var continuation = gutter ? gutter + "   " : "  ";
    [["note", notes], ["help", helps]].forEach(function (pair) {
      (pair[1] || []).forEach(function (item) {
        String(item).split("\n").forEach(function (text, index) {
          if (index === 0) {
            lines.push(text ? prefix + "= " + pair[0] + ": " + text
                            : prefix + "= " + pair[0] + ":");
          } else {
            lines.push(text ? continuation + text : continuation.replace(/ +$/, ""));
          }
        });
      });
    });
    return lines;
  }

  function renderDiagnostic(error) {
    var name = error.file || activeFile().name;
    var sourceText = fileContentFor(error.file);
    var sourceLines = sourceText ? sourceText.split("\n") : [];
    var lines = ["error: " + error.message];
    var gutter = "";
    if (error.line != null) {
      gutter = " ".repeat(String(error.line).length);
      var location = name + ":" + error.line;
      if (error.column != null) {
        location += ":" + error.column;
      }
      lines.push(gutter + "--> " + location);
    } else {
      lines.push("--> " + name);
    }
    if (error.line != null && error.line >= 1 && error.line <= sourceLines.length) {
      var rawLine = sourceLines[error.line - 1];
      var column = Math.max(1, error.column || 1);
      var endColumn = (error.endLine === error.line && error.endColumn != null)
        ? Math.max(column + 1, error.endColumn)
        : column + 1;
      var caretStart = expandTabs(rawLine.slice(0, column - 1)).length;
      var caretLength = Math.max(
        1,
        expandTabs(rawLine.slice(column - 1, endColumn - 1)).length
      );
      lines.push(gutter + " |");
      lines.push(String(error.line) + " | " + expandTabs(rawLine));
      lines.push(
        gutter + " | " +
        " ".repeat(caretStart) + "^".repeat(caretLength) + " " + error.message
      );
    }
    return lines
      .concat(hintLines(error.notes, error.helps, gutter))
      .join("\n");
  }

  function renderOutput(result) {
    els.output.textContent = "";
    els.errors.textContent = "";

    if (result.output && result.output.length) {
      els.output.textContent = result.output.join("\n");
    } else if (result.ok) {
      els.output.textContent = "(no output)";
    }

    clearLinters();
    if (result.errors && result.errors.length) {
      var blocks = result.errors.map(function (error) {
        if (!error.file || error.file === activeFile().name) {
          markErrorLine(error.line);
        }
        return renderDiagnostic(error);
      });
      els.errors.textContent = blocks.join("\n\n");
    }

    var ms = typeof result.durationMs === "number" ? result.durationMs : null;
    if (result.ok) {
      setStatus(ms != null ? "Finished in " + ms + " ms" : "Finished", "ok");
    } else {
      setStatus(ms != null ? "Failed in " + ms + " ms" : "Failed", "error");
    }
  }

  /* ---------- worker ---------- */

  function spawnWorker() {
    if (worker) {
      worker.terminate();
    }
    workerReady = false;
    worker = new Worker(
      "playground/worker.js?v=" + encodeURIComponent(window.X_PLAYGROUND_BUILD || String(Date.now())),
      { type: "module" }
    );
    worker.addEventListener("message", function (event) {
      var data = event.data || {};
      if (data.id === bootMessageId) {
        if (data.type === "ready") {
          workerReady = true;
          clearFatal();
          setStatus("Ready — press Run (Ctrl+Enter)", "idle");
          els.run.disabled = false;
        } else if (data.type === "error") {
          setStatus("Runtime failed to load", "error");
          setFatal(
            "Could not start the WebAssembly runtime:\n" + data.message +
            "\n\nServe the repo over HTTP from the project root:\n" +
            "  python3 -m http.server 8080\n" +
            "then open http://localhost:8080/docs-site/playground.html\n\n" +
            "If playground/pyodide/ is missing, rebuild with:\n" +
            "  .venv/bin/python docs-site/playground/build.py"
          );
        }
        return;
      }
      if (data.id !== activeRunId) {
        return;
      }
      if (data.type === "progress") {
        setStatus(workerReady ? "Running…" : "Loading WebAssembly runtime…", "busy");
        return;
      }
      if (runTimer) {
        clearTimeout(runTimer);
        runTimer = null;
      }
      els.run.disabled = false;
      if (data.type === "result") {
        if (els.format && els.format.getAttribute("data-busy") === "1") {
          handleFormatResult(data.result);
        } else {
          renderOutput(data.result);
        }
      } else if (data.type === "error") {
        setStatus("Runner error", "error");
        els.errors.textContent = data.message || String(data);
      }
    });
    worker.addEventListener("error", function (event) {
      setStatus("Worker error", "error");
      setFatal(event.message || "The playground worker crashed.");
      els.run.disabled = false;
    });
    worker.postMessage({ type: "boot" });
  }

  function nextMessageId() {
    pendingRunId += 1;
    return pendingRunId;
  }

  function run() {
    if (!worker) {
      spawnWorker();
    }
    if (runTimer) {
      clearTimeout(runTimer);
      runTimer = null;
    }

    activeRunId = nextMessageId();
    els.run.disabled = true;
    if (els.format) {
      els.format.removeAttribute("data-busy");
    }
    setStatus(workerReady ? "Running…" : "Loading WebAssembly runtime…", "busy");

    worker.postMessage({
      type: "run",
      id: activeRunId,
      files: collectFilesForRun(),
      entry: entryFileName()
    });

    runTimer = setTimeout(function () {
      if (activeRunId !== pendingRunId) {
        return;
      }
      setStatus("Stopped after " + RUN_TIMEOUT_MS / 1000 + "s (possible infinite loop)", "error");
      els.errors.textContent =
        "Execution timed out. The program was terminated so the page stays responsive.";
      els.output.textContent = "";
      spawnWorker();
      els.run.disabled = false;
    }, RUN_TIMEOUT_MS);
  }

  function handleFormatResult(result) {
    if (els.format) {
      els.format.removeAttribute("data-busy");
    }
    if (!result || result.ok === false) {
      setStatus("Format failed", "error");
      els.errors.textContent = (result && result.error) || "Could not format this file.";
      return;
    }
    var formatted = result.source;
    if (typeof formatted === "string") {
      suppressChange = true;
      var cursor = editor.getCursor();
      editor.setValue(formatted);
      editor.setCursor(cursor);
      syncActiveFromEditor();
      suppressChange = false;
      setStatus("Formatted " + activeFile().name, "ok");
      els.errors.textContent = "";
    }
  }

  function formatActive() {
    if (!worker || !workerReady) {
      setStatus("Runtime still loading…", "busy");
      return;
    }
    syncActiveFromEditor();
    activeRunId = nextMessageId();
    if (els.format) {
      els.format.setAttribute("data-busy", "1");
    }
    setStatus("Formatting " + activeFile().name + "…", "busy");
    worker.postMessage({
      type: "format",
      id: activeRunId,
      source: activeFile().content || "",
      name: activeFile().name
    });
  }

  /* ---------- splitter ---------- */

  function initSplitter() {
    var splitter = $("splitter");
    var main = $("playground-main");
    if (!splitter || !main) {
      return;
    }

    var dragging = false;

    function applyFromClientX(clientX) {
      var rect = main.getBoundingClientRect();
      var min = 200;
      var max = rect.width - min - 8;
      var x = clientX - rect.left;
      x = Math.max(min, Math.min(max, x));
      var pct = (x / rect.width) * 100;
      main.style.gridTemplateColumns = pct + "% 8px 1fr";
      try {
        localStorage.setItem("x-playground-split", String(Math.round(pct * 10) / 10));
      } catch (error) { /* ignore */ }
      if (editor) {
        editor.refresh();
      }
    }

    splitter.addEventListener("mousedown", function (event) {
      dragging = true;
      event.preventDefault();
      document.body.classList.add("splitter-dragging");
    });

    window.addEventListener("mousemove", function (event) {
      if (!dragging) {
        return;
      }
      applyFromClientX(event.clientX);
    });

    window.addEventListener("mouseup", function () {
      if (!dragging) {
        return;
      }
      dragging = false;
      document.body.classList.remove("splitter-dragging");
      if (editor) {
        editor.refresh();
      }
    });

    try {
      var saved = Number(localStorage.getItem("x-playground-split"));
      if (saved >= 15 && saved <= 85) {
        main.style.gridTemplateColumns = saved + "% 8px 1fr";
      }
    } catch (error) { /* ignore */ }
  }

  /* ---------- autocomplete (unchanged catalogue logic) ---------- */

  function catalog() {
    return window.X_COMPLETIONS || { types: [], keywords: [], builtins: [], classes: [], snippets: [], members: {} };
  }

  function prefixFilter(items, word) {
    if (!word) {
      return items.slice();
    }
    var lowered = word.toLowerCase();
    var starts = [];
    var contains = [];
    items.forEach(function (item) {
      var name = item.displayText || item.text;
      var lowerName = name.toLowerCase();
      if (lowerName === lowered) {
        return;
      }
      if (lowerName.indexOf(lowered) === 0) {
        starts.push(item);
      } else if (lowerName.indexOf(lowered) !== -1) {
        contains.push(item);
      }
    });
    return starts.concat(contains);
  }

  function dottedChain(cm, pos) {
    var line = cm.getLine(pos.line).slice(0, pos.ch);
    var chain = [];
    var re = /([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*$/;
    var cursor = line;
    while (true) {
      var match = cursor.match(re);
      if (!match) {
        break;
      }
      chain.unshift(match[1]);
      cursor = cursor.slice(0, match.index);
    }
    return chain;
  }

  function lineBefore(cm, pos) {
    return cm.getLine(pos.line).slice(0, pos.ch);
  }

  function inTypePosition(before) {
    return /(^|[^\w.])(let|const|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*[A-Za-z_]*$/.test(before) ||
      /(^|[^\w.])(integer|int|float|string|boolean|any|void|var)\s+[A-Za-z_][A-Za-z0-9_]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=(,;]*\s*$/.test(before) ||
      /function\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*:\s*[A-Za-z_]*$/.test(before) ||
      /(^|[^\w.])(class|interface|extends|implements)\s+[A-Za-z_]*$/.test(before);
  }

  /* Best-effort type of a local from its declaration / initializer. */
  function inferVarType(cm, name) {
    if (!name) {
      return null;
    }
    var members = catalog().members;
    var content = cm.getValue();
    var declared = new RegExp(
      "(?:let|const|var)\\s+" + name + "\\s*:\\s*([A-Za-z_][A-Za-z0-9_]*)"
    ).exec(content);
    if (declared && declared[1] && members[declared[1]]) {
      return declared[1];
    }
    var typed = new RegExp(
      "\\b(integer|int|float|string|boolean|any|void)\\s+" + name + "\\b"
    ).exec(content);
    if (typed) {
      return typed[1] === "int" ? "integer" : typed[1];
    }
    var init = new RegExp(
      "(?:let|const|var)\\s+" + name + "\\s*=\\s*([^;\\n]+)"
    ).exec(content);
    if (init) {
      var rhs = init[1].trim();
      if (/^["'`]/.test(rhs)) {
        return "string";
      }
      if (/^-?\d+(\.\d+)?\b/.test(rhs)) {
        return "number";
      }
      if (/^(true|false)\b/.test(rhs)) {
        return "boolean";
      }
      if (/^\[/.test(rhs)) {
        return "Array";
      }
      if (/^\{/.test(rhs)) {
        return "object";
      }
      var newCall = /^new\s+([A-Za-z_][A-Za-z0-9_]*)/.exec(rhs);
      if (newCall) {
        return newCall[1];
      }
      if (/^[A-Za-z_][A-Za-z0-9_]*\s*\(/.test(rhs)) {
        return "function";
      }
      if (/^null\b/.test(rhs) || /^undefined\b/.test(rhs)) {
        return null;
      }
      var callName = /^([A-Za-z_][A-Za-z0-9_]*)$/.exec(rhs);
      if (callName) {
        var nested = inferVarType(cm, callName[1]);
        if (nested) {
          return nested;
        }
        if (members[callName[1]]) {
          return callName[1];
        }
      }
    }
    return null;
  }

  function memberItemsFor(chain, word) {
    var members = catalog().members;
    var items = [];
    var seen = {};

    function addAll(list) {
      (list || []).forEach(function (item) {
        if (!item || !item.text || seen[item.text]) {
          return;
        }
        seen[item.text] = true;
        items.push(item);
      });
    }

    if (!chain.length) {
      addAll(members["*"]);
      return items;
    }

    var head = chain[0];
    var second = chain[1];

    if (head === "System") {
      if (!second) {
        addAll(members.System);
        return items;
      }
      if (second === "utils" && chain.length === 2) {
        addAll(members.utils);
        return items;
      }
      if (second === "utils" && chain[2]) {
        addAll(members[chain[2]]);
        addAll(members["*"]);
        return items;
      }
      if (second === "io" && chain.length === 2) {
        addAll(members.io);
        return items;
      }
      if (second === "io" && chain[2]) {
        addAll(members[chain[2]]);
        addAll(members["*"]);
        return items;
      }
      addAll(members[second]);
      addAll(members["*"]);
      return items;
    }

    if (!second && editor) {
      var inferred = inferVarType(editor, head);
      if (inferred === "string") {
        addAll(members.string);
      } else if (inferred === "Array") {
        addAll(members.List);
        addAll(members["*"]);
        return items;
      } else if (inferred === "number") {
        addAll(members.Math);
        addAll(members["*"]);
        return items;
      } else if (inferred && members[inferred]) {
        addAll(members[inferred]);
      }
    }

    addAll(members[head]);
    addAll(members["*"]);
    return items;
  }

  function hintItemToCompletion(item) {
    return {
      text: item.text,
      displayText: item.displayText || item.text,
      className: "cm-hint-" + (item.type || "plain"),
      render: function (elt, data, completion) {
        elt.appendChild(document.createTextNode(completion.displayText || completion.text));
        if (item.detail) {
          var detail = document.createElement("span");
          detail.className = "cm-hint-detail";
          detail.textContent = item.detail;
          elt.appendChild(detail);
        }
      },
      hint: function (cm, data, completion) {
        var from = data.from;
        var to = data.to || cm.getCursor();
        var text = completion.text;
        if (item.snippet) {
          cm.replaceRange("", from, to);
          cm.replaceSelection(item.snippet);
          var body = cm.getValue();
          var m = body.slice(cm.indexFromPos(from)).match(/\$1/);
          if (m) {
            var abs = cm.indexFromPos(from) + m.index;
            var pos = cm.posFromIndex(abs);
            cm.replaceRange("", pos, CodeMirror.Pos(pos.line, pos.ch + 2));
            cm.setCursor(pos);
          }
          return;
        }
        cm.replaceRange(text, from, to, "complete");
      }
    };
  }

  function isCatalogKeyword(name) {
    var keywords = catalog().keywords || [];
    for (var i = 0; i < keywords.length; i += 1) {
      if (keywords[i].text === name) {
        return true;
      }
    }
    return false;
  }

  /* Names declared in the current buffer (variables, parameters, functions,
     types, classes, imports) so they complete alongside the static catalogue. */
  function collectDeclarations(cm) {
    var variables = [];
    var types = [];
    var seenVar = {};
    var seenType = {};
    if (!cm) {
      return { variables: variables, types: types };
    }
    var content = cm.getValue()
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/\/\/[^\n]*/g, " ");

    function addVar(name, detail, kind) {
      if (!name || seenVar[name] || isCatalogKeyword(name)) {
        return;
      }
      seenVar[name] = true;
      variables.push({ text: name, type: kind || "variable", detail: detail });
    }

    function addType(name, kind) {
      if (!name || seenType[name] || isCatalogKeyword(name)) {
        return;
      }
      seenType[name] = true;
      types.push({ text: name, type: kind || "type", detail: kind || "type" });
    }

    var match;
    var typeRe = /\b(type|class|interface|enum|namespace)\s+([A-Za-z_][A-Za-z0-9_]*)/g;
    while ((match = typeRe.exec(content)) !== null) {
      addType(match[2], match[1]);
    }

    var fnRe = /\bfunction(?:\s*<[^<>]*>)?\s+([A-Za-z_][A-Za-z0-9_]*)/g;
    while ((match = fnRe.exec(content)) !== null) {
      addVar(match[1], "function", "method");
    }

    function splitParams(text) {
      var parts = [];
      var depth = 0;
      var current = "";
      for (var i = 0; i < text.length; i += 1) {
        var ch = text[i];
        if (ch === "<") {
          depth += 1;
        } else if (ch === ">") {
          depth = Math.max(0, depth - 1);
        } else if (ch === "," && depth === 0) {
          parts.push(current);
          current = "";
          continue;
        }
        current += ch;
      }
      parts.push(current);
      return parts;
    }

    var paramRe = /\bfunction(?:\s*<[^<>]*>)?\s+[A-Za-z_][A-Za-z0-9_]*\s*\(([^)]*)\)/g;
    while ((match = paramRe.exec(content)) !== null) {
      splitParams(match[1]).forEach(function (chunk) {
        var clean = chunk.replace(/<[^<>]*>/g, "");
        var colon = clean.indexOf(":");
        var name;
        if (colon !== -1) {
          var head = clean.slice(0, colon).match(/[A-Za-z_][A-Za-z0-9_]*\s*$/);
          name = head ? head[0].replace(/\s+$/, "") : null;
        } else {
          var ids = clean.match(/[A-Za-z_][A-Za-z0-9_]*/g);
          name = ids ? ids[ids.length - 1] : null;
        }
        addVar(name, "parameter", "parameter");
      });
    }

    var colonVarRe = /\b(?:let|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:/g;
    while ((match = colonVarRe.exec(content)) !== null) {
      addVar(match[1], "variable", "variable");
    }

    var typedVarRe =
      /\b(?:let|const|var)\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^<>]*>)?(?:\[\])*\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?=[=;,)\n])/g;
    while ((match = typedVarRe.exec(content)) !== null) {
      addVar(match[1], "variable", "variable");
    }

    var plainVarRe = /\b(?:let|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=/g;
    while ((match = plainVarRe.exec(content)) !== null) {
      addVar(match[1], "variable", "variable");
    }

    var forRe =
      /\bfor\s*\(\s*(?:let|const|var)\s+(?:[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^<>]*>)?(?:\[\])*\s+)?([A-Za-z_][A-Za-z0-9_]*)/g;
    while ((match = forRe.exec(content)) !== null) {
      addVar(match[1], "loop variable", "variable");
    }

    var catchRe =
      /\bcatch\s*\(\s*(?:[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^<>]*>)?(?:\[\])*\s+)?([A-Za-z_][A-Za-z0-9_]*)/g;
    while ((match = catchRe.exec(content)) !== null) {
      addVar(match[1], "exception", "variable");
    }

    var groupedImportRe = /import\s+[A-Za-z_][A-Za-z0-9_.]*\.\{([^}]*)\}/g;
    while ((match = groupedImportRe.exec(content)) !== null) {
      match[1].split(",").forEach(function (chunk) {
        var alias = chunk.match(/\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*$/);
        var ids = chunk.match(/[A-Za-z_][A-Za-z0-9_]*/g);
        var chosen = alias ? alias[1] : (ids ? ids[0] : null);
        addVar(chosen, "import", "namespace");
      });
    }

    var singleImportRe = /^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;?\s*$/gm;
    while ((match = singleImportRe.exec(content)) !== null) {
      var parts = match[1].split(".");
      addVar(parts[parts.length - 1], "import", "namespace");
    }

    return { variables: variables, types: types };
  }

  function dedupeItems(items) {
    var seen = {};
    var unique = [];
    items.forEach(function (item) {
      var name = item.displayText || item.text;
      if (seen[name]) {
        return;
      }
      seen[name] = true;
      unique.push(item);
    });
    return unique;
  }

  function allStandaloneItems(word, cm) {
    var c = catalog();
    var pool = []
      .concat(c.types || [])
      .concat(c.keywords || [])
      .concat(c.builtins || [])
      .concat(c.classes || [])
      .concat(c.snippets || []);
    pool = pool.concat(collectDeclarations(cm).variables);
    return prefixFilter(dedupeItems(pool), word);
  }

  function xHint(cm) {
    var cur = cm.getCursor();
    var token = cm.getTokenAt(cur);
    var before = lineBefore(cm, cur);
    var start = token.start;
    var end = cur.ch;

    if (token.type === "comment" || token.type === "string" ||
        token.type === "string-2" || before.slice(0, end).match(/\/\/.*$/) ||
        before.slice(0, end).match(/\/\*.*$/)) {
      return null;
    }

    var chain = dottedChain(cm, cur);
    var list;

    if (chain.length || token.string === ".") {
      list = memberItemsFor(chain, token.string === "." ? "" : token.string);
      if (token.string === ".") {
        start = end;
      }
    } else {
      var word = token.string.slice(0, end - token.start);
      if (!word || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(word)) {
        if (/[\s;{}(,]$/.test(before) || before === "") {
          word = "";
          start = end;
        } else {
          return null;
        }
      }
      if (inTypePosition(before)) {
        var typePool = (catalog().types || [])
          .concat(catalog().keywords || [])
          .concat(collectDeclarations(cm).types);
        var rest = prefixFilter(
          (catalog().builtins || []).concat(catalog().classes || []).concat(catalog().snippets || []),
          word
        );
        list = prefixFilter(dedupeItems(typePool), word).concat(rest);
      } else {
        list = allStandaloneItems(word, cm);
      }
    }

    if (!list.length) {
      return null;
    }

    return {
      list: list.map(hintItemToCompletion),
      from: CodeMirror.Pos(cur.line, start),
      to: CodeMirror.Pos(cur.line, end)
    };
  }

  function shouldAutoHint(cm, change) {
    if (change.origin !== "+input" || !change.text.length) {
      return false;
    }
    var typed = change.text[0];
    return typed === "." || typed === ":" || /[A-Za-z_]/.test(typed);
  }

  function initEditor() {
    var dark = currentTheme() === "dark";
    editor = CodeMirror.fromTextArea($("editor"), {
      mode: "x",
      lineNumbers: true,
      indentUnit: 4,
      indentWithTabs: false,
      matchBrackets: true,
      bracketGuides: false,
      autoCloseBrackets: {
        pairs: "()[]{}''\"\"``",
        closeBefore: ")]}:;>'\"`",
        triples: "",
        explode: "[]{}"
      },
      styleActiveLine: true,
      gutters: ["CodeMirror-linenumbers", "errors"],
      theme: dark ? "material" : "default",
      extraKeys: {
        "Ctrl-Enter": function () { run(); },
        "Cmd-Enter": function () { run(); },
        "Ctrl-S": function () { formatActive(); },
        "Cmd-S": function (cm) { formatActive(); return false; },
        "Ctrl-Space": function (cm) {
          cm.showHint({ hint: cm.getOption("hint"), completeSingle: false });
        },
        "Alt-Space": function (cm) {
          cm.showHint({ hint: cm.getOption("hint"), completeSingle: false });
        }
      },
      hintOptions: {
        completeSingle: false,
        completeOnSingleClick: false,
        pickOnTab: true
      }
    });

    editor.on("change", function () {
      if (!suppressChange) {
        syncActiveFromEditor();
      }
    });

    editor.on("inputRead", function (cm, change) {
      if (!shouldAutoHint(cm, change)) {
        return;
      }
      cm.showHint({ hint: cm.getOption("hint"), completeSingle: false });
    });

    editor.setOption("hint", xHint);
  }

  function init() {
    els = {
      run: $("run"),
      status: $("run-status"),
      output: $("output"),
      errors: $("errors"),
      examples: $("examples"),
      reset: $("reset"),
      format: $("format"),
      fileBar: $("file-bar"),
      activeFileName: $("active-file-name"),
      fatal: $("fatal-bar")
    };

    initThemeToggle();
    initEditor();
    initSplitter();
    populateExamples();
    loadInitialCode();
    renderFileBar();

    els.run.addEventListener("click", run);
    if (els.format) {
      els.format.addEventListener("click", formatActive);
    }
    els.reset.addEventListener("click", function () {
      if (window.X_PLAYGROUND_EXAMPLES && window.X_PLAYGROUND_EXAMPLES[0]) {
        loadExample(window.X_PLAYGROUND_EXAMPLES[0]);
        els.examples.selectedIndex = 0;
      }
    });

    setStatus("Loading WebAssembly runtime…", "busy");
    spawnWorker();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
