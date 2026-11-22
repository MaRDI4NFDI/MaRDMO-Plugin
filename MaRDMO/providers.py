'''RDMO option set provider of MaRDMO: one class, its searches in :mod:`MaRDMO.optionsets`.

:class:`MaRDMOProvider` looks up its search by the provider key RDMO gives
it (see :mod:`MaRDMO.optionsets`).  Up to 0.6, every key had a class of its
own (``MaRDMO.model.providers.MathematicalModel`` and so on); settings that
still list those must be replaced by :data:`MaRDMO.optionsets.OPTIONSET_PROVIDERS`.
'''
from rdmo.options.providers import Provider

from .getters import get_items

from .optionsets import PROVIDERS
from .queries import (
    item_by_id, publication_options, query_sources, query_sources_with_user_additions, typed_item_id,
)


class MaRDMOProvider(Provider):
    '''Searches the MaRDI Portal (and Wikidata) as its row in :data:`~MaRDMO.optionsets.PROVIDERS` says.'''

    search = True

    def __init__(self, key, label, class_name):
        super().__init__(key, label, class_name)
        self.config = PROVIDERS[key]
        self.refresh = self.config.refresh

    def get_options(self, project, search=None, user=None, site=None):
        '''Return the options for *search* (``{"id": …, "text": …}`` dicts, sorted by relevance).

        Args:
            project: RDMO project instance (its items of the user's own are offered).
            search:  Search text; nothing is searched below the row's ``min_search`` characters.
                     ``mardi:Q…`` or ``wikidata:Q…`` offers that item, if it fits.
            user:    Requesting user (unused).
            site:    Current site (unused).
        '''
        config = self.config
        if not search or len(search) < config.min_search:
            return []
        if config.by_identifier:
            return publication_options(search)

        items = get_items()
        # On the portal, the classes with a MaRDI profile are searched by it
        # (most software has no class), the others by class (#170)
        without_profile = config.classes_without_profile
        item_class = ([items[name] for name in without_profile] if isinstance(config.item_class, list)
                      else items[without_profile[0]]) if without_profile else None
        profiles = [items[name] for name in config.profiles] or None
        exclude = [items[name] for name in config.excluded_classes] or None
        sources = config.search_sources
        # The Wikidata hits must be at or below these classes, or not of these (#170)
        on_wikidata = 'wikidata' in (sources or ['wikidata'])
        roots = config.wikidata_roots if on_wikidata else None
        noise = config.wikidata_noise if on_wikidata else None
        # mardi:Q… or wikidata:Q…: that item, if it fits the dropdown (#170)
        typed = typed_item_id(search)
        if typed:
            source, qid = typed
            if source not in (sources or ['mardi', 'wikidata']):
                return []
            return item_by_id(source, qid, classes=[items[name] for name in config.classes], profiles=profiles,
                              exclude=exclude, roots=roots, noise=noise)
        if config.with_answers:
            return query_sources_with_user_additions(
                search = search,
                project = project,
                setup = define_setup(
                    query_attributes = config.answers,
                    creation = config.creation,
                    sources = sources,
                    item_class = item_class,
                    answer_class = config.answer_class,
                    roots = roots,
                    noise = noise,
                    profiles = profiles,
                    exclude = exclude,
                ),
            )
        return query_sources(
            search = search,
            item_class = item_class,
            sources = sources,
            not_found = config.not_found,
            roots = roots,
            noise = noise,
            profiles = profiles,
            exclude = exclude,
        )


def define_setup(query_attributes, creation=False, query_id='', sources=None, item_class=None,
                 answer_class=None, roots=None, noise=None, profiles=None, exclude=None):
    """Build a query-setup dict used by provider ``get_options`` methods.

    Args:
        query_attributes: List of questionnaire attribute keys whose existing
                          values are surfaced as user-defined options.
        creation:         If ``True``, a "create new" option is prepended when
                          the search term is not found.
        query_id:         Identifier passed through to the query (optional).
        sources:          List of external sources to search (e.g.
                          ``['mardi', 'wikidata']``).  ``None`` defaults to
                          both sources inside the query helper.
        item_class:       Wikibase QID string or list of QID strings used to
                          restrict the MaRDI class-based search.
        answer_class:     MathModDB class key (``Quantity`` or ``QuantityKind``)
                          the user's own quantities must have (optional).
        roots:            Wikidata classes the Wikidata hits must be at or
                          below (``None``: not filtered, #170).
        noise:            Wikidata classes the Wikidata hits must not be
                          instances of, where no roots fit (``None``: none).
        profiles:         QIDs of MaRDI profiles whose items the portal
                          search finds too (``None``: none).
        exclude:          QIDs of classes whose items the portal search
                          leaves out (``None``: none).

    Returns:
        Dict consumed by :func:`~MaRDMO.queries.query_sources_with_user_additions`.
    """
    return {
        'creation': creation,
        'query_attributes': query_attributes,
        'query_id': query_id,
        'sources': sources,
        'item_class': item_class,
        'answer_class': answer_class,
        'roots': roots,
        'noise': noise,
        'profiles': profiles,
        'exclude': exclude,
    }
