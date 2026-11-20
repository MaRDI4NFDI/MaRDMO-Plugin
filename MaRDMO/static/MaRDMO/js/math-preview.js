/* MaRDMO: the LaTeX of the formula and symbol questions, rendered below their fields in RDMO's interview.

The questionnaire marks these questions by an empty <span class="mardmo-math"> in their help text
(RDMO shows a question's help as HTML).  For each value of a marked question, the TeX typed is
rendered by MaRDMO's MathJax below its field, while typing; what MathJax cannot render is shown with
its message, as a hint only: the MaRDI Portal's TeX check decides (the checks and the preview).
MathJax is loaded only on a page with a marked question.  The interview is drawn by React, which
redraws its fields; a MutationObserver puts the rendering back where it is gone.
*/
(function () {
  'use strict'

  var script = document.currentScript
  var MARKER = '.mardmo-math'
  var PREVIEW = 'mardmo-math-preview'
  var WAIT = 300 // ms after the last key before rendering
  var mathjax = null

  function text(name, fallback) {
    return (script && script.dataset['text' + name]) || fallback
  }

  // MathJax, loaded once on demand; the safe configuration (_mathjax_safe_config.html) is merged
  function loadMathJax() {
    if (!mathjax) {
      mathjax = new Promise(function (resolve, reject) {
        window.MathJax = window.MathJax || {}
        window.MathJax.startup = Object.assign(window.MathJax.startup || {}, {
          typeset: false,
          ready: function () {
            window.MathJax.startup.defaultReady()
            window.MathJax.startup.promise.then(resolve, reject)
          }
        })
        var tag = document.createElement('script')
        tag.src = script.dataset.mathjax
        tag.async = true
        tag.onerror = reject
        document.head.appendChild(tag)
      })
    }
    return mathjax
  }

  function addStyle() {
    if (document.getElementById(PREVIEW + '-style')) return
    var style = document.createElement('style')
    style.id = PREVIEW + '-style'
    // RDMO lays out a field and its buttons in a row: the rendering goes into a line of its own
    style.textContent =
      '.interview-input:has(> .' + PREVIEW + ') { flex-wrap: wrap; }' +
      '.' + PREVIEW + ' { flex: 0 0 100%; max-width: 100%; margin-top: 4px; overflow-x: auto; overflow-y: hidden; }' +
      '.' + PREVIEW + ' mjx-container[display="true"] { margin: 0.25em 0 !important; text-align: left !important; }' +
      '.' + PREVIEW + '-hint { color: #8a6d3b; font-size: 90%; }'
    document.head.appendChild(style)
  }

  // The inputs of the marked questions (one per value)
  function inputs() {
    var found = []
    document.querySelectorAll('.interview-question').forEach(function (question) {
      if (!question.querySelector(MARKER)) return
      question.querySelectorAll('.interview-input input[type="text"], .interview-input textarea').forEach(function (input) {
        found.push(input)
      })
    })
    return found
  }

  function previewOf(input) {
    var container = input.closest('.interview-input')
    if (!container) return null
    var preview = container.querySelector(':scope > .' + PREVIEW)
    if (!preview) {
      preview = document.createElement('div')
      preview.className = PREVIEW
      preview.setAttribute('aria-live', 'polite')
      container.appendChild(preview)
    }
    return preview
  }

  function render(input) {
    var preview = previewOf(input)
    if (!preview) return
    var tex = input.value.trim()
    if (preview.dataset.tex === tex) return
    preview.dataset.tex = tex
    if (!tex) {
      preview.replaceChildren()
      return
    }
    loadMathJax().then(function () {
      return window.MathJax.tex2chtmlPromise(tex, { display: true })
    }).then(function (node) {
      if (preview.dataset.tex !== tex) return // typed on meanwhile
      var error = node.querySelector('mjx-merror')
      if (error) {
        var hint = document.createElement('span')
        hint.className = PREVIEW + '-hint'
        hint.textContent = text('Error', 'MathJax cannot show this formula:') + ' ' +
          (error.getAttribute('data-mjx-error') || error.textContent)
        preview.replaceChildren(hint)
        return
      }
      preview.replaceChildren(node)
      window.MathJax.startup.document.clear()
      window.MathJax.startup.document.updateDocument()
    }).catch(function () {
      preview.replaceChildren() // MathJax not available: no preview
    })
  }

  var timers = new WeakMap()

  function later(input) {
    clearTimeout(timers.get(input))
    timers.set(input, setTimeout(function () { render(input) }, WAIT))
  }

  function scan() {
    var found = inputs()
    if (found.length) addStyle()
    found.forEach(render)
  }

  document.addEventListener('input', function (event) {
    var input = event.target
    if (input.closest && input.closest('.interview-question') &&
        input.closest('.interview-question').querySelector(MARKER)) {
      later(input)
    }
  })

  // The interview draws its pages after loading and on every tab, page or value change
  var pending = false
  new MutationObserver(function () {
    if (pending) return
    pending = true
    window.requestAnimationFrame(function () {
      pending = false
      scan()
    })
  }).observe(document.body, { childList: true, subtree: true })
  scan()
})()
