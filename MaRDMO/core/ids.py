'''The IDs of the items in a project, and what they say (#198).

Every item in a project has an ID: ``mardi:<QID>`` or ``wikidata:<QID>`` for
an item of the MaRDI Portal or Wikidata, ``user:<uuid>`` for an item of the
user's own.  The dropdowns offer "new item" (ID of a page) or the typed
label (relations) to add an own item, both with the option ID "not found",
which never becomes a stored ID
(:func:`~MaRDMO.project.identity.assign_id`).

These are the rules only, without the database: what keeps the IDs right
while a project is answered is in :mod:`MaRDMO.project.identity`, the items
of an export in :mod:`MaRDMO.export.items`.
'''
import uuid
from urllib.parse import unquote

NOT_FOUND = 'not found'
# Text of the option NOT_FOUND in the ID dropdown of a page
NEW_ITEM = 'new item'
SOURCES = ('user', 'mardi', 'wikidata')

# A publication is selected by its identifier with a prefix (#158); for now the DOI.
# The option of a new publication has the ID NEW_DOI + DOI, which the router turns
# into a user: ID (assign_id)
DOI_PREFIX = 'doi:'
NEW_DOI = 'new:doi:'
# Links to a DOI that are dropped when pasted after the prefix
_DOI_LINKS = ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'http://dx.doi.org/', 'doi.org/')


def new_user_id():
    '''Return a new ID for an item of the user's own.'''
    return f'user:{uuid.uuid4()}'


def part_id(kind, *keys):
    '''Return the ``user:`` ID of a new author or journal (*kind*) of a publication.

    The preview writes a publication's authors and journal again each time
    from its citation, so their ID is derived from the first of *keys* that
    is given (ORCID iD, zbMATH ID, Wikidata QID, name; ISSN, Wikidata QID,
    title): the same each time, and the same for the same author in two
    publications.
    '''
    key = next((key for key in keys if key and key != 'None'), '')
    return f'user:{uuid.uuid5(uuid.NAMESPACE_URL, f"mardmo/{kind}/{key}")}'


def is_user_id(identifier):
    '''Return ``True`` if *identifier* is the ID of an item of the user's own.'''
    return bool(identifier) and identifier.startswith('user:')


def is_item_id(identifier):
    '''Return ``True`` if *identifier* is an ID of the form ``<source>:<id>``.'''
    return bool(identifier) and identifier.split(':', 1)[0] in SOURCES and ':' in identifier


def is_portal_item(identifier):
    '''Return ``True`` if *identifier* is the ID of an item of the MaRDI Portal or Wikidata.'''
    return bool(identifier) and identifier.split(':', 1)[0] in ('mardi', 'wikidata') and ':' in identifier


def is_own_item(identifier):
    '''Return ``True`` for an item of the user's own: a ``user:`` ID or "not found".

    Answers never store "not found" (:func:`assign_id`); it is the ID of the
    workflow itself in the export (:func:`~MaRDMO.export.items.unique_items`), and
    of the items of projects made before 0.8.0, which the checks report.
    '''
    return identifier == NOT_FOUND or is_user_id(identifier)


# The ID of the links of a tab whose item was cleared: tab:<section>:<set index>
PLACEHOLDER_PREFIX = 'tab:'


def tab_placeholder(section, set_index):
    '''The ID the links of tab *set_index* of *section* get while it has no item (#186).'''
    return f'{PLACEHOLDER_PREFIX}{section}:{set_index}'


def publication_doi(text):
    '''The DOI of the identifier *text* typed for a publication (``doi:10.1000/x``), or ``None``.

    The prefix is required (case does not matter); spaces around and a link
    pasted after the prefix (``doi:https://doi.org/10.1000/x``) are dropped.
    A link is percent-encoded (``%3C`` for ``<``, ``%23`` for ``#`` in old
    DOIs): its DOI is decoded.  The DOI itself is not checked:
    :func:`~MaRDMO.components.validators.doi_problem` does.
    '''
    prefix, separator, rest = (text or '').strip().partition(':')
    if not separator or prefix.strip().lower() != DOI_PREFIX[:-1]:
        return None
    doi = rest.strip()
    for link in _DOI_LINKS:
        if doi.lower().startswith(link):
            doi = unquote(doi[len(link):].strip())
            break
    return doi


def item_text(name, description):
    '''Return the text of an answer that refers to an item, as the dropdowns show it.

    ``"Label (Description)"``, ``"Label"`` without description.  The source
    is not part of it (#103): the dropdowns show it in the option's help
    (:func:`~MaRDMO.components.dropdowns.option_help`), the preview by the ID.
    '''
    return f'{name} ({description})' if description else name


