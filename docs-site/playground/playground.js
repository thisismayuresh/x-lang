/* X playground UI: multi-file editor (Monaco), formatter, Pyodide worker host. */

/* global require, monaco, X_PLAYGROUND_EXAMPLES */

"use strict";

(function () {
  var RUN_TIMEOUT_MS = 15000;
  var MAX_FILES = 5;
  var DEFAULT_ENTRY = "main.x";
  var MONACO_BASE = "playground/monaco/vs";

  var editor = null;
  var models = Object.create(null);
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

  function monacoThemeName() {
    return currentTheme() === "dark" ? "vs-dark" : "vs";
  }

  function setThemeOnEditor(theme) {
    if (window.monaco) {
      monaco.editor.setTheme(theme === "dark" ? "vs-dark" : "vs");
    }
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

  /* ---------- project / multi-file ---------- */

  function activeFile() {
    return project.files[project.active] || project.files[0];
  }

  function modelUriFor(name) {
    return monaco.Uri.parse("inmemory://playground/" + name);
  }

  function getModelFor(file) {
    if (!file) {
      return null;
    }
    var existing = models[file.name];
    if (existing && !existing.isDisposed()) {
      if (existing.getValue() !== (file.content || "")) {
        // model is source of truth when attached; content updated on sync
      }
      return existing;
    }
    var model = monaco.editor.createModel(
      file.content || "",
      "x",
      modelUriFor(file.name)
    );
    models[file.name] = model;
    return model;
  }

  function disposeModelsExcept(keepNames) {
    var keep = Object.create(null);
    keepNames.forEach(function (n) { keep[n] = true; });
    Object.keys(models).forEach(function (name) {
      if (!keep[name] && models[name] && !models[name].isDisposed()) {
        models[name].dispose();
      }
      if (!keep[name]) {
        delete models[name];
      }
    });
  }

  function syncActiveFromEditor() {
    if (!editor || !project.files[project.active]) {
      return;
    }
    var model = editor.getModel();
    if (model) {
      project.files[project.active].content = model.getValue();
    }
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

  function attachActiveModel() {
    if (!editor) {
      return;
    }
    var file = activeFile();
    var model = getModelFor(file);
    if (editor.getModel() !== model) {
      suppressChange = true;
      editor.setModel(model);
      suppressChange = false;
    }
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
    attachActiveModel();
    clearLinters();
    renderFileBar();
    if (editor) {
      editor.focus();
    }
  }

  function addFile() {
    if (project.files.length >= MAX_FILES) {
      return;
    }
    syncActiveFromEditor();
    var name = uniqueName("util.x");
    project.files.push({
      name: name,
      content: "// " + name + "\nexport string function hello() {\n    return \"hi\";\n}\n"
    });
    project.active = project.files.length - 1;
    attachActiveModel();
    renderFileBar();
    if (editor) {
      editor.focus();
    }
  }

  function closeFile(index) {
    if (index === 0 || project.files.length <= 1 || !project.files[index]) {
      return;
    }
    var removed = project.files.splice(index, 1)[0];
    if (removed && models[removed.name] && !models[removed.name].isDisposed()) {
      models[removed.name].dispose();
    }
    delete models[removed.name];
    if (project.active >= project.files.length) {
      project.active = project.files.length - 1;
    } else if (project.active === index) {
      project.active = Math.max(0, index - 1);
    }
    attachActiveModel();
    clearLinters();
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
    window.X_PLAYGROUND_EXAMPLES.forEach(function (example) {
      var option = document.createElement("option");
      option.value = example.id || String(select.options.length);
      option.textContent = example.label;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      var example = window.X_PLAYGROUND_EXAMPLES[Number(select.value)];
      if (!example) {
        example = window.X_PLAYGROUND_EXAMPLES.filter(function (e) {
          return e.id === select.value;
        })[0];
      }
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

    syncActiveFromEditor();
    files.forEach(function (file) {
      var model = models[file.name];
      if (model && !model.isDisposed()) {
        model.setValue(file.content || "");
      }
    });
    project = { files: files, active: 0 };
    disposeModelsExcept(files.map(function (f) { return f.name; }));
    files.forEach(function (file) {
      var model = models[file.name];
      if (model && !model.isDisposed()) {
        model.setValue(file.content || "");
      } else {
        models[file.name] = monaco.editor.createModel(
          file.content || "",
          "x",
          modelUriFor(file.name)
        );
      }
    });
    attachActiveModel();
    clearLinters();
    renderFileBar();
    if (editor) {
      editor.focus();
    }
  }

  function loadInitialCode() {
    if (window.X_PLAYGROUND_EXAMPLES && window.X_PLAYGROUND_EXAMPLES[0]) {
      loadExample(window.X_PLAYGROUND_EXAMPLES[0]);
    }
  }

  /* ---------- status / output / markers ---------- */

  function setStatus(text, tone) {
    els.status.textContent = text;
    els.status.setAttribute("data-tone", tone || "idle");
  }

  function clearLinters() {
    if (!editor) {
      return;
    }
    var model = editor.getModel();
    if (model) {
      monaco.editor.setModelMarkers(model, "x", []);
    }
  }

  function markErrorLine(line) {
    if (!line || line < 1 || !editor) {
      return;
    }
    var model = editor.getModel();
    if (!model || line > model.getLineCount()) {
      return;
    }
    var maxCol = model.getLineMaxColumn(line);
    monaco.editor.setModelMarkers(model, "x", [{
      startLineNumber: line,
      endLineNumber: line,
      startColumn: 1,
      endColumn: maxCol,
      message: "Error on this line",
      severity: monaco.MarkerSeverity.Error
    }]);
  }

  function fileContentFor(name) {
    var files = project.files || [];
    for (var i = 0; i < files.length; i++) {
      if (files[i].name === name) {
        return files[i].content || "";
      }
    }
    return editor && editor.getModel() ? editor.getModel().getValue() : "";
  }

  function expandTabs(text) {
    var out = "";
    for (var i = 0; i < text.length; i++) {
      if (text[i] === "\t") {
        out += " ".repeat(4 - (out.length % 4));
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
    if (typeof formatted === "string" && editor) {
      var model = editor.getModel();
      if (model) {
        suppressChange = true;
        var pos = editor.getPosition();
        model.setValue(formatted);
        if (pos) {
          editor.setPosition({
            lineNumber: Math.min(pos.lineNumber, model.getLineCount()),
            column: 1
          });
        }
        syncActiveFromEditor();
        suppressChange = false;
      }
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
    });

    try {
      var saved = Number(localStorage.getItem("x-playground-split"));
      if (saved >= 15 && saved <= 85) {
        main.style.gridTemplateColumns = saved + "% 8px 1fr";
      }
    } catch (error) { /* ignore */ }
  }

  /* ---------- completions ---------- */

  function catalog() {
    return window.X_COMPLETIONS || {
      types: [], keywords: [], builtins: [], classes: [], snippets: [], members: {}
    };
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

  function dottedChain(linePrefix) {
    var chain = [];
    var re = /([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*$/;
    var cursor = linePrefix;
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

  function inTypePosition(before) {
    return /(^|[^\w.])(let|const|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*[A-Za-z_]*$/.test(before) ||
      /(^|[^\w.])(integer|int|float|string|boolean|any|void|var)\s+[A-Za-z_][A-Za-z0-9_]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=(,;]*\s*$/.test(before) ||
      /function\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*:\s*[A-Za-z_]*$/.test(before) ||
      /(^|[^\w.])(class|interface|extends|implements)\s+[A-Za-z_]*$/.test(before);
  }

  function inferVarType(content, name) {
    if (!name) {
      return null;
    }
    var members = catalog().members;
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
    }
    return null;
  }

  function memberItemsFor(chain, content) {
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

    if (!second) {
      var inferred = inferVarType(content, head);
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

  function isCatalogKeyword(name) {
    var keywords = catalog().keywords || [];
    for (var i = 0; i < keywords.length; i += 1) {
      if (keywords[i].text === name) {
        return true;
      }
    }
    return false;
  }

  function collectDeclarations(content) {
    var variables = [];
    var types = [];
    var seenVar = {};
    var seenType = {};
    if (!content) {
      return { variables: variables, types: types };
    }
    content = content
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

    var colonVarRe = /\b(?:let|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:/g;
    while ((match = colonVarRe.exec(content)) !== null) {
      addVar(match[1], "variable", "variable");
    }

    var plainVarRe = /\b(?:let|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=/g;
    while ((match = plainVarRe.exec(content)) !== null) {
      addVar(match[1], "variable", "variable");
    }

    // Plain dotted imports register the last path segment; `as alias`
    // registers the alias instead; namespace wildcards (`util.Ns.*`) bind
    // no single name, so they add nothing.
    var importLineRe =
      /^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)(\.\*)?\s*(?:as\s+([A-Za-z_][A-Za-z0-9_]*))?\s*;?\s*$/gm;
    while ((match = importLineRe.exec(content)) !== null) {
      if (match[3]) {
        addVar(match[3], "import", "namespace");
      } else if (!match[2]) {
        var parts = match[1].split(".");
        addVar(parts[parts.length - 1], "import", "namespace");
      }
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

  function kindForType(type) {
    switch (type) {
      case "keyword": return monaco.languages.CompletionItemKind.Keyword;
      case "type": return monaco.languages.CompletionItemKind.TypeParameter;
      case "builtin":
      case "method": return monaco.languages.CompletionItemKind.Function;
      case "class": return monaco.languages.CompletionItemKind.Class;
      case "property": return monaco.languages.CompletionItemKind.Property;
      case "namespace": return monaco.languages.CompletionItemKind.Module;
      case "snippet": return monaco.languages.CompletionItemKind.Snippet;
      case "parameter": return monaco.languages.CompletionItemKind.Variable;
      default: return monaco.languages.CompletionItemKind.Value;
    }
  }

  function toCompletion(item, range) {
    var result = {
      label: item.displayText || item.text,
      kind: kindForType(item.type),
      insertText: item.snippet || item.text,
      range: range
    };
    if (item.detail) {
      result.detail = item.detail;
      result.documentation = { value: item.detail };
    }
    if (item.snippet) {
      result.insertTextRules = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
    }
    return result;
  }

  function buildCompletions(model, position) {
    var word = model.getWordUntilPosition(position);
    var range = new monaco.Range(
      position.lineNumber, word.startColumn,
      position.lineNumber, word.endColumn
    );
    var linePrefix = model.getValueInRange({
      startLineNumber: position.lineNumber,
      startColumn: 1,
      endLineNumber: position.lineNumber,
      endColumn: position.column
    });
    var content = model.getValue();
    var chain = dottedChain(linePrefix);
    var list;

    if (chain.length || /\.\s*[A-Za-z0-9_]*$/.test(linePrefix)) {
      list = memberItemsFor(chain, content);
      if (/\.$/.test(linePrefix.replace(/\s+$/, ""))) {
        range = new monaco.Range(
          position.lineNumber, position.column,
          position.lineNumber, position.column
        );
      }
    } else {
      var wordPrefix = word.word || "";
      if (inTypePosition(linePrefix)) {
        var typePool = (catalog().types || [])
          .concat(catalog().keywords || [])
          .concat(collectDeclarations(content).types);
        var rest = prefixFilter(
          (catalog().builtins || [])
            .concat(catalog().classes || [])
            .concat(catalog().snippets || [])
            .concat(collectDeclarations(content).variables),
          wordPrefix
        );
        list = prefixFilter(dedupeItems(typePool), wordPrefix).concat(rest);
      } else {
        var pool = []
          .concat(catalog().types || [])
          .concat(catalog().keywords || [])
          .concat(catalog().builtins || [])
          .concat(catalog().classes || [])
          .concat(catalog().snippets || [])
          .concat(collectDeclarations(content).variables);
        list = prefixFilter(dedupeItems(pool), wordPrefix);
      }
    }

    return list.map(function (item) { return toCompletion(item, range); });
  }

  /* ---------- Monaco language + editor ---------- */

  function registerXLanguage() {
    if (monaco.languages.getLanguages().some(function (l) { return l.id === "x"; })) {
      return;
    }

    monaco.languages.register({
      id: "x",
      extensions: [".x"],
      aliases: ["X", "x"]
    });

    monaco.languages.setLanguageConfiguration("x", {
      comments: { lineComment: "//", blockComment: ["/*", "*/"] },
      brackets: [["{", "}"], ["[", "]"], ["(", ")"]],
      autoClosingPairs: [
        { open: "{", close: "}" },
        { open: "[", close: "]" },
        { open: "(", close: ")" },
        { open: "'", close: "'", notIn: ["string", "comment"] },
        { open: "\"", close: "\"", notIn: ["string", "comment"] },
        { open: "`", close: "`", notIn: ["string", "comment"] }
      ],
      surroundingPairs: [
        { open: "{", close: "}" },
        { open: "[", close: "]" },
        { open: "(", close: ")" },
        { open: "'", close: "'" },
        { open: "\"", close: "\"" },
        { open: "`", close: "`" }
      ],
      indentationRules: {
        increaseIndentPattern: /\{$/,
        decreaseIndentPattern: /^\s*\}/
      }
    });

    monaco.languages.setMonarchTokensProvider("x", {
      keywords: [
        "abstract", "as", "async", "await", "break", "case", "catch", "class",
        "const", "continue", "default", "do", "else", "enum", "export",
        "extends", "finally", "for", "function", "if", "import", "in",
        "interface", "let", "match", "namespace", "new", "of", "private",
        "protected", "public", "return", "static", "super", "switch", "this",
        "throw", "try", "virtual", "while", "with", "override", "final",
        "implements", "null", "true", "false", "type"
      ],
      typeKeywords: ["integer", "float", "string", "boolean", "var", "any", "void", "int"],
      builtins: ["print", "println", "typeOf", "System"],
      operators: [
        "=", ">", "<", "!", "~", "?", ":",
        "==", "<=", ">=", "!=", "&&", "||", "++", "--",
        "+", "-", "*", "/", "%", "&", "|", "^", ".", "...",
        "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "=>"
      ],
      symbols: /[=><!~?:&|+\-*/^%]+/,
      escapes: /\\(?:[abfnrtv\\"'0]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})/,
      tokenizer: {
        root: [
          [/\/\/.*$/, "comment"],
          [/\/\*/, { token: "comment", next: "@blockComment" }],
          [/`/, { token: "string.quote", bracket: "@open", next: "@templateString" }],
          [/"/, { token: "string.quote", bracket: "@open", next: "@doubleString" }],
          [/'/, { token: "string.quote", bracket: "@open", next: "@singleString" }],
          [/@[\w.]+/, "annotation"],
          [/\d+\.\d+([eE][-+]?\d+)?/, "number.float"],
          [/0[xX][0-9a-fA-F]+/, "number.hex"],
          [/\d+/, "number"],
          [/[a-zA-Z_]\w*/, {
            cases: {
              "@typeKeywords": "type",
              "@keywords": "keyword",
              "@builtins": "constant",
              "@default": "identifier"
            }
          }],
          [/[{}()[\]]/, "delimiter.bracket"],
          [/@symbols/, { cases: { "@operators": "operator", "@default": "" } }],
          [/[;,.]/, "delimiter"],
          [/[ \t\r\n]+/, "white"]
        ],
        blockComment: [
          [/[^/*]+/, "comment"],
          [/\*\//, { token: "comment", next: "@pop" }],
          [/[/*]/, "comment"]
        ],
        doubleString: [
          [/[^\\"]+/, "string"],
          [/@escapes/, "string.escape"],
          [/\\./, "string.escape.invalid"],
          [/"/, { token: "string.quote", bracket: "@close", next: "@pop" }]
        ],
        singleString: [
          [/[^\\']+/, "string"],
          [/@escapes/, "string.escape"],
          [/\\./, "string.escape.invalid"],
          [/'/, { token: "string.quote", bracket: "@close", next: "@pop" }]
        ],
        templateString: [
          [/[^\\`$]+/, "string"],
          [/\\./, "string.escape"],
          [/`\{/, { token: "delimiter", next: "@templateExpr" }],
          [/`/, { token: "string.quote", bracket: "@close", next: "@pop" }]
        ],
        templateExpr: [
          [/`/, "delimiter"],
          [/[{}]/, "delimiter"],
          [/[^`{}]+/, "expression"],
          [/`/, { token: "string.quote", next: "@pop" }]
        ]
      }
    });

    monaco.languages.registerCompletionItemProvider("x", {
      // Only "." triggers the suggest widget. Space/":" were removed —
      // they made every keystroke open suggestions and stole the spacebar.
      triggerCharacters: ["."],
      provideCompletionItems: function (model, position) {
        return { suggestions: buildCompletions(model, position) };
      }
    });
  }

  function initEditor() {
    registerXLanguage();

    var host = $("editor");
    if (host) {
      host.textContent = "";
    }

    var mainFile = activeFile() || project.files[0];
    var initialModel = getModelFor(mainFile);

    editor = monaco.editor.create(host, {
      model: initialModel,
      theme: monacoThemeName(),
      automaticLayout: true,
      fontSize: 14,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      lineNumbers: "on",
      renderLineHighlight: "all",
      matchBrackets: "always",
      autoClosingBrackets: "always",
      autoClosingQuotes: "always",
      autoSurround: "languageDefined",
      tabSize: 4,
      insertSpaces: true,
      wordWrap: "off",
      smoothScrolling: true,
      padding: { top: 8, bottom: 8 },
      unicodeHighlight: { ambiguousCharacters: false },
      overviewRulerLanes: 0,
      scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 }
    });

    editor.onDidChangeModelContent(function () {
      if (!suppressChange) {
        syncActiveFromEditor();
      }
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, function () {
      run();
    });
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function () {
      formatActive();
    });
    // Ctrl+Space only — Alt+Space is the window menu on many Linux desktops.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Space, function () {
      editor.trigger("playground", "editor.action.triggerSuggest", {});
    });
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
    initSplitter();

    setStatus("Loading editor…", "busy");

    if (typeof require !== "function") {
      setFatal(
        "Could not load the Monaco editor runtime.\n" +
        "Expected playground/monaco/vs/loader.js to be served over HTTP."
      );
      setStatus("Editor failed to load", "error");
      return;
    }

    window.MonacoEnvironment = {
      getWorkerUrl: function () {
        return MONACO_BASE + "/base/worker/workerMain.js";
      }
    };

    require.config({ paths: { vs: MONACO_BASE } });
    require(["vs/editor/editor.main"], function () {
      try {
        initEditor();
        populateExamples();
        loadInitialCode();
        renderFileBar();
      } catch (error) {
        setFatal("Editor failed to start: " + (error && error.message ? error.message : error));
        setStatus("Editor failed to load", "error");
        return;
      }

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
    }, function (err) {
      setFatal(
        "Could not load Monaco from " + MONACO_BASE + ".\n" +
        "Serve the repo over HTTP from the project root:\n" +
        "  python3 -m http.server 8080"
      );
      setStatus("Editor failed to load", "error");
      try {
        console.error(err);
      } catch (ignore) { /* ignore */ }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
