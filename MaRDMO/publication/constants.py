'''Compile-time constants for the Publication documentation sub-package.

Defines the property-to-predicate mappings (``PROPS``), item-info dicts
(``ITEMINFOS``, ``CITATIONINFOS``), and lookup tables for journals, authors,
and languages that the publication worker and handlers consume.

Also provides ``get_publication_relations()`` — the single authoritative
source for the shared publication-role → Wikibase-property mapping used by
the model, algorithm, and workflow ``get_relations()`` functions.
'''

from ..catalogs import registrations
from ..getters import get_items, get_properties, get_publication_mapping


def get_publication_relations():
    '''Return the shared publication-role → Wikibase property+qualifier mapping.

    Used by the model, algorithm, and workflow ``get_relations()`` functions so
    the mapping is defined exactly once.

    Returns:
        Dict mapping each ``mardmo/`` publication-role URL to a
        ``[property, qualifier_item]`` list.
    '''
    publication_mapping = get_publication_mapping()
    items               = get_items()
    properties          = get_properties()
    return {
        publication_mapping.get(key='analyzes')['url']: [
            properties['described by source'],
            items['analysis']
        ],
        publication_mapping.get(key='applies')['url']: [
            properties['described by source'],
            items['application']
        ],
        publication_mapping.get(key='documents')['url']: [
            properties['described by source'],
            items['documentation']
        ],
        publication_mapping.get(key='invents')['url']: [
            properties['described by source'],
            items['invention']
        ],
        publication_mapping.get(key='studies')['url']: [
            properties['described by source'],
            items['study']
        ],
        publication_mapping.get(key='surveys')['url']: [
            properties['described by source'],
            items['review']
        ],
        publication_mapping.get(key='uses')['url']: [
            properties['described by source'],
            items['use']
        ],
    }


PROPS = {
    'P2ME':  ['documents', 'invents', 'studies', 'surveys', 'uses'],
    'P2A':   ['analyzes', 'applies', 'invents', 'studies', 'surveys'],
    'P2BS':  ['documents', 'uses'],
    'P2IWE': ['analyzes', 'applies', 'documents', 'invents', 'studies', 'surveys', 'uses'],
}


def routing():
    '''The relations a publication can have, per catalog: ``{catalog name: [rule, …]}``.

    Each catalog declares its rules (:attr:`~MaRDMO.catalogs.Registration.routing`):
    which classes of items a publication of it can be related to, by which
    relation types (:data:`PROPS`) and in which answer.
    '''
    return {catalog.name: list(registration.routing) for registration in registrations()
            for catalog in registration.catalogs if registration.routing}

# URI mappings for item infos
# The name is the label: a publication referenced by its MaRDI Portal or
# Wikidata ID is shown with the item's label and description (the title
# statement may differ or be missing); for the other sources both are the title
ITEMINFOS = {
    "Name": "label",
    "Description": "description"
}

# URI mappings for citation infos
CITATIONINFOS = {
    "Entrytype": "entrytype",
    "Title": "title",
    "Date": "date",
    "Volume": "volume",
    "Issue": "issue",
    "Page": "page"
}

# URI mappings for languages
LANGUAGES = {
    "Language ID": "id",
    "Language Name": "label",
    "Language Description": "description"
}

# URI mappings for journals
JOURNALS = {
    "Journal ID": "id",
    "Journal ISSN": "issn",
    "Journal Name": "label",
    "Journal Description": "description"
}

# URI mappings for author
AUTHORS = {
    "Author ID": "id",
    "Author ORCID": "orcid_id",
    "Author ZBMath": "zbmath_id",
    "Author Wikidata": "wikidata_id",
    "Author Name": "label",
    "Author Description": "description"
}
