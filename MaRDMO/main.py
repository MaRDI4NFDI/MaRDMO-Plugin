'''Main export entry points and RDMO provider classes for MaRDMO.

Provides:

- :class:`BaseMaRDMOExportProvider` — abstract base carrying the MaRDI Portal
  OAuth2 credentials and callback wiring shared by all providers that need to
  post to the portal.
- :class:`MaRDMOExportProvider` — "Export to MaRDI Portal" button; handles
  preview and authenticated upload for the model, algorithm, and workflow
  documentation catalogs.
- :class:`MaRDMOQueryProvider` — "Query MaRDI Portal" button; handles the
  search-catalog preview and result rendering without requiring OAuth2.
- :func:`render_preview` — the preview page of both providers.
'''

from abc import ABC

from django import forms
from django.conf import settings
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.utils.translation import gettext, gettext_lazy as _, ngettext

from rdmo.projects.exports import Export

from .core.catalogs import SEARCH, catalog_of
from .export.duplicates import preview_duplicates
from . import VERSION
from .core.config import catalog_questions, get_item_url, get_options, get_questions, get_url
from .project.answers import get_answers, process_question_dict
from .export.ordering import topological_order
from .project.pages import describe_items_without_page, distinguish_publications, link_to_pages
from .project.writes import batched_writes
from .export.oauth2 import OauthProviderMixin
from .project.pages import add_tab_names, interview_urls
from .export.problems import attach as attach_problems, report_lines
from .export import pipeline

from .search.sparql import SEARCH_LIMIT
from .search.worker import search
from .components.publication.worker import PublicationRetriever


def _documenting(project):
    '''The :class:`~MaRDMO.core.catalogs.Catalog` of *project* if it documents items, else ``None``.'''
    catalog = catalog_of(project)
    return catalog if catalog and catalog.documents else None


def render_preview(self, template, answers, option, submit_label, duplicates=None, gate=None):
    """Render the documentation preview page.

    Args:
        self:       Export provider instance with ``request``, ``ExportForm``,
                    ``project`` and ``key`` attributes.
        template:   Template name (relative path) to include in the preview.
        answers:    Prepared answers dict passed to the template context.
        option:     Option string controlling template behaviour (passed to context).
        duplicates: :class:`~MaRDMO.export.duplicates.Report` of the items that are on
                    the MaRDI Portal already; shown at the top, and while it has
                    rows the export button is disabled (#141).
        gate:       :class:`~MaRDMO.export.pipeline.Gate` of the checks; while it is
                    not clear the export button is disabled (#152).

    Returns:
        HTTP 200 response rendering ``MaRDMO/preview.html``.
    """
    return render(
        self.request,
        'MaRDMO/preview.html',
        {
            'form': self.ExportForm(),
            'include_file': template,
            'include_params': {
                'title': self.project.title
            },
            'answers': answers,
            'option': option,
            'submit_label': submit_label,
            'duplicates': duplicates,
            'gate': gate,
            # The interview pages of the problems' pages, linked in "Before you export"
            'interview': interview_urls(self.project, {problem.page.section for problem in gate.problems + gate.hints
                                                       if problem.page is not None}) if gate else {},
            'project': self.project,
            'export_format': getattr(self, 'key', ''),
            'mardiURI': get_item_url('mardi'),
            'wikidataURI': get_item_url('wikidata'),
            # Appended to the stylesheet URL so browsers reload it after an update
            'mardmo_version': VERSION,
        },
        status=200
    )


class BaseMaRDMOExportProvider(OauthProviderMixin, Export, ABC):
    '''Base export provider wiring MaRDMO to the MaRDI Portal OAuth2 flow.

    Provides the concrete MaRDI Portal URLs and credentials needed by
    :class:`~MaRDMO.export.oauth2.OauthProviderMixin`.  Subclasses implement
    the catalog-specific :meth:`render` and :meth:`submit_*` methods.
    '''
    @property
    def oauth2_client_id(self):
        '''OAuth2 client ID read from ``settings.MARDMO_PROVIDER["mardi"]``.'''
        return settings.MARDMO_PROVIDER['mardi']['oauth2_client_id']

    @property
    def oauth2_client_secret(self):
        '''OAuth2 client secret read from ``settings.MARDMO_PROVIDER["mardi"]``.'''
        return settings.MARDMO_PROVIDER['mardi']['oauth2_client_secret']

    @property
    def authorize_url(self):
        '''MaRDI Portal OAuth2 authorization endpoint URL.'''
        return f"{get_url('mardi', 'uri')}/w/rest.php/oauth2/authorize"

    @property
    def token_url(self):
        '''MaRDI Portal OAuth2 token exchange endpoint URL.'''
        return f"{get_url('mardi', 'uri')}/w/rest.php/oauth2/access_token"

    def get_authorize_params(self, request, state):
        '''Return OAuth2 authorization query parameters for the MaRDI Portal.

        Args:
            request: Django HTTP request (unused — client ID is from settings).
            state:   CSRF state token generated by the OAuth2 flow.

        Returns:
            Dict with ``response_type``, ``client_id``, and ``state`` keys.
        '''
        return {
            'response_type': 'code',
            'client_id': self.oauth2_client_id,
            'state': state
        }

    def get_callback_data(self, request):
        '''Return POST body fields for the MaRDI Portal token exchange request.

        Args:
            request: Django HTTP request supplying the ``code`` GET parameter.

        Returns:
            Dict with ``client_id``, ``client_secret``, ``grant_type``, and
            ``code`` fields.
        '''
        return {
            'client_id': self.oauth2_client_id,
            'client_secret': self.oauth2_client_secret,
            'grant_type': 'authorization_code',
            'code': request.GET.get('code')
        }


# The export page names what the export finds; the preview offered the export,
# so it found nothing then (#152)
CHANGED_HINT = _('Something changed since the preview. Open the preview again, fix the points it lists, '
                 'then export.')
UNREACHABLE_HINT = _('The MaRDI Portal is not reachable at the moment, so the documentation could not be '
                     'checked completely. Nothing was exported; please try again shortly.')


class MaRDMOExportProvider(BaseMaRDMOExportProvider):
    '''Export provider for the "Export to MaRDI Portal" button.

    Handles preview and authenticated Wikibase upload for the model, algorithm,
    and workflow documentation catalogs.  Search is handled separately by
    :class:`MaRDMOQueryProvider`.

    Attributes:
        request: The Django HttpRequest associated with the provider.
    '''

    request: HttpRequest

    class ExportForm(forms.Form):
        '''Empty form class required by the RDMO Export provider interface.'''

    def render(self):
        '''Render the catalog-appropriate documentation preview page.

        Dispatches to the correct template based on the active catalog
        (model, algorithm, or workflow).

        Returns:
            HTTP response rendering the preview page, or an error page for
            unsupported catalogs.
        '''

        catalog = _documenting(self.project)

        if catalog:
            answers, options = self.get_post_data('preview')
            prepare_class, checks_class = catalog.prepare_class, catalog.checks_class
            # Items that are on the MaRDI Portal already, at the top (#141)
            duplicates = preview_duplicates(self.project, answers, prepare_class())
            # Everything the export checks, so a clean preview exports (#152)
            gate = pipeline.run(self.project, answers, prepare_class, checks_class,
                                preview=True, duplicates=duplicates)
            # The red marks of the pages are these problems (#152), the blue ones the hints (#167)
            attach_problems(answers, gate.problems + gate.hints)
            return render_preview(
                self=self,
                template=catalog.template,
                answers=answers,
                option=options,
                submit_label=_('Export to MaRDI Portal'),
                duplicates=duplicates,
                gate=gate,
            )

        return render(
            self.request,
            'core/error.html',
            {
                'title': _('Catalog Error'),
                'errors': [_('The catalog is not supported by the MaRDMO Plugin.')]
            },
            status=200
        )

    def submit(self):
        '''Dispatch the form submission to the catalog-appropriate export handler.

        Handles the cancel action, checks OAuth2 credentials, then routes to
        :meth:`_submit_catalog` based on the active project catalog.

        Returns:
            HTTP redirect or rendered response from the selected submit method.
        '''
        if 'cancel' in self.request.POST:
            return redirect('project', self.project.id)

        if not (self.oauth2_client_id and self.oauth2_client_secret):
            return render(
                self.request,
                'core/error.html',
                {
                    'title': _('Missing Credentials'),
                    'errors': [_('Credentials for MaRDI Portal are missing!')]
                },
                status=200
            )

        catalog = _documenting(self.project)

        if not catalog:
            return render(
                self.request,
                'core/error.html',
                {
                    'title': _('Unknown catalog'),
                    'errors': [_('Cannot handle this catalog type.')]
                },
                status=400
            )

        return self._submit_catalog(catalog)

    def _submit_catalog(self, catalog):
        '''Check the documentation once more and submit it for any supported catalog.

        Runs what the preview ran (:func:`~MaRDMO.export.pipeline.run`): the
        preview offers the export only when it found nothing, so whatever is
        found now changed since the preview (in the documentation or on the
        MaRDI Portal).  Then delegates to :meth:`~MaRDMO.export.oauth2.OauthProviderMixin.post`
        for the authenticated upload.

        Args:
            catalog: The project's :class:`~MaRDMO.core.catalogs.Catalog`.

        Returns:
            HTTP response — either an error page or a redirect to the OAuth
            authorization flow.
        '''
        answers, __ = self.get_post_data()
        gate = pipeline.run(self.project, answers, catalog.prepare_class, catalog.checks_class)
        if gate.unreachable:
            return render(self.request, 'core/error.html', {
                'title': _('MaRDI Portal not reachable'),
                'errors': [gate.unreachable, UNREACHABLE_HINT],
            }, status=200)
        if gate.internal:
            # MaRDMO's error, not the documentation's: nothing changed
            return render(self.request, 'core/error.html', {
                'title': _('Export not possible'), 'errors': [str(problem.message) for problem in gate.problems],
            }, status=200)
        if gate.problems:
            return render(self.request, 'core/error.html', {
                'title': _('Incomplete or Inconsistent Documentation'),
                'errors': [CHANGED_HINT, *report_lines(gate.problems)],
            }, status=200)
        return self.post(self.request, gate.payload, topological_order(gate.dependency))

    def get_post_data(self, mode = 'submit'):
        '''Collect and pre-process user answers for the documentation catalogs.

        Reads all RDMO project values, names the pages by their tabs, gives
        relations the name and description of their page, applies the
        catalog's preview step, and returns the structured answers dict
        alongside the global options dict.

        Supports the model, algorithm, and workflow documentation catalogs;
        callers check the catalog beforehand.  The search catalog is handled
        by :class:`MaRDMOQueryProvider`.

        Args:
            mode: ``'preview'`` first looks up the citation data of the
                  publications and stores it in the project; ``'submit'``
                  (default) reads what is stored.

        Returns:
            Tuple ``(answers, options)`` where *answers* is a nested dict
            organised by entity type (e.g. ``{"field": {...}, "model": {...}}``)
            and *options* maps RDMO option URIs to their string values.
        '''
        options = get_options()

        catalog = catalog_of(self.project)
        questions = get_questions(catalog.questions) | get_questions('publication')
        if catalog.subset:
            # The basics catalog shares the model's questions but has fewer (#168)
            questions = catalog_questions(questions, self.project.catalog)
        answers = process_question_dict(
            project=self.project,
            questions=questions,
            get_answer=get_answers
        )

        if mode == 'preview':
            publication = PublicationRetriever()
            # MaRDMO always works on the current values, also when the export
            # was opened from a snapshot
            with batched_writes():
                answers = publication.get_information(
                    project=self.project,
                    snapshot=None,
                    answers=answers,
                )
            # The export reads the citation data (title, authors, journal, ...)
            # from the project; read the answers again so the preview shows it too
            answers = process_question_dict(
                project=self.project,
                questions=questions,
                get_answer=get_answers
            )

        # Pages are named by their tab (#152); relations show their page's
        # name and description (IDs, #100), own items without page a generic
        # one (#129)
        add_tab_names(self.project, answers)
        # Publications with the name and description of another one get their DOI in it (#183)
        distinguish_publications(answers)
        link_to_pages(answers)
        describe_items_without_page(answers)

        prepare = catalog.prepare_class()
        answers = prepare.preview(answers)

        return answers, options


class MaRDMOQueryProvider(Export):
    '''Export provider for the "Query MaRDI Portal" button.

    Handles the search-catalog preview (showing a form to configure the query)
    and the submit action (executing the search and rendering matching results).
    Does not require OAuth2 — no portal writes are performed.

    Attributes:
        request: The Django HttpRequest associated with the provider.
    '''

    request: HttpRequest

    class ExportForm(forms.Form):
        '''Empty form class required by the RDMO Export provider interface.'''

    def render(self):
        '''Render the search configuration preview page.

        Returns:
            HTTP response rendering ``MaRDMO/preview_search.html``, or an error
            page if the active catalog is not the search catalog.
        '''
        if getattr(catalog_of(self.project), 'kind', None) == SEARCH:
            answers, options = self.get_post_data()
            return render_preview(
                self = self,
                template = 'MaRDMO/preview_search.html',
                answers = answers,
                option = options,
                submit_label = _('Query MaRDI Portal'),
            )

        return render(
            self.request,
            'core/error.html',
            {
                'title': _('Catalog Error'),
                'errors': [_('The catalog is not supported by the MaRDMO Query Plugin.')]
            },
            status=200
        )

    def submit(self):
        '''Execute the MaRDI Portal query and render the results page.

        Handles the cancel action (redirects to the project page), then calls
        :meth:`submit_mardmo_search` for the search catalog.

        Returns:
            HTTP redirect or rendered results response.
        '''
        if 'cancel' in self.request.POST:
            return redirect('project', self.project.id)

        if getattr(catalog_of(self.project), 'kind', None) == SEARCH:
            return self.submit_mardmo_search()

        return render(
            self.request,
            'core/error.html',
            {
                'title': _('Unknown catalog'),
                'errors': [_('Cannot handle this catalog type.')]
            },
            status=400
        )

    def submit_mardmo_search(self):
        '''Execute a MaRDI Portal search and render the matching results.

        The headline counts the results, or says that there are more than
        :data:`~MaRDMO.search.sparql.SEARCH_LIMIT`; the class of the search
        mode stands above them, as on the result page of the export.

        Returns:
            Rendered ``MaRDMO/search_results.html`` response with the list of
            matching portal items.
        '''
        answers, _options = self.get_post_data()
        kind, count = answers.get('kind'), len(answers['links'])
        if answers.get('more'):
            heading = gettext('More than %(limit)s results in the MaRDI Portal') % {'limit': SEARCH_LIMIT}
        elif count:
            heading = ngettext('%(count)s result in the MaRDI Portal', '%(count)s results in the MaRDI Portal',
                               count) % {'count': count}
        else:
            heading = gettext('No results in the MaRDI Portal')

        return render(
            self.request,
            'MaRDMO/search_results.html',
            {
                'heading': heading,
                'kind': gettext(kind) if kind else '',
                'links': answers['links'],
                'more': answers.get('more', False),
                'limit': SEARCH_LIMIT,
                'searchFailed': answers.get('search_failed', False),
            },
            status=200
        )

    def get_post_data(self):
        '''Load and execute the search query for the search catalog.

        Reads the search configuration from RDMO project values and dispatches
        to the :func:`~MaRDMO.search.worker.search` function to retrieve
        matching items from the MaRDI Portal.  Callers check beforehand that
        the project uses the search catalog.

        Returns:
            Tuple ``(answers, options)`` where *answers* contains the search
            results and *options* maps RDMO option URIs to their string values.
        '''
        options = get_options()

        answers = process_question_dict(
            project = self.project,
            questions = get_questions('search'),
            get_answer = get_answers
        )

        return search(answers, options), options
