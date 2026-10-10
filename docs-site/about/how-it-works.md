# How this site is built

This page documents the site you are reading: how a plain `README.md` in the
repository becomes a rendered static webpage, what the shell does, and what
rules the content follows.

## The files

Everything lives in `docs-site/` and uses no frameworks, no build step, and
no dependencies.

| File | Role |
| --- | --- |
| `index.html` | The fixed shell: top bar, sidebar, content area, table of contents, script tags. Never changes when content changes. |
| `README.md` | The content source. This is a copy of the repository README, extended for the website. Editing this file is all a documentation writer does. |
| `markdown.js` | Fetches the markdown, parses it to HTML, builds the sidebar navigation. |
| `script.js` | Everything the page does after render: theme, mobile menu, table of contents, scroll spy, syntax highlighting, copy buttons. |
| `styles.css` | All styling, light and dark themes, responsive layout. |
| `about/` | Extra pages like this one, each a plain markdown file. |

## From README.md to the page

There is no compilation. A browser loads `index.html`, the two scripts run,
and the page assembles itself:

1. `script.js` boots on `DOMContentLoaded`: theme from `localStorage`,
   mobile-menu wiring.
2. `markdown.js` fetches `README.md` (cache disabled, so edits show up on
   reload). Over `file://` this fetch fails and the shell shows the
   "Could not load README.md" box — the site must be served over HTTP.
3. The block parser turns markdown into HTML: headings get slugged ids
   (`Switch statements` → `#switch-statements`), fenced code becomes labelled
   `.code-block` cards, `output` fences become `.output` boxes, plus tables,
   lists, quotes, horizontal rules, and paragraphs with inline formatting.
4. Raw `<svg>` and `<figure>` blocks pass through untouched, which is how the
   architecture diagrams inside the README render as vector graphics.
5. HTML comments are consumed silently — that is how the
   `<!-- verify: skip -->` markers next to some examples stay invisible.
6. The parsed HTML is injected into `#doc-view`.
7. The sidebar is built from the page's `h2` headings (groups) and `h3`
   headings (children). The right-hand "On this page" list comes from the
   same headings.
8. `script.js` refreshes: syntax highlighting wraps `x` code in token spans,
   copy buttons attach to every code card, an `IntersectionObserver` drives
   the scroll spy that highlights the current section in both menus.

## Markdown conventions the parser understands

- ```` ```x file.x ```` — an X example. The label after the language becomes
  the card title.
- ```` ```output ```` — the verified stdout of the example right above it.
  Rendered as a distinct "Output" box.
- ```` ```sh ```` — a shell command.
- Ordinary fenced blocks (`text`, `markdown`, ...) render as labelled code
  cards.
- Tables, nested lists, blockquotes, `---` rules, and `**bold**` / `*em*` /
  `` `code` `` / `[links](...)` inline.
- Links to `?page=about/...` switch to another page; links starting with
  `../` or `./` resolve one directory up from `docs-site/`, which is how
  repository paths like `../examples/hello.x` work.

## Verified examples

Every `x` code block in the main README is followed by an `output` block
containing what the interpreter actually printed — each pair was executed
with `x run` and the captured stdout was pasted underneath, so the output
can never drift from the code. Blocks that cannot run standalone (multi-file
import demos, declaration-only snippets) carry a `<!-- verify: skip -->`
marker on the line before the fence; the marker hides the comment from
readers but tells the checker to leave the block alone.

To check an example yourself, copy it to a file and run:

```sh
x run example.x
```

## Running the site locally

From the repository root:

```sh
python3 -m http.server
```

Then open `http://localhost:8000/docs-site/`. Any static file server works;
nothing has to be built first.

## Editing rules

- Content changes = edit `docs-site/README.md` (or a file in
  `docs-site/about/`). Reload the page and the site follows.
- `index.html`, `markdown.js`, `script.js`, and `styles.css` are the shell.
  They only change when the behaviour of the site itself changes.
- Keep examples honest: run them, paste the real output underneath.

## Extra pages and the ?page= parameter

The shell renders one markdown file at a time. The main page always uses
`README.md`. Any other page inside `docs-site/` is selected with a query
parameter:

| URL | Renders |
| --- | --- |
| `/docs-site/` | `docs-site/README.md` |
| `/docs-site/?page=about/how-it-works.md` | `docs-site/about/how-it-works.md` |
| `/docs-site/?page=about/project-ideas.md` | `docs-site/about/project-ideas.md` |

Only names matching `about/<file>.md` style paths are accepted (no `..`, no
outside files). On an extra page the sidebar lists that page's own headings,
the top bar title becomes the page's `h1`, and the first sidebar entry links
back to the main documentation.

## Project ideas

The goals and future ideas for this documentation project are on their own
page: [Project ideas](?page=about/project-ideas.md).
