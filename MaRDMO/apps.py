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

        from .core.catalogs import registrations
        from .core.config import get_data

        # The publication's questions belong to every catalog; the others are the catalogs' own
        self.questions = {'publication': get_data('components/publication/data/questions.json')}
        for registration in registrations():
            self.questions.update({key: get_data(path) for key, path in registration.questions.items()})
        self.mathmoddb          = get_data('model/data/mapping.json')
        self.mathalgodb         = get_data('algorithm/data/mapping.json')
        self.publication_mapping = get_data('components/publication/data/mapping.json')
        self.options = get_data('data/options.json')
        self.items = get_data(settings.MARDMO_PROVIDER['mardi']['items'])
        self.properties = get_data(settings.MARDMO_PROVIDER['mardi']['properties'])

        from . import router  # noqa: F401  (registers the signal receivers)
