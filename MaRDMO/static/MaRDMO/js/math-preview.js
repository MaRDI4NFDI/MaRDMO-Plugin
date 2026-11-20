/* MaRDMO: the LaTeX of the formula and symbol questions, rendered below their fields in RDMO's interview.

The questionnaire marks these questions by an empty <span class="mardmo-math"> in their help text
(RDMO shows a question's help as HTML).  For each value of a marked question, the TeX typed is
rendered by MaRDMO's MathJax below its field while typing (#190).  The field is only read.

After a pause in typing, MaRDMO's tex_check view gives the MaRDI Portal's verdict (the checks and the
export use the same, with the same cache):
- invalid: its message below the rendering;
- valid, but MathJax cannot render the formula as typed (shorthands of the portal's checker such
  as \R): the checker's form is rendered instead;
- no verdict (the portal is not reachable): nothing for the user (data-check="unverified").
Errors (the portal's, or MathJax's where the portal has none) appear only when the user stops
typing or leaves the field; meanwhile the last formula that could be rendered stays, dimmed, so a
half-typed \begin{align} does not flash an error.

MathJax is loaded only on a page with a marked question.  The interview is drawn by React, which
redraws its fields; a MutationObserver puts the rendering back where it is gone.
*/
(function () {
  'use strict'

  var script = document.currentScript
  var MARKER = '.mardmo-math'
  var PREVIEW = 'mardmo-math-preview'
  var RENDER_WAIT = 300 // ms after the last key: render
  var CHECK_WAIT = 1000 // ms after the last key: ask the portal
  var SETTLE_WAIT = 1800 // ms after the last key: show errors
  var mathjax = null
  var verdicts = new Map() // TeX -> the portal's verdict, for this page
  var states = new WeakMap() // rendering element -> its state
  var timers = new WeakMap() // input -> its timers

  function text(name, fallback) {
    return (script && script.dataset['text' + name]) || fallback
  }

  // MathJax, loaded once on demand; the safe configuration (_mathjax_safe_config.html) is merged
  function loadMathJax() {
    if (!mathjax) {
      mathjax = new Promise(function (resolve, reject) {
        window.MathJax = window.MathJax || {}
        // An unknown command is an error here (noundefined would show it in red): a typo such as
        // \fracc gets a message, and a shorthand only the portal knows (\R) its checker's form
        window.MathJax.tex = Object.assign(window.MathJax.tex || {}, { packages: { '[-]': ['noundefined'] } })
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
      '.' + PREVIEW + '-stale { opacity: 0.4; }' +
      '.' + PREVIEW + '-hint { display: block; color: #8a6d3b; font-size: 90%; }'
    document.head.appendChild(style)
  }

  function marked(element) {
    var question = element.closest && element.closest('.interview-question')
    return question && question.querySelector(MARKER) ? question : null
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

  function stateOf(preview) {
    var state = states.get(preview)
    if (!state) {
      // tex: what is rendered; node: its rendering (null if MathJax cannot); good: the last rendering;
      // error: MathJax's message; verdict: the portal's; settled: the user stopped typing
      state = { tex: null, node: null, good: null, error: null, verdict: null, settled: true }
      states.set(preview, state)
    }
    return state
  }

  function hint(prefix, message) {
    var element = document.createElement('span')
    element.className = PREVIEW + '-hint'
    element.textContent = prefix + ' ' + message
    return element
  }

  function draw(preview, state) {
    var children = []
    var verdict = state.verdict
    if (state.node) {
      children.push(state.node)
    } else if (!state.settled && state.good) {
      // Still typing: the last formula that could be rendered, dimmed
      var stale = document.createElement('div')
      stale.className = PREVIEW + '-stale'
      stale.appendChild(state.good)
      children.push(stale)
    }
    if (state.settled) {
      if (verdict && verdict.state === 'invalid') {
        children.push(hint(text('Portal', 'The MaRDI Portal does not accept this formula:'), verdict.message))
      } else if (state.error && !(verdict && verdict.state === 'valid')) {
        children.push(hint(text('Error', 'MathJax cannot show this formula:'), state.error))
      }
    }
    preview.dataset.check = verdict ? verdict.state : ''
    preview.replaceChildren.apply(preview, children)
    if (window.MathJax && window.MathJax.startup && window.MathJax.startup.document) {
      window.MathJax.startup.document.clear()
      window.MathJax.startup.document.updateDocument()
    }
  }

  // MathJax's rendering of tex: {node} or {error}
  function typeset(tex) {
    return loadMathJax().then(function () {
      return window.MathJax.tex2chtmlPromise(tex, { display: true })
    }).then(function (node) {
      var error = node.querySelector('mjx-merror')
      return error ? { error: error.getAttribute('data-mjx-error') || error.textContent } : { node: node }
    })
  }

  function render(input) {
    var preview = previewOf(input)
    if (!preview) return Promise.resolve()
    var state = stateOf(preview)
    var tex = input.value.trim()
    if (state.tex === tex) return Promise.resolve()
    state.tex = tex
    state.verdict = verdicts.get(tex) || null
    if (!tex) {
      state.node = state.good = state.error = null
      draw(preview, state)
      return Promise.resolve()
    }
    return typeset(tex).then(function (result) {
      if (state.tex !== tex) return // typed on meanwhile
      state.node = result.node || null
      state.error = result.error || null
      if (state.node) state.good = state.node
      return useChecked(preview, state, tex)
    }).then(function () {
      if (state.tex === tex) draw(preview, state)
    }).catch(function () {
      preview.replaceChildren() // MathJax not available: no rendering
    })
  }

  // The portal accepts what MathJax cannot render as typed: its checker's form is rendered
  function useChecked(preview, state, tex) {
    var verdict = state.verdict
    if (state.node || !verdict || verdict.state !== 'valid' || !verdict.checked) return Promise.resolve()
    return typeset(verdict.checked).then(function (result) {
      if (state.tex !== tex || !result.node) return
      state.node = state.good = result.node
      state.error = null
    })
  }

  function check(input) {
    var preview = previewOf(input)
    var url = script.dataset.texCheck
    var tex = input.value.trim()
    if (!preview || !url || !tex) return
    var state = stateOf(preview)
    var known = verdicts.get(tex)
    var asked = known ? Promise.resolve(known) : fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': script.dataset.csrf || '' },
      body: 'tex=' + encodeURIComponent(tex)
    }).then(function (response) {
      return response.ok ? response.json() : { state: 'unverified', message: '', checked: '' }
    }).catch(function () {
      return { state: 'unverified', message: '', checked: '' }
    }).then(function (verdict) {
      if (verdict.state !== 'unverified') verdicts.set(tex, verdict) // no verdict: asked again later
      return verdict
    })
    asked.then(function (verdict) {
      if (state.tex !== tex) return
      state.verdict = verdict
      return useChecked(preview, state, tex).then(function () {
        if (state.tex === tex) draw(preview, state)
      })
    })
  }

  function settle(input) {
    var preview = previewOf(input)
    if (!preview) return
    var state = stateOf(preview)
    state.settled = true
    draw(preview, state)
  }

  function timersOf(input) {
    var own = timers.get(input)
    if (!own) {
      own = {}
      timers.set(input, own)
    }
    return own
  }

  function stop(input) {
    var own = timersOf(input)
    clearTimeout(own.render)
    clearTimeout(own.check)
    clearTimeout(own.settle)
  }

  // Typing: render soon, ask the portal after a pause, show errors after a longer one
  document.addEventListener('input', function (event) {
    var input = event.target
    if (!marked(input)) return
    var preview = previewOf(input)
    if (!preview) return
    stateOf(preview).settled = false
    stop(input)
    var own = timersOf(input)
    own.render = setTimeout(function () { render(input) }, RENDER_WAIT)
    own.check = setTimeout(function () { render(input).then(function () { check(input) }) }, CHECK_WAIT)
    own.settle = setTimeout(function () { settle(input) }, SETTLE_WAIT)
  })

  // Leaving the field: everything at once
  document.addEventListener('focusout', function (event) {
    var input = event.target
    if (!marked(input)) return
    stop(input)
    render(input).then(function () {
      check(input)
      settle(input)
    })
  })

  // A field without its rendering (on loading, a new tab, page or value, after React redrew it)
  function scan() {
    var found = inputs()
    if (found.length) addStyle()
    found.forEach(function (input) {
      var preview = previewOf(input)
      if (!preview) return
      var state = stateOf(preview)
      // A field being typed into is the input handler's (pauses before asking the portal)
      if (!state.settled || state.tex === input.value.trim()) return
      render(input).then(function () { check(input) })
    })
  }

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
