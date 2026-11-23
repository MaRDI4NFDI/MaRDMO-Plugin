'''The items of an export: each once, and what the export gave them (#198).

The export takes every item of the answers once (:func:`unique_items`) and
afterwards finds the items it created (:func:`compare_items`); after it,
:func:`replace_ids` gives the answers that referred to them the item's new
portal ID.
'''
from rdmo.projects.models import Value

from ..core.config import get_options
from ..core.ids import is_own_item, is_user_id, item_text
from ..core.properties import find_reference
from ..project.writes import internal_write


# Answer keys of a publication's parts: an item under them is an author or a
# journal (#118), which the export creates with their own statements
PART_KINDS = {'author': 'author', 'journal': 'journal'}


def item_key(identifier, name, description):
    '''Return what makes an item in an export the same item: ``(ID, name, description)``.

    The user's own items are the same item when name and description are:
    the same new programming language on two software pages, or the same
    new author in two publications.
    '''
    return ('user' if is_own_item(identifier) else identifier, name, description)


def unique_items(data, title = None):
    '''Collect all unique items referenced anywhere in *data*.

    Recursively walks the nested answers dict and returns every sub-dict
    that contains an ``ID`` key exactly once.  An optional workflow *title*
    item is prepended as ``Item0000000000``.

    Args:
        data:  Top-level answers dict.
        title: Optional workflow title string.  When provided, a placeholder
               item for the workflow itself is added first.

    Returns:
        Tuple ``(items, dependency)`` where *items* maps ``"Item<n>"`` keys to
        ``{ID, Name, Description, orcid, zbmath, issn}`` dicts (with ``kind``
        ``author`` or ``journal`` for the authors and journals of
        publications, see :data:`PART_KINDS`) and *dependency*
        maps the same keys to empty sets (populated later by
        :class:`~MaRDMO.export.payload.GeneratePayload`).
    '''
    # Set up Item Dict and track seen Items
    items = {}
    dependency = {}
    seen_items = {}
    # Add Workflow Item
    if title:
        triple = (
            *item_key('not found', title, data.get('general', {}).get('objective', '')),
            '', '', '', None
        )
        items[f'Item{str(0).zfill(10)}'] = {
            'ID': 'not found',
            'Name': title,
            'Description': data.get('general', {}).get('objective', '')
        }
        seen_items[triple] = f'Item{str(0).zfill(10)}'
        dependency.update({f'Item{str(0).zfill(10)}': set()})
    # Add Workflow Component Items

    def search(subdict, kind=None):
        '''Search unique Items; *kind* is the kind of the publication part they are in.'''
        if isinstance(subdict, dict) and 'ID' in subdict:
            triple = (
                *item_key(subdict.get('ID', ''), subdict.get('Name', ''), subdict.get('Description', '')),
                subdict.get('orcid', ''),
                subdict.get('zbmath', ''),
                subdict.get('issn', ''),
                kind
            )
            if triple not in seen_items:
                item = f'Item{str(len(items)).zfill(10)}'  # Create unique key
                items[item] = {
                    'ID': subdict.get('ID', ''),
                    'Name': triple[1],
                    'Description': triple[2],
                    'orcid': triple[3],
                    'zbmath': triple[4],
                    'issn': triple[5]
                }
                if kind:
                    items[item]['kind'] = kind
                seen_items[triple] = item
                dependency.update({item: set()})
            # All user: IDs of the item, to give them its portal ID after the export
            if is_user_id(subdict['ID']):
                user_ids = items[seen_items[triple]].setdefault('user_ids', [])
                if subdict['ID'] not in user_ids:
                    user_ids.append(subdict['ID'])
        if isinstance(subdict, dict):
            for key, value in subdict.items():
                if isinstance(value, dict):
                    search(value, PART_KINDS.get(key, kind))
    search(data)
    _add_publication_dois(data, items, seen_items)
    return items, dependency


def _add_publication_dois(data, items, seen_items):
    '''Give the items of the publication pages of *data* their DOI (``doi``), if they have one (#158).

    The duplicate check finds publications on the MaRDI Portal by it
    (:func:`~MaRDMO.export.duplicates.look_up`).
    '''
    option = get_options()['DOI']
    for page in (data.get('publication') or {}).values():
        if not isinstance(page, dict) or not page.get('ID'):
            continue
        doi = find_reference(page.get('reference'), option)
        key = seen_items.get((*item_key(page['ID'], page.get('Name', ''), page.get('Description', '')),
                              page.get('orcid', ''), page.get('zbmath', ''), page.get('issn', ''), None))
        if doi and doi[1] and key:
            items[key].setdefault('doi', doi[1])


def compare_items(old, new, wikidata_qid_prop=None):
    """Return the items that got a QID by the export, by their payload key (``Item<n>``).

    Compares the ``id`` field of every ``Item*`` key: entries that had no id
    before posting (``old[key]['id']`` is falsy) and have one afterwards are
    collected together with the original external ID and the new QID.
    Items still without id (export aborted before they were posted) are
    skipped.

    The original external ID is inferred from the item's statements: items
    that carry a Wikidata QID external-id statement are tagged as
    ``wikidata:<QID>``; all others are tagged as ``user``, with the
    ``user:`` IDs the item had in the project (``user_ids`` of the payload
    entry).

    Args:
        old:                Deep copy of the payload dict taken *before* posting.
        new:                Payload dict *after* posting (ids filled in by Wikibase).
        wikidata_qid_prop:  Property ID string for the Wikidata QID property
                            (e.g. ``'P123'``), used to detect Wikidata-sourced
                            items.  Pass ``get_properties().get('Wikidata QID')``.

    Returns:
        Dict mapping payload keys to ``{'label': …, 'description': …,
        'old_id': <original external id>, 'new_qid': <assigned QID>,
        'class': <class>, 'user_ids': [<user: IDs>]}``.
    """

    created = {}
    for key, value in old.items():
        if key.startswith('Item') and not value['id'] and new[key].get('id'):
            item = new[key]
            label = item['payload']['item']['labels']['en']
            description = item['payload']['item'].get('descriptions', {}).get('en', '')

            # Detect wikidata items by presence of the Wikidata QID statement.
            old_id = 'user'
            if wikidata_qid_prop:
                for stmt in value.get('statements', []):
                    if stmt[0] == wikidata_qid_prop and stmt[1] == 'external-id':
                        old_id = f'wikidata:{stmt[2]}'
                        break

            created[key] = {
                'label':    label,
                'description': description,
                'old_id':   old_id,
                'new_qid':  item['id'],
                'class':    old[key].get('class', ''),
                'user_ids': old[key].get('user_ids', []),
            }
    return created


def replace_ids(project, created):
    """Update RDMO project Values after a successful portal export.

    For every newly created MaRDI Portal item, every
    :class:`~rdmo.projects.models.Value` in *project* that holds its old ID
    gets the new ``mardi:<QID>`` identifier:

    - **Wikidata items**: matched by their ``wikidata:<QID>``.
    - **Items of the user's own**: matched by their ``user:`` IDs (all of
      them, if the export made one item of several, see :func:`unique_items`).

    The text becomes the exported item's ``"Label (Description)"``
    (:func:`~MaRDMO.core.ids.item_text`).

    Args:
        project:  RDMO project instance whose Values should be updated.
        created:  Dict as returned by :func:`compare_items` —
                  ``{key: {'label': ..., 'description': ..., 'old_id': ..., 'new_qid': ...,
                  'user_ids': [...]}}``.
    """

    # Wikidata items: one bulk query per export, matched by QID
    wikidata_map = {
        info['old_id']: (f"mardi:{info['new_qid']}", item_text(info['label'], info['description']))
        for info in created.values()
        if info['old_id'].startswith('wikidata:')
    }
    if wikidata_map:
        for v in Value.objects.filter(
            project=project, snapshot=None, external_id__in=wikidata_map
        ).select_related('attribute'):
            v.external_id, v.text = wikidata_map[v.external_id]
            with internal_write():
                v.save()

    # Items of the user's own: matched by ID, written with update() so an
    # interview open on another page can still save
    for info in created.values():
        if info.get('user_ids'):
            Value.objects.filter(
                project=project, snapshot=None, external_id__in=info['user_ids']
            ).update(
                external_id=f"mardi:{info['new_qid']}",
                text=item_text(info['label'], info['description']),
            )
