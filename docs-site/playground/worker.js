/* ES-module Web Worker: load Pyodide (CPython → WebAssembly), install the X
   wheel, run playground programs off the main thread.

   Pyodide ≥ recent releases reject classic workers (importScripts). This
   file must be loaded with `new Worker(..., { type: "module" })`. */

var LOCAL_INDEX = "pyodide/";
var CDN_INDEXES = [
  "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
  "https://cdn.jsdelivr.net/pyodide/v0.29.5/full/"
];

var ready = null;
var bridge = null;

function baseDir() {
  return self.location.href.replace(/[^/]*$/, "");
}

function post(id, payload) {
  self.postMessage(Object.assign({ id: id }, payload));
}

async function probeIndex(indexUrl) {
  var response = await fetch(indexUrl + "pyodide.mjs", { method: "GET" });
  if (!response.ok) {
    throw new Error("HTTP " + response.status + " for " + indexUrl + "pyodide.mjs");
  }
  return indexUrl;
}

async function resolveIndexUrl() {
  var localUrl = baseDir() + LOCAL_INDEX;
  try {
    return await probeIndex(localUrl);
  } catch (localError) {
    var lastError = localError;
    for (var i = 0; i < CDN_INDEXES.length; i++) {
      try {
        return await probeIndex(CDN_INDEXES[i]);
      } catch (cdnError) {
        lastError = cdnError;
      }
    }
    throw new Error(
      "Could not load Pyodide from " + localUrl + " or the CDN. " +
      "(" + (lastError && lastError.message ? lastError.message : lastError) + ") " +
      "The vendored runtime lives in docs-site/playground/pyodide/ — " +
      "re-run .venv/bin/python docs-site/playground/build.py and reload over HTTP."
    );
  }
}

async function importLoadPyodide(indexUrl) {
  var mod = await import(/* @vite-ignore */ indexUrl + "pyodide.mjs");
  return mod.loadPyodide;
}

async function loadInterpreterWheel(pyodide) {
  var manifestUrl = baseDir() + "wheels/manifest.json";
  // The wheel filename is stable across rebuilds, so a cached manifest
  // would keep pointing at a stale `?v=` fingerprint after a redeploy.
  // Always fetch the manifest fresh; the wheel URL stays busted by the
  // fingerprint itself.
  var manifestResponse = await fetch(manifestUrl, { cache: "no-store" });
  if (!manifestResponse.ok) {
    throw new Error(
      "Could not fetch " + manifestUrl + " (" + manifestResponse.status + "). " +
      "Run .venv/bin/python docs-site/playground/build.py and reload."
    );
  }
  var manifest = await manifestResponse.json();
  if (!manifest.wheel) {
    throw new Error("wheels/manifest.json is missing a wheel entry.");
  }

  var micropip = pyodide.pyimport("micropip");
  var cacheKey = manifest.sourceFingerprint || manifest.builtAt || String(Date.now());
  var wheelUrl = baseDir() + "wheels/" + manifest.wheel + "?v=" + encodeURIComponent(cacheKey);

  try {
    await micropip.install(wheelUrl);
  } catch (localInstallError) {
    try {
      await micropip.install(wheelUrl, { deps: false });
    } catch (retryError) {
      throw new Error(
        "Could not install the X interpreter wheel (" + wheelUrl + "): " +
        (retryError && retryError.message ? retryError.message : retryError)
      );
    }
  }
  return manifest;
}

function boot() {
  if (ready) {
    return ready;
  }
  ready = (async function () {
    var indexUrl = await resolveIndexUrl();
    var loadPyodide = await importLoadPyodide(indexUrl);
    var pyodide = await loadPyodide({ indexURL: indexUrl });
    await pyodide.loadPackage("micropip");
    await loadInterpreterWheel(pyodide);

    bridge = pyodide.runPython(
      "import json\n" +
      "from xlang.playground import run_files, run_source, format_file\n" +
      "def _run(payload):\n" +
      "    data = json.loads(payload)\n" +
      "    files = data.get('files') or []\n" +
      "    if files:\n" +
      "        return json.dumps(run_files(files, entry=data.get('entry')))\n" +
      "    return json.dumps(run_source(data.get('source') or ''))\n" +
      "def _format(payload):\n" +
      "    data = json.loads(payload)\n" +
      "    return json.dumps(format_file(data.get('source') or '', data.get('name') or 'main.x'))\n" +
      "{ 'run': _run, 'format': _format }\n"
    );
    return pyodide;
  })();
  ready.catch(function () {
    ready = null;
  });
  return ready;
}

self.addEventListener("message", async function (event) {
  var data = event.data || {};

  if (data.type === "boot") {
    boot()
      .then(function () {
        post("boot", { type: "ready" });
      })
      .catch(function (error) {
        post("boot", {
          type: "error",
          message: (error && error.message) ? error.message : String(error)
        });
      });
    return;
  }

  if (data.type !== "run" && data.type !== "format") {
    return;
  }

  var id = data.id;
  try {
    await boot();
    post(id, { type: "progress", stage: data.type });

    var payload = JSON.stringify({
      source: data.source,
      files: data.files,
      entry: data.entry,
      name: data.name
    });

    var json;
    if (data.type === "format") {
      json = bridge.get("format")(payload);
    } else {
      json = bridge.get("run")(payload);
    }
    post(id, { type: "result", result: JSON.parse(json) });
  } catch (error) {
    post(id, {
      type: "error",
      message: (error && error.message) ? error.message : String(error),
      stack: (error && error.stack) ? String(error.stack) : ""
    });
  }
});
