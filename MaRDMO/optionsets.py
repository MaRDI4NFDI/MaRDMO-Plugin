'''The setting ``OPTIONSET_PROVIDERS`` for MaRDMO's option set providers.

The questionnaire names a provider by its key (``provider_key`` of an option
set); RDMO creates the provider as ``Class(key, label, class_name)`` from the
setting and asks it for options with the search text only, not with the
question.  So one provider class, :class:`MaRDMO.providers.MaRDMOProvider`,
looks up its search by key in :data:`MaRDMO.core.searches.PROVIDERS`.

The RDMO settings import :data:`OPTIONSET_PROVIDERS` while Django starts, so
neither this module nor :mod:`MaRDMO.core.searches` may import RDMO or MaRDMO
models::

    from MaRDMO.optionsets import OPTIONSET_PROVIDERS as MARDMO_OPTIONSET_PROVIDERS
    OPTIONSET_PROVIDERS = MARDMO_OPTIONSET_PROVIDERS
'''
from django.utils.translation import gettext_lazy as _

from .core.searches import PROVIDERS


#: The setting ``OPTIONSET_PROVIDERS`` for every MaRDMO option set.
OPTIONSET_PROVIDERS = [
    (key, _(search.label), 'MaRDMO.providers.MaRDMOProvider') for key, search in PROVIDERS.items()
]
