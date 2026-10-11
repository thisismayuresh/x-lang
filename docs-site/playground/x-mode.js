/* CodeMirror mode for the X programming language.
   Includes depth-based paired-bracket colourisation (VS Code style). */

/* global CodeMirror */

"use strict";

(function () {
  var keywords = (
    "abstract as async await break case catch class const continue default " +
    "do else enum export extends finally for function if import in interface " +
    "let match namespace new of private protected public return static super " +
    "switch this throw try virtual while with override final implements null " +
    "true false"
  ).split(" ");

  var types = (
    "integer float string boolean var any void int"
  ).split(" ");

  var keywordSet = {};
  keywords.forEach(function (word) { keywordSet[word] = true; });
  var typeSet = {};
  types.forEach(function (word) { typeSet[word] = true; });

  var BRACKET_LEVELS = 6;

  CodeMirror.defineMode("x", function () {
    return {
      startState: function () {
        return {
          inString: null,
          inComment: false,
          inTemplate: false,
          bracketDepth: 0
        };
      },
      token: function (stream, state) {
        if (state.inComment) {
          return eatComment(stream, state);
        }
        if (state.inString) {
          return eatString(stream, state, state.inString);
        }

        if (stream.eatSpace()) {
          return null;
        }

        if (stream.match("//")) {
          stream.skipToEnd();
          return "comment";
        }
        if (stream.match("/*")) {
          state.inComment = true;
          return eatComment(stream, state);
        }
        if (stream.match("`")) {
          state.inTemplate = true;
          state.inString = "`";
          return "string";
        }
        if (stream.match('"')) {
          state.inString = '"';
          return "string";
        }
        if (stream.match("'")) {
          state.inString = "'";
          return "string";
        }
        if (stream.match("@")) {
          stream.eatWhile(/[\w.]/);
          return "def";
        }
        if (/[\d]/.test(stream.peek())) {
          stream.eatWhile(/[\d.]/);
          if (stream.peek() === "e" || stream.peek() === "E") {
            stream.next();
            stream.eatWhile(/[-+]/);
            stream.eatWhile(/\d/);
          }
          return "number";
        }
        if (stream.match(/^(?:===|!==|==|!=|<=|>=|&&|\|\||\?\?|=>|\.\.\.|\?\.)/)) {
          return "operator";
        }
        if (stream.match(/^[=+\-*/%<>!&|^~?:]/)) {
          return "operator";
        }

        /* Paired brackets — colour by nesting depth so matching pairs share a colour. */
        if (stream.match(/^[({[]/)) {
          state.bracketDepth += 1;
          return "bracket-" + ((state.bracketDepth - 1) % BRACKET_LEVELS);
        }
        if (stream.match(/^[)}\]]/)) {
          if (state.bracketDepth > 0) {
            state.bracketDepth -= 1;
          }
          return "bracket-" + (state.bracketDepth % BRACKET_LEVELS);
        }

        if (stream.match(/^[;,.]/)) {
          return "punctuation";
        }

        var word = stream.match(/^[A-Za-z_][A-Za-z0-9_]*/);
        if (word) {
          var text = word[0];
          if (keywordSet[text]) {
            return "keyword";
          }
          if (typeSet[text]) {
            return "type";
          }
          if (/^[A-Z]/.test(text)) {
            return "type";
          }
          if (stream.peek() === "(") {
            return "def";
          }
          return "variable";
        }
        stream.next();
        return null;
      }
    };

    function eatComment(stream, state) {
      while (!stream.eol()) {
        if (stream.match("*\/")) {
          state.inComment = false;
          return "comment";
        }
        stream.next();
      }
      return "comment";
    }

    function eatString(stream, state, quote) {
      while (!stream.eol()) {
        if (stream.peek() === "\\") {
          stream.next();
          stream.next();
          continue;
        }
        if (stream.next() === quote) {
          state.inString = null;
          if (quote === "`") {
            state.inTemplate = false;
          }
          return "string";
        }
      }
      return "string";
    }
  });

  CodeMirror.defineMIME("text/x-x", "x");
})();
