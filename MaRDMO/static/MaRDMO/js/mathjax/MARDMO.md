# MathJax in MaRDMO

MathJax 3.0.0 (`package.json`), trimmed to what MaRDMO loads (from 23 MB to 9 MB):

| Kept | Loaded by |
|---|---|
| `es5/tex-mml-chtml.js` | the preview (`MaRDMO/preview.html`) and the formulas in the interview (`MaRDMO/js/math-preview.js`) |
| `es5/tex-svg.js` | the result page of the export (`MaRDMO/export_result.html`) |
| `es5/input/tex/extensions/` | both, on demand: TeX extensions are loaded when a formula uses them (`\cancel`, `\ce`, `\boldsymbol`, ...) |
| `es5/output/chtml/fonts/woff-v2/` | `tex-mml-chtml.js`: the fonts of its HTML output (`tex-svg.js` has its own) |
| `es5/a11y/`, `es5/sre/` | both, when a user turns on the explorer or speech in MathJax's context menu (screen readers) |

Removed: the other combined components (`tex-chtml*`, `tex-svg-full`, `tex-mml-svg`, `mml-*`), the
single components (`core`, `loader`, `startup`, `input/*.js`, `output/*.js`, `ui`, `adaptors`),
`node-main.js`, `latest.js` and the SVG fonts as files.  What a page requests was recorded in a
browser (both components, a formula with extensions, the explorer turned on); nothing removed was
requested.  When MathJax is updated, keep the same parts of the new version and check it the same way.
