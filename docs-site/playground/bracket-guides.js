/* Bracket-pair guide lines for the X playground (CodeMirror 5).
   Draws a vertical line from each opening bracket down to its match,
   colourised by nesting depth to match the token colours in x-mode.js. */

/* global CodeMirror */

"use strict";

(function () {
  var LAYER_CLASS = "bracket-guide-layer";
  var LINE_CLASS = "bracket-guide-line";
  var MAX_DEPTH_COLORS = 6;
  var UPDATE_DEBOUNCE_MS = 40;

  function depthFromType(type) {
    var match = /^bracket-(\d+)/.exec(type || "");
    return match ? Number(match[1]) % MAX_DEPTH_COLORS : 0;
  }

  function findPairs(cm) {
    var stack = [];
    var pairs = [];

    cm.eachLine(function (line) {
      var lineNo = line.lineNo();
      var tokens;
      try {
        tokens = cm.getLineTokens(lineNo);
      } catch (error) {
        return;
      }
      tokens.forEach(function (token) {
        if (!token.type || token.type.indexOf("bracket-") !== 0) {
          return;
        }
        var ch = token.string;
        var pos = { line: lineNo, ch: token.start };
        if (ch === "(" || ch === "{" || ch === "[") {
          stack.push({ ch: ch, pos: pos, depth: stack.length });
          return;
        }
        if (ch !== ")" && ch !== "}" && ch !== "]") {
          return;
        }
        var open = stack.pop();
        if (!open) {
          return;
        }
        var ok =
          (open.ch === "(" && ch === ")") ||
          (open.ch === "{" && ch === "}") ||
          (open.ch === "[" && ch === "]");
        if (!ok) {
          return;
        }
        pairs.push({
          open: open.pos,
          close: { line: lineNo, ch: token.end },
          depth: open.depth % MAX_DEPTH_COLORS
        });
      });
    });

    return pairs;
  }

  function ensureLayer(cm) {
    var wrapper = cm.getWrapperElement();
    var layer = wrapper.querySelector("." + LAYER_CLASS);
    if (!layer) {
      layer = document.createElement("div");
      layer.className = LAYER_CLASS;
      layer.setAttribute("aria-hidden", "true");
      wrapper.appendChild(layer);
    }
    return layer;
  }

  function clearLayer(layer) {
    while (layer.firstChild) {
      layer.removeChild(layer.firstChild);
    }
  }

  /* Half-line offset so the guide starts below the open bracket and
     stops above the close bracket (full height on lines in between). */
  function guideSegment(cm, pair) {
    var openCoords = cm.charCoords(pair.open, "local");
    var closeCoords = cm.charCoords(
      { line: pair.close.line, ch: Math.max(0, pair.close.ch - 1) },
      "local"
    );
    var textHeight = cm.defaultTextHeight();
    var x = openCoords.left;
    var top = openCoords.bottom;
    var bottom = closeCoords.top;
    if (bottom - top < 1) {
      /* Same-line or adjacent: still draw a short tick under the open. */
      bottom = top + Math.max(2, textHeight * 0.4);
    }
    return {
      x: x,
      top: top,
      height: Math.max(2, bottom - top),
      depth: pair.depth
    };
  }

  function draw(cm) {
    var layer = ensureLayer(cm);
    clearLayer(layer);

    if (!cm.getOption("bracketGuides")) {
      return;
    }

    var pairs = findPairs(cm);
    var frag = document.createDocumentFragment();

    pairs.forEach(function (pair) {
      if (pair.close.line === pair.open.line) {
        return;
      }
      var seg = guideSegment(cm, pair);
      var div = document.createElement("div");
      div.className = LINE_CLASS + " bracket-guide-depth-" + seg.depth;
      div.style.left = Math.round(seg.x) + "px";
      div.style.top = Math.round(seg.top) + "px";
      div.style.height = Math.round(seg.height) + "px";
      frag.appendChild(div);
    });

    layer.appendChild(frag);
  }

  function scheduleDraw(cm) {
    if (cm._xBracketGuideTimer) {
      clearTimeout(cm._xBracketGuideTimer);
    }
    cm._xBracketGuideTimer = setTimeout(function () {
      cm._xBracketGuideTimer = null;
      draw(cm);
    }, UPDATE_DEBOUNCE_MS);
  }

  CodeMirror.defineOption("bracketGuides", false, function (cm, val) {
    if (val) {
      cm.on("change", scheduleDraw);
      cm.on("refresh", scheduleDraw);
      cm.on("scroll", scheduleDraw);
      cm.on("optionChange", function (_cm, name) {
        if (name === "theme" || name === "bracketGuides") {
          scheduleDraw(cm);
        }
      });
      scheduleDraw(cm);
    } else {
      cm.off("change", scheduleDraw);
      cm.off("refresh", scheduleDraw);
      cm.off("scroll", scheduleDraw);
      var layer = cm.getWrapperElement().querySelector("." + LAYER_CLASS);
      if (layer && layer.parentNode) {
        layer.parentNode.removeChild(layer);
      }
    }
  });

  CodeMirror.prototype.redrawBracketGuides = function () {
    draw(this);
  };
})();
