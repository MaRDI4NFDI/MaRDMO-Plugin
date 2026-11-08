'''RDMO option set provider of MaRDMO: one class, its searches in :mod:`MaRDMO.optionsets`.

:class:`MaRDMOProvider` looks up its search by the provider key RDMO gives
it (see :mod:`MaRDMO.optionsets`).  Up to 0.6, every key had a class of its
own (``MaRDMO.model.providers.MathematicalModel`` and so on); settings that
still list those must be replaced by :data:`MaRDMO.optionsets.OPTIONSET_PROVIDERS`.
'''
from rdmo.options.providers import Provider

from .getters import get_items
from .helpers import define_setup
from .optionsets import PROVIDERS
from .queries import query_sources, query_sources_with_user_additions


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
            user:    Requesting user (unused).
            site:    Current site (unused).
        '''
        config = self.config
        if not search or len(search) < config.min_search:
            return []

        items = get_items()
        item_class = ([items[name] for name in config.item_class] if isinstance(config.item_class, list)
                      else items[config.item_class])
        if config.with_answers:
            return query_sources_with_user_additions(
                search = search,
                project = project,
                setup = define_setup(
                    query_attributes = config.answers,
                    creation = config.creation,
                    sources = config.sources,
                    item_class = item_class,
                    answer_class = config.answer_class,
                ),
            )
        return query_sources(
            search = search,
            item_class = item_class,
            sources = config.sources,
            not_found = config.not_found,
        )

