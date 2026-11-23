'''The citation of a publication: looked up by its DOI and written into the questionnaire.

Provides:

- :class:`PublicationRetriever` — fetches citation metadata for a DOI and
  writes the results into the questionnaire via the adders module
- :func:`best_citation`, :func:`write_citation` — the citation of the most
  trusted source, written into the publication page

The export of publications: :class:`MaRDMO.export.worker.CatalogExport`.
'''

import html
import re
from multiprocessing.pool import ThreadPool

from .constants import ITEMINFOS, CITATIONINFOS, JOURNALS, AUTHORS, LANGUAGES
from .utils import clean_background_data, get_citation

from ..core.constants import BASE_URI
from ..core.config import get_questions
from ..project.writes import commit_writes, value_editor
from ..core.ids import is_user_id

# Publications whose citation data is looked up at the same time
CITATION_LOOKUPS_IN_PARALLEL = 3


# Formatting tags in fetched titles (Crossref, DataCite, ...); only these are
# removed, so a title like "a < b and c > d" keeps its text
_FORMATTING_TAG_RE = re.compile(
    r'</?(?:i|b|u|em|strong|sup|sub|scp|tt|sc|span|jats:[a-z-]+|mml:[a-z]+)(?:\s[^<>]*)?/?>',
    re.IGNORECASE,
)


def _single_line(text):
    '''Collapse whitespace (incl. line breaks), remove formatting tags and decode HTML entities in fetched metadata text.

    Crossref/DataCite titles and names occasionally contain line breaks, which
    the MaRDI Portal rejects, formatting tags (``<i>``, ``<sup>``) and HTML
    entities (``&amp;``), which would end up literally in labels.  Users
    cannot edit this background data, so it is normalised when stored instead
    of blocking the export.
    '''
    if not isinstance(text, str):
        return text
    return ' '.join(html.unescape(_FORMATTING_TAG_RE.sub('', text)).split())


# The sources of a citation, in the order they are trusted
CITATION_SOURCES = ('mardi', 'wikidata', 'crossref', 'datacite', 'zbmath', 'doi')


def best_citation(citations):
    '''The citation of the first source in :data:`CITATION_SOURCES` that knows the publication, or ``None``.

    Args:
        citations: The result of :func:`~.utils.get_citation` (``{source: Publication or None}``).
    '''
    return next((citations[source] for source in CITATION_SOURCES if citations.get(source)), None)


def write_citation(project, set_index, data):
    '''Write the citation *data* (:class:`~MaRDMO.core.models.Publication`) into the hidden answers of publication *set_index*.

    Name, description, entry type, title, date, volume, issue, pages, and the
    languages, journals and authors, each as one answer (metadata text on one
    line, see :func:`_single_line`).  The preview writes them, and the lookup
    of a new publication in the background (#158).
    '''
    questions = get_questions('publication')["Publication"]
    for uri, data_key in (ITEMINFOS | CITATIONINFOS).items():
        value_editor(project=project, uri=f'{BASE_URI}{questions[uri]["uri"]}',
                     info={'text': _single_line(getattr(data, data_key)), 'set_index': set_index})
    for parts, mapping in ((data.language, LANGUAGES), (data.journal, JOURNALS), (data.authors, AUTHORS)):
        for idx, part in enumerate(parts):
            for uri, data_key in mapping.items():
                value_editor(project=project, uri=f'{BASE_URI}{questions[uri]["uri"]}',
                             info={'text': _single_line(getattr(part, data_key)), 'collection_index': idx,
                                   'set_index': set_index})


class PublicationRetriever:
    '''Retrieve Metadata from MaRDI Portal, Wikidata, and other
       sources like Crossref, DataCite, zbMath, DOI, and ORCid for Workflow,
       Model, and Algorithm documentation.'''

    # Get Publication-related Questions
    questions = get_questions('publication')

    def get_information(self, project, snapshot, answers):
        '''Look up and store the citations that new and Wikidata publications are missing (#158).

        The export creates both, with their citation.  A new publication
        (``user:`` ID, selected by its DOI) gets it in the background when it
        is selected; one whose lookup failed or has not finished, those of
        imported projects, and the Wikidata publications (selected, or added
        with a Wikidata item) get it here.  Publications of the MaRDI Portal
        need none.  Nothing here changes the ID of a publication.

        Args:
            project:  RDMO project instance.
            snapshot: RDMO snapshot (``None`` for the current snapshot).
            answers:  Top-level answers dict; the caller reads the answers
                      again to show what was stored.

        Returns:
            *answers*, unchanged.
        '''
        for key, citations in self._lookup_citations(answers).items():
            data = best_citation(citations)
            if data is None:
                continue
            clean_background_data(
                key_dict  = ITEMINFOS | CITATIONINFOS | LANGUAGES | JOURNALS | AUTHORS,
                questions = self.questions["Publication"],
                project   = project,
                snapshot  = snapshot,
                set_index = key
            )
            write_citation(project, key, data)
        return answers

    @staticmethod
    def _lookup_citations(answers):
        '''Look up the citations of the new and Wikidata publications with a DOI and no citation yet, in parallel.

        Without citation means without title (a Wikidata publication has its
        name and description already).

        Returns:
            Dict mapping the publication's set index to the result of
            :func:`~.utils.get_citation`.
        '''
        dois = {
            key: publication['reference'][0][1].upper()
            for key, publication in answers.get('publication', {}).items()
            if (is_user_id(publication.get('ID')) or (publication.get('ID') or '').startswith('wikidata:'))
            and not publication.get('title')
            and publication.get('reference', {}).get(0, ['', ''])[1]
        }
        if not dois:
            return {}
        commit_writes()
        with ThreadPool(min(CITATION_LOOKUPS_IN_PARALLEL, len(dois))) as pool:
            results = pool.map(get_citation, dois.values())
        return dict(zip(dois, results))
