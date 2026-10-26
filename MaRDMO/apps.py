'''Django application configuration for the MaRDMO plugin.

Defines :class:`MaRDMOConfig`, which loads all static JSON data (questions,
ontology mappings, options, items, and properties) into app-config attributes
during the ``ready()`` phase and registers the signal router.
'''

from django.apps import AppConfig
from django.conf import settings

class MaRDMOConfig(AppConfig):
    '''MaRDMO Configuration'''

    name = 'MaRDMO'
    label = 'MaRDMO'
    verbose_name = 'MaRDMO Plugin'

    def __init__(self, app_name, app_module):
        '''Initialise MaRDMO app config, declaring all lazy data attributes as None.

        Concrete values are populated in :meth:`ready` once the Django app
        registry is fully loaded.
        '''
        super().__init__(app_name, app_module)
        self.questions = None
        self.mathmoddb = None
        self.mathalgodb = None
        self.publication_mapping = None
        self.options = None
        self.items = None
        self.properties = None

    def ready(self):
        '''Load static JSON data into app-config attributes and register signal handlers.

        Called automatically by Django after all apps are loaded.  Populates
        ``questions``, ``mathmoddb``, ``mathalgodb``, ``options``, ``items``,
        and ``properties`` so that they are available as fast in-process
        lookups throughout the plugin.
        '''

        from .getters import get_data

        self.questions = {
            'algorithm': get_data('algorithm/data/questions.json'),
            'model': get_data('model/data/questions.json'),
            'publication': get_data('publication/data/questions.json'),
            'workflow': get_data('workflow/data/questions.json'),
            'search': get_data('search/data/questions.json'),
        }
        self.mathmoddb          = get_data('model/data/mapping.json')
        self.mathalgodb         = get_data('algorithm/data/mapping.json')
        self.publication_mapping = get_data('publication/data/mapping.json')
        self.options = get_data('data/options.json')
        self.items = get_data(settings.MARDMO_PROVIDER['mardi']['items'])
        self.properties = get_data(settings.MARDMO_PROVIDER['mardi']['properties'])

        from . import router  # noqa: F401  (registers the signal receivers)
