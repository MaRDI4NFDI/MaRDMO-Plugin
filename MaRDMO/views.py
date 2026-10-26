'''Django views for the MaRDMO plugin.

Provides the three AJAX endpoints used by the questionnaire frontend to
communicate with background workers, plus the ``render_preview`` helper
used by export providers to build HTML previews.

Provides:

- ``get_progress``   — JSON endpoint that returns current task progress for polling
- ``show_progress``  — HTML view that renders a live progress page for a running task
- ``show_success``   — HTML view that renders the completed-task result page
- ``render_preview`` — helper that renders a Jinja2 template with questionnaire answers

Success page (``show_success``)
--------------------------------
After a successful portal export the success page presents two views of the
exported data, switchable via tab buttons:

**List view** — every newly created MaRDI Portal item, grouped by class, with
all its statements shown as ``property → value`` lines.  Values that are
external identifiers (DOI, ORCID, swMath ID, …) or URLs are rendered as
clickable links.  Qualifier statements are shown indented beneath their parent.
Mathematical expressions (``math`` datatype) are typeset via
`MathJax <https://www.mathjax.org/>`_ (Apache 2.0).

**Graph view** — an interactive network graph built with
`Cytoscape.js <https://js.cytoscape.org/>`_ (MIT) showing items as labelled
circles and literal values as rectangles, connected by directed, labelled
edges.  Features include zoom/pan controls, click-to-open portal links on
nodes, a qualifier tooltip on edge click, and a filter panel that lets the user
toggle individual node classes, literal/existing-item layers, and individual
edge properties.
'''

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .constants import (DOI_BASE_URL, ISSN_BASE_URL, MORWIKI_BASE_URL, ORCID_BASE_URL,
                        QUDT_CONSTANT_URL, QUDT_QUANTITYKIND_URL, SWMATH_BASE_URL,
                        WIKIDATA, ZBMATH_AUTHOR_BASE_URL)
from . import VERSION
from .getters import get_item_url
from .validators import url_problem
from .store import (
    _progress_store,
    clear_progress,
    _unregister_job_for_session,
    _job_belongs_to_session,
)

@login_required
def get_progress(request, job_id):
    """Return the current progress data for *job_id* as a JSON response.

    Args:
        request: Django HTTP request; the user must own the job (checked via
                 the session).  Raises :exc:`~django.http.Http404` otherwise.
        job_id:  Unique job identifier string.

    Returns:
        :class:`~django.http.JsonResponse` with keys ``progress`` (int 0–100)
        and ``done`` (bool), defaulting to ``{"progress": 0, "done": False}``
        when no data is found.
    """
    if not _job_belongs_to_session(request, job_id):
        raise Http404()

    data = _progress_store.get(job_id, {"progress": 0, "done": False})
    return JsonResponse(data)


@login_required
@require_GET
def show_progress(request, job_id):
    """Render the progress-bar page for the given job.

    Args:
        request: Django HTTP request; the user must own the job (checked via
                 the session).  Raises :exc:`~django.http.Http404` otherwise.
        job_id:  Unique job identifier string passed to the template.

    Returns:
        Rendered ``MaRDMO/progress.html`` response with context ``job_id`` and
        ``mardmo_version`` (appended to the script URL so browsers load the
        current script after an update).
    """
    if not _job_belongs_to_session(request, job_id):
        raise Http404()

    return render(
        request,
        "MaRDMO/progress.html",
        {"job_id": job_id, "mardmo_version": VERSION},
    )


@login_required
@require_GET
def show_success(request, job_id):
    """Render the export-success page and clean up the job's progress entry.

    Args:
        request: Django HTTP request; the user must own the job (checked via
                 the session).  Raises :exc:`~django.http.Http404` otherwise.
        job_id:  Unique job identifier string; the associated progress data is
                 cleared from the cache after being read.

    Returns:
        Rendered ``MaRDMO/portalExport.html`` with the exported item IDs,
        or an error page if the job data is missing.
    """
    if not _job_belongs_to_session(request, job_id):
        raise Http404()

    job_data = _progress_store.get(job_id)
    if not job_data or "ids" not in job_data:
        return render(
            request,
            "core/error.html",
            {
                "title": "Not ready",
                "errors": ["Job not found."],
            },
        )

    # Once the success page is shown we can drop the progress entry
    clear_progress(job_id)
    _unregister_job_for_session(request, job_id)

    # Group ids by class in a fixed display order
    _CLASS_ORDER = [
        'Mathematical Model', 'Research Problem', 'Formula', 'Computational Task',
        'Quantity', 'Algorithm', 'Algorithmic Task', 'Software', 'Benchmark',
        'Workflow', 'Process Step', 'Hardware', 'CPU Model', 'Dataset',
        'Experimental Method', 'Experimental Equipment', 'Academic Discipline',
        'Programming Language', 'Publication', 'Author', 'Journal',
    ]
    grouped = defaultdict(list)
    for cls, name, qid in job_data["ids"]:
        grouped[cls].append({'name': name, 'qid': qid})
    # Split statements: those on newly created items vs. those on existing items
    created_qids = {qid for cls, name, qid in job_data["ids"]}

    _SKIP_PROPS = {'community', 'MaRDI profile type'}

    def _obj_url(prop, obj, obj_qid):
        """Return a clickable external URL for *obj* based on its property name.

        Returns an empty string when *obj_qid* is set (the object is already a
        portal item and needs no external URL) or when the property is not one
        of the known identifier/URL properties.
        """
        if obj_qid:
            return ''
        if prop == 'Wikidata QID':
            return f'{WIKIDATA["entity"]}{obj}'
        if prop == 'DOI':
            return f'{DOI_BASE_URL}{obj}'
        if prop == 'swMath work ID':
            return f'{SWMATH_BASE_URL}{obj}'
        if prop == 'MORwiki ID':
            return f'{MORWIKI_BASE_URL}{obj}'
        if prop in ('described at URL', 'source code repository URL', 'URL'):
            # User-entered URL: only http(s) may become a link (no javascript: etc.)
            return obj if not url_problem(obj) else ''
        if prop == 'QUDT quantity kind ID':
            return f'{QUDT_QUANTITYKIND_URL}{obj}'
        if prop == 'QUDT constant ID':
            return f'{QUDT_CONSTANT_URL}{obj}'
        if prop == 'ORCID iD':
            return f'{ORCID_BASE_URL}{obj}'
        if prop == 'zbMATH author ID':
            return f'{ZBMATH_AUTHOR_BASE_URL}{obj}'
        if prop == 'ISSN':
            return f'{ISSN_BASE_URL}{obj}'
        return ''

    stmt_map = defaultdict(list)
    relation_stmts = []
    for stmt in job_data.get("statements", []):
        subj, subj_qid, prop, obj, obj_qid = stmt[0], stmt[1], stmt[2], stmt[3], stmt[4]
        qualifiers  = stmt[5] if len(stmt) > 5 else []
        unit_label  = stmt[6] if len(stmt) > 6 else ''
        unit_qid    = stmt[7] if len(stmt) > 7 else ''
        obj_url = _obj_url(prop, obj, obj_qid)
        for q in qualifiers:
            q['obj_url'] = _obj_url(q['prop'], q['obj'], q.get('obj_qid', ''))
        if prop in _SKIP_PROPS:
            continue
        if subj_qid in created_qids:
            stmt_map[subj_qid].append(
                {'prop': prop, 'obj': obj, 'obj_qid': obj_qid, 'obj_url': obj_url,
                 'qualifiers': qualifiers, 'unit_label': unit_label, 'unit_qid': unit_qid}
            )
        else:
            relation_stmts.append({
                'subject': subj, 'subject_qid': subj_qid,
                'prop': prop, 'obj': obj, 'obj_qid': obj_qid, 'obj_url': obj_url,
                'qualifiers': qualifiers, 'unit_label': unit_label, 'unit_qid': unit_qid,
            })

    # Attach statements to each item and group by class
    items_by_class = defaultdict(list)
    for cls, name, qid in job_data["ids"]:
        items_by_class[cls].append({'name': name, 'qid': qid, 'stmts': stmt_map.get(qid, [])})

    grouped_ids = [
        (cls, items_by_class[cls]) for cls in _CLASS_ORDER if cls in items_by_class
    ] + [
        (cls, items) for cls, items in items_by_class.items() if cls not in _CLASS_ORDER
    ]

    mardi_uri = get_item_url('mardi')

    # Build graph data for Cytoscape
    graph_nodes = {}
    graph_edges = []
    _lit_idx = 0

    def _add_item_node(qid, label, node_type, cls=''):
        """Insert or upgrade a node entry in *graph_nodes*.

        *node_type* ``'new'`` always wins over ``'item'``; an existing ``'new'``
        node is never overwritten by an ``'item'`` entry for the same QID.
        """
        if not qid:
            return
        existing = graph_nodes.get(qid)
        # 'new' always wins; only insert 'item' if the node isn't already known
        if existing is None or (node_type == 'new' and existing['node_type'] != 'new'):
            graph_nodes[qid] = {
                'id': qid, 'label': label,
                'node_type': node_type, 'cls': cls,
                'url': mardi_uri + qid,
            }

    def _get_obj_node(obj_qid, obj_label, obj_url=''):
        """Return the graph node ID for a statement object, creating the node if needed.

        If *obj_qid* is set the object is a portal item (circle node).  Otherwise
        a fresh literal node (rectangle) is created with an auto-incremented ID
        and optional *obj_url* for click-through linking.
        """
        nonlocal _lit_idx
        if obj_qid:
            _add_item_node(obj_qid, obj_label, 'item')
            return obj_qid
        nid = f'_lit_{_lit_idx}'
        _lit_idx += 1
        graph_nodes[nid] = {
            'id': nid, 'label': obj_label, 'node_type': 'literal', 'cls': '', 'url': obj_url,
        }
        return nid

    for cls, items in grouped_ids:
        for item in items:
            qid = item['qid']
            _add_item_node(qid, item['name'], 'new', cls)
            for s in item['stmts']:
                obj_nid = _get_obj_node(s['obj_qid'], s['obj'], s.get('obj_url', ''))
                graph_edges.append({
                    'source': qid, 'target': obj_nid,
                    'label': s['prop'], 'qualifiers': s.get('qualifiers', []),
                })
                if s.get('unit_qid'):
                    _add_item_node(s['unit_qid'], s['unit_label'], 'item')
                    graph_edges.append({
                        'source': obj_nid, 'target': s['unit_qid'],
                        'label': 'unit', 'qualifiers': [],
                    })

    for r in relation_stmts:
        subj_qid = r['subject_qid']
        if subj_qid:
            _add_item_node(subj_qid, r['subject'], 'item')
            obj_nid = _get_obj_node(r['obj_qid'], r['obj'], r.get('obj_url', ''))
            graph_edges.append({
                'source': subj_qid, 'target': obj_nid,
                'label': r['prop'], 'qualifiers': r.get('qualifiers', []),
            })
            if r.get('unit_qid'):
                _add_item_node(r['unit_qid'], r['unit_label'], 'item')
                graph_edges.append({
                    'source': obj_nid, 'target': r['unit_qid'],
                    'label': 'unit', 'qualifiers': [],
                })

    graph_data = {'nodes': list(graph_nodes.values()), 'edges': graph_edges}

    return render(
        request,
        "MaRDMO/portalExport.html",
        {
            "grouped_ids": grouped_ids,
            "relation_stmts": relation_stmts,
            # Set when the export failed after some entities were created
            "export_error": job_data.get("error"),
            # Items linked to existing portal items instead of being created
            "export_notes": job_data.get("notes", []),
            "counts": job_data.get("counts", {}),
            "mardi_uri": mardi_uri,
            "graph_data": graph_data,
        },
    )

def render_preview(self, template, answers, option, submit_label):
    """Render the documentation preview page.

    Args:
        self:     Export provider instance with ``request``, ``ExportForm``,
                  and ``project`` attributes.
        template: Template name (relative path) to include in the preview.
        answers:  Prepared answers dict passed to the template context.
        option:   Option string controlling template behaviour (passed to context).

    Returns:
        HTTP 200 response rendering ``MaRDMO/mardmoPreview.html``.
    """
    return render(
        self.request,
        'MaRDMO/mardmoPreview.html', 
        {
            'form': self.ExportForm(),
            'include_file': template,
            'include_params': {
                'title': self.project.title
            },
            'answers': answers,
            'option': option,
            'submit_label': submit_label,
            'mardiURI': get_item_url('mardi'),
            'wikidataURI': get_item_url('wikidata'),
            # Appended to the stylesheet URL so browsers reload it after an update
            'mardmo_version': VERSION,
        },
        status=200
    )
