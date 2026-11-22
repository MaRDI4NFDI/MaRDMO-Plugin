'''Django views for the MaRDMO plugin.

Provides the endpoints used by the questionnaire frontend to
communicate with background workers (the preview page of the export
providers: :func:`MaRDMO.main.render_preview`).

Provides:

- ``get_progress``   — JSON endpoint that returns current task progress for polling
- ``show_progress``  — HTML view that renders a live progress page for a running task
- ``show_success``   — HTML view that renders the completed-task result page
- ``reuse_portal_item`` — POST endpoint of the preview's "Use this item" (#141)
- ``check_tex``      — POST endpoint: the portal's verdict on a formula typed into the interview (#190)

Success page (``show_success``)
--------------------------------
After a successful portal export the success page presents two views of the
exported data (built by :mod:`MaRDMO.success`), switchable via tab buttons:

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

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from rdmo.core.plugins import get_plugin
from rdmo.projects.models import Project

from . import VERSION
from .getters import get_item_url
from .main import MaRDMOExportProvider
from .success import CLASS_ORDER, group_by_class, result_graph, split_statements
from .store import (
    _progress_store,
    clear_progress,
    _unregister_job_for_session,
    _job_belongs_to_session,
)
from .duplicates import preview_duplicates, reuse, same_duplicate
from .catalogs import catalog_of
from .tex_check import check_formula


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
        Rendered ``MaRDMO/export_result.html`` with the exported item IDs,
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
                "title": _("Not ready"),
                "errors": [_("Job not found.")],
            },
        )

    # Once the success page is shown we can drop the progress entry
    clear_progress(job_id)
    _unregister_job_for_session(request, job_id)

    created_qids = {qid for cls, name, qid in job_data["ids"]}
    by_item, relation_stmts, standard_added = split_statements(job_data, created_qids)
    grouped_ids = group_by_class(job_data["ids"], by_item)
    mardi_uri = get_item_url('mardi')
    graph_data = result_graph(grouped_ids, relation_stmts, mardi_uri)

    return render(
        request,
        "MaRDMO/export_result.html",
        {
            "grouped_ids": grouped_ids,
            "relation_stmts": relation_stmts,
            "standard_added": standard_added,
            # Set when the export failed after some entities were created
            "export_error": job_data.get("error"),
            "counts": job_data.get("counts", {}),
            "mardi_uri": mardi_uri,
            "graph_data": graph_data,
            # The graph's texts, for its script
            "graph_texts": {
                'classes': {name: _(name) for name in CLASS_ORDER},
                'new_class': _('New {class}'),
                'existing_item': _('Existing item'),
                'new_literal': _('New Literal Value'),
                'toggle': _('Click to toggle'),
                'filters': _('Filters'),
                'node_types': _('Node types'),
                'literal_values': _('Literal values'),
                'existing_items': _('Existing items'),
                'properties': _('Properties'),
                'qualifiers': _('Qualifiers'),
                'fullscreen': _('Fullscreen'),
                'exit_fullscreen': _('Exit fullscreen'),
            },
        },
    )


def _refuse(request, error):
    return render(request, 'core/error.html',
                  {'title': _('The portal item cannot be used'), 'errors': [error]}, status=400)


@login_required
@require_POST
def reuse_portal_item(request, project_id):
    """Make an item of the documentation the MaRDI Portal item it duplicates (#141).

    The preview's "Use this item" posts ``format`` (the export's key),
    ``item`` (the item's ID) and ``qid`` (the portal item).  Nothing of the
    request is trusted: the duplicate is looked up again and must allow the
    reuse (:func:`~MaRDMO.duplicates.decide`).  The user needs RDMO's
    permission to change the project's answers; Django checks the CSRF token.

    Returns:
        A redirect to the preview's box "Before you export", or an error page.
    """
    project = get_object_or_404(Project, pk=project_id)
    if not request.user.has_perm('projects.change_value_object', project):
        return render(request, 'core/error.html',
                      {'title': _('Permission denied'),
                       'errors': [_('You may not change the answers of this project.')]}, status=403)

    export_format = request.POST.get('format', '')
    provider = get_plugin('PROJECT_EXPORTS', export_format)
    catalog = catalog_of(project)
    if not isinstance(provider, MaRDMOExportProvider) or not (catalog and catalog.documents):
        return _refuse(request, _('This export cannot use portal items.'))

    provider.request, provider.project, provider.snapshot = request, project, None
    answers, _options = provider.get_post_data()
    prepare = catalog.prepare_class()
    row = same_duplicate(preview_duplicates(project, answers, prepare).rows,
                         request.POST.get('item', ''), request.POST.get('qid', ''))
    if row is None:
        return _refuse(request, _('The item is not, or no longer, a duplicate of this portal item.'))
    if row.action != 'reuse':
        return _refuse(request, ' '.join(row.reasons) or _('This item cannot become the portal item.'))
    if not row.portal_label:
        return _refuse(request, _('The label of the portal item could not be looked up; please try again.'))

    reuse(project, row.duplicate, row.portal_label, row.portal_description)
    # Back to the box at the top: the preview runs its checks again, the item is no longer listed
    return redirect(reverse('project_export', args=[project.pk, export_format]) + '#before-export')


# Longer texts are no formulas typed into the interview; they are not sent to the portal
TEX_CHECK_MAX_LENGTH = 4000


@login_required
@require_POST
def check_tex(request):
    """The MaRDI Portal's verdict on a formula typed into the interview (#190).

    The interview's script (``MaRDMO/js/math-preview.js``) posts ``tex``
    after a pause in typing.  The verdict comes from the portal's TeX check,
    as for the checks and the export, and with their cache
    (:func:`~MaRDMO.tex_check.check_formula`).  Only for logged-in users and
    with Django's CSRF token: the interview has both; the URL is not a way
    to the portal's checker for anyone else.

    Returns:
        JSON ``{"state": "valid" | "invalid" | "unverified", "message": …,
        "checked": …}``; HTTP 400 without a formula or for a text too long.
    """
    tex = request.POST.get('tex', '')
    if not tex.strip() or len(tex) > TEX_CHECK_MAX_LENGTH:
        return JsonResponse({'error': 'tex'}, status=400)
    return JsonResponse(check_formula(tex))
