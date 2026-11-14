'''Items of a documentation that exist on the MaRDI Portal already (#141).

The export creates the user's own items and the Wikidata items it uses.  One
of them is a duplicate if the portal has an item with exactly its label and
description (the portal's own rule), a Wikidata item also if a portal item
has its Wikidata QID (P12); also an own item with the label and description
of a Wikidata item of the same documentation (the portal takes only one).
:func:`look_up` finds them; the export stops at them
(:meth:`~MaRDMO.payload.GeneratePayload.process_items`), the preview lists
them at the top (:func:`preview_duplicates`), with the action the user can
take:

- ``reuse``: the portal item may be used instead; :func:`reuse` rewrites the
  answers to it.  Allowed if none of the markers (class, community, profile
  type) the export would give the item contradicts the portal item's
  (:func:`~MaRDMO.markers.contradictions`); the export then adds the missing
  ones.
- ``rename``: an own item whose portal namesake is another kind of item;
  the user renames it.
- ``replace``: a Wikidata item whose portal twin is another kind of item; a
  new name would not change its Wikidata QID, so the user chooses another
  item or makes it a new one.
- ``unknown``: the portal item's markers could not be looked up.

Authors and journals of publications are not shown: MaRDMO takes them from
the citation, the user cannot change them.  :func:`_resolve_parts` decides
for them in the background.
'''
from dataclasses import dataclass, field
import logging
import time

from django.urls import reverse
from rdmo.projects.models import Value
from rdmo.questions.models import Question

from .getters import get_items
from .helpers import unique_items
from .ids import id_attributes, is_own_item, item_text
from .markers import PUBLICATION_MARKERS, SECTION_MARKERS, class_families, contradictions
from .queries import find_portal_items, portal_labels

logger = logging.getLogger(__name__)

# The preview waits less for the portal than the export (which checks again)
PREVIEW_RETRY_WAITS = (2,)
PREVIEW_DEADLINE = 30

# The kinds of new items the export creates (process_items) besides the user's own
CREATED = ('wikidata', 'not found', 'author', 'journal')


def item_source(value):
    '''How the export treats the item *value* of :func:`~MaRDMO.helpers.unique_items`.

    ``mardi`` (exists), ``wikidata`` (created with its Wikidata QID), ``not
    found`` (the user's own), ``author`` or ``journal`` (new parts of a
    publication, #118); ``None`` if it is not exported (no ID, or an author
    without ORCID iD and zbMATH ID).
    '''
    identifier = value.get('ID')
    if not identifier:
        return None
    if is_own_item(identifier):
        source = value.get('kind') or 'not found'
    else:
        source = next((source for source in ('mardi', 'wikidata') if source in identifier), None)
    if source == 'author' and not (value.get('zbmath') or value.get('orcid')):
        return None
    return source


@dataclass
class Duplicate:
    """An item the export would create that exists on the portal as *qid*.

    *rule*: ``wikidata`` (same Wikidata QID), ``label`` (same label and
    description), or ``documentation`` (same label and description as the
    item *other* of the same documentation; *qid* is empty).
    """
    item: dict
    source: str
    qid: str
    rule: str
    other: dict | None = None


# The identifiers of authors and journals, in the order they name the item in a description
PART_IDENTIFIERS = {
    'author': (('orcid', 'ORCID iD'), ('zbmath', 'zbMath ID')),
    'journal': (('issn', 'ISSN'),),
}


def part_identifier(item):
    """``(name, value)`` of the first identifier of the author or journal *item*; ``None`` without any.

    ORCID iD, zbMATH author ID (authors) or ISSN (journals), then the
    Wikidata QID.
    """
    for key, name in PART_IDENTIFIERS[item['kind']]:
        if item.get(key):
            return name, item[key]
    if item['ID'].startswith('wikidata:'):
        return 'Wikidata QID', item['ID'].split(':', 1)[1]
    return None


def look_up(items, waits, deadline):
    """Look up *items* ``[(source, item)]`` on the MaRDI Portal (see :func:`item_source`).

    Items the user documents are :class:`Duplicate` if the portal has them
    (or another item of the documentation has their label and
    description).  Authors and journals of publications are never reported:
    the user cannot change them, so :func:`_resolve_parts` decides.

    Returns:
        ``(found, duplicates)``: the :class:`~MaRDMO.queries.PortalItems`
        (with the markers of the existing items and of the duplicates' portal
        items) and the :class:`Duplicate` items.
    """
    created = [(source, item) for source, item in items if source in CREATED]
    found = find_portal_items(
        pairs=[(item['Name'], item['Description']) for _, item in created],
        wikidata_qids=[item['ID'] for source, item in created if source == 'wikidata'],
        marker_qids=[item['ID'] for source, item in items if source == 'mardi'],
        waits=waits,
        deadline=deadline,
    )
    documented = [(source, item) for source, item in created if not item.get('kind')]
    duplicates = []
    for source, item in documented:
        twin = found.by_wikidata.get(item['ID'].split(':', 1)[-1]) if source == 'wikidata' else None
        same = found.by_label.get((item['Name'], item['Description']))
        if twin:
            duplicates.append(Duplicate(item, source, twin, 'wikidata'))
        elif same:
            duplicates.append(Duplicate(item, source, same, 'label'))
    duplicates += _same_in_documentation(documented, {id(duplicate.item) for duplicate in duplicates})
    _resolve_parts([(source, item) for source, item in created if item.get('kind')], found, waits, deadline)
    return found, duplicates


def _same_in_documentation(documented, reported):
    """Own items with the label and description of a Wikidata item of the documentation.

    The portal takes only one item per label and description.  (Own items
    with the same name and description are one item already, see
    :func:`~MaRDMO.ids.item_key`; Wikidata has no two such items.)
    """
    wikidata = {(item['Name'], item['Description']): item for source, item in documented
                if source == 'wikidata' and item['Description']}
    return [Duplicate(item, source, '', 'documentation', other=wikidata[(item['Name'], item['Description'])])
            for source, item in documented
            if source != 'wikidata' and (item['Name'], item['Description']) in wikidata and id(item) not in reported]


def _resolve_parts(parts, found, waits, deadline):
    """Decide for the new authors and journals *parts* that are on the portal already.

    Sets ``use`` (the portal item's QID: the export adds to it), ``create_as``
    (the description of the new item) or ``omit`` (left out) on the item:

    1. a portal item with the same Wikidata QID is the item;
    2. so is one with the same label and MaRDMO's description with the
       item's own identifier, e.g. "scientist (ORCID iD …)";
    3. otherwise a portal item with the same label and description does not
       say who it is: the item is created with its identifier in the
       description, e.g. "researcher (Wikidata QID Q1)", unless exactly
       that item exists (then it is used);
    4. a journal without any identifier uses the portal item with its title
       and description if that is not another kind of item, else it is
       left out.
    """
    fallback = {}
    for source, item in parts:
        twin = found.by_wikidata.get(item['ID'].split(':', 1)[-1]) if source == 'wikidata' else None
        same = found.by_label.get((item['Name'], item['Description']))
        if twin:
            item['use'] = twin
            continue
        if not same:
            continue
        identifier = part_identifier(item)
        if identifier and source != 'wikidata' and identifier[1].lower() in item['Description'].lower():
            item['use'] = same
        elif identifier:
            fallback[(item['Name'], f"{item['Description']} ({identifier[0]} {identifier[1]})")] = item
        else:
            portal = found.markers.get(same)
            if portal is not None and not contradictions(PUBLICATION_MARKERS['journal'], portal):
                item['use'] = same
            else:
                item['omit'] = True
                logger.info("Journal '%s' left out: %s has its title and description but is no journal.",
                            item['Name'], same)
    if fallback:
        again = find_portal_items(pairs=list(fallback), waits=waits, deadline=deadline)
        found.markers.update(again.markers)
        found.markers_failed = found.markers_failed or again.markers_failed
        for pair, item in fallback.items():
            if again.by_label.get(pair):
                item['use'] = again.by_label[pair]
            else:
                item['create_as'] = pair[1]


def item_ids(item):
    '''All IDs the answers give the item *item* (several ``user:`` IDs if the export merges pages).'''
    return item.get('user_ids') or [item['ID']]


@dataclass
class Row:
    '''A row of the preview's section "Already on the MaRDI Portal".'''
    duplicate: Duplicate
    action: str
    portal_label: str = ''
    portal_description: str = ''
    # {'class': [names], 'community': [...], 'profile': [...]} of the portal item
    portal_markers: dict = field(default_factory=dict)
    # Why the portal item cannot be reused, one line per marker
    reasons: list = field(default_factory=list)
    # [{'page': title, 'tab': name, 'url': interview URL}] where the item is entered
    locations: list = field(default_factory=list)


@dataclass
class Report:
    '''The duplicates of a documentation, for the preview.'''
    rows: list = field(default_factory=list)
    # The portal could not be asked: the export checks again
    failed: bool = False


def _names(qids):
    '''The names (items.json) of *qids*, the QID for those MaRDMO does not know.'''
    names = {}
    for name, qid in get_items().items():
        names.setdefault(qid, name)
    return sorted(names.get(qid, qid) for qid in qids)


def _reasons(sections, catalog, portal):
    '''Why the item of *sections* (:data:`~MaRDMO.markers.SECTION_MARKERS`) may not become the portal item.'''
    reasons = []
    families = class_families()
    for section in sorted(sections):
        markers = SECTION_MARKERS[catalog][section]
        kinds = contradictions(markers, portal)
        ours = markers.qids()
        if 'class' in kinds:
            family = families.get(ours['class'], set())
            other = [qid for qid in portal['class'] if qid in families and families[qid].isdisjoint(family)]
            reasons.append(f"Its class on the MaRDI Portal is {', '.join(_names(other))}; "
                           f"MaRDMO would give it the class {markers.cls}.")
        if 'community' in kinds:
            reasons.append(f"It belongs to {', '.join(_names(portal['community']))}; "
                           f"MaRDMO would add {markers.community}.")
        if 'profile' in kinds:
            reasons.append(f"Its profile type is {', '.join(_names(portal['profile']))}; "
                           f"MaRDMO would add {markers.profile}.")
    return list(dict.fromkeys(reasons))


def decide(duplicate, found, sections, catalog):
    '''The action for *duplicate* and the reasons, see the module.

    *sections*: ``{item ID: sections}`` (``marker_sections`` of the worker).
    '''
    if duplicate.rule == 'documentation':
        other = duplicate.other
        return 'rename', [f"The Wikidata item {other['ID'].split(':', 1)[-1]} of this documentation has the same "
                          "label and description, and the MaRDI Portal takes only one item per label and "
                          "description. Rename yours, or select the Wikidata item."]
    portal = found.markers.get(duplicate.qid)
    if portal is None:
        return 'unknown', ['The markers of the portal item could not be looked up.']
    item_sections = set().union(*(sections.get(identifier, set()) for identifier in item_ids(duplicate.item)))
    reasons = _reasons(item_sections, catalog, portal)
    if not reasons:
        return 'reuse', []
    return ('replace' if duplicate.source == 'wikidata' else 'rename'), reasons


def documentation_items(answers):
    '''``[(source, item)]`` of the items the export of *answers* handles (see :func:`item_source`).'''
    items, _ = unique_items(answers)
    return [(item_source(item), item) for item in items.values() if item_source(item)]


def preview_duplicates(project, answers, prepare):
    '''The rows of the preview's section "Already on the MaRDI Portal".

    Args:
        project: The RDMO project (for where the items are entered).
        answers: The preview's answers (``get_post_data``).
        prepare: The catalog's worker (``PrepareModel`` ...).

    Returns:
        :class:`Report`.
    '''
    found, duplicates = look_up(documentation_items(answers), PREVIEW_RETRY_WAITS,
                                time.monotonic() + PREVIEW_DEADLINE)
    report = Report(failed=found.label_failed or found.wikidata_failed)
    if not duplicates:
        return report
    sections = prepare.marker_sections(answers)
    twins = [duplicate.qid for duplicate in duplicates if duplicate.rule == 'wikidata']
    labels = (portal_labels(twins, PREVIEW_RETRY_WAITS) if twins else {}) or {}
    places = locations(project, [identifier for duplicate in duplicates for identifier in item_ids(duplicate.item)])
    for duplicate in duplicates:
        action, reasons = decide(duplicate, found, sections, prepare.catalog)
        label, description = labels.get(duplicate.qid) or (
            (duplicate.item['Name'], duplicate.item['Description']) if duplicate.rule == 'label' else ('', ''))
        portal = found.markers.get(duplicate.qid) or {}
        report.rows.append(Row(
            duplicate=duplicate,
            action=action,
            portal_label=label,
            portal_description=description,
            portal_markers={kind: _names(qids) for kind, qids in portal.items()},
            reasons=reasons,
            locations=[place for identifier in item_ids(duplicate.item) for place in places.get(identifier, [])],
        ))
    return report


def _pages(question, catalog):
    '''The pages of *catalog* that hold *question* (directly or in its question sets).'''
    pages, sets = list(question.pages.all()), list(question.questionsets.all())
    while sets and not pages:
        pages = [page for questionset in sets for page in questionset.pages.all()]
        sets = [parent for questionset in sets for parent in questionset.parents.all()]
    return [page for page in pages if page.sections.filter(catalogs=catalog).exists()]


def locations(project, identifiers):
    '''Where the items *identifiers* are entered: ``{ID: [{'page', 'tab', 'url'}]}``.

    The page of an item is where its ID is asked (``<section>/id``); an item
    without page of its own (e.g. a programming language) is where it was
    entered.  The tab is the name of the page's set (RDMO cannot open a tab,
    so it is named).
    '''
    values = (Value.objects.filter(project=project, snapshot=None, external_id__in=identifiers)
              .select_related('attribute'))
    on_pages = {value.external_id for value in values if value.attribute.uri in id_attributes()}
    places = {}
    for value in values:
        # An item's own page, if it has one; else every answer that entered it
        if value.external_id in on_pages and value.attribute.uri not in id_attributes():
            continue
        tab = int(value.set_prefix.split('|')[0]) if value.set_prefix else value.set_index
        for question in Question.objects.filter(attribute=value.attribute):
            for page in _pages(question, project.catalog):
                name = ''
                if page.is_collection and page.attribute:
                    name = (Value.objects.filter(project=project, snapshot=None, attribute=page.attribute,
                                                 set_prefix='', set_index=tab)
                            .values_list('text', flat=True).first() or '')
                place = {'page': page.title, 'tab': name or f'#{tab + 1}',
                         'url': reverse('project_interview', args=[project.pk]) + f'{page.pk}/'}
                if place not in places.setdefault(value.external_id, []):
                    places[value.external_id].append(place)
    return places


def reuse(project, duplicate, label, description):
    '''Make the item of *duplicate* the portal item: rewrite the project's answers.

    Every answer with one of the item's IDs gets ``mardi:<QID>`` and the text
    "Label (Description)" of the portal item; the name and description of
    its page become the portal item's.  Written with ``update()``, without
    MaRDMO's handlers (they would ask the portal), as
    :func:`~MaRDMO.helpers.replace_ids` after an export.

    Returns:
        The number of answers changed.
    '''
    identifiers = item_ids(duplicate.item)
    # The item's pages (<section>/id); not the pages an item without page was entered on
    pages = list(Value.objects.filter(project=project, snapshot=None, external_id__in=identifiers,
                                      attribute__uri__in=id_attributes(), attribute__uri__endswith='/id')
                 .select_related('attribute'))
    changed = Value.objects.filter(project=project, snapshot=None, external_id__in=identifiers).update(
        external_id=f'mardi:{duplicate.qid}', text=item_text(label, description))
    for page in pages:
        section = page.attribute.uri.rsplit('/', 1)[0]
        prefix = f'{page.set_prefix}|{page.set_index}' if page.set_prefix else str(page.set_index)
        for field_name, text in (('name', label), ('description', description)):
            changed += Value.objects.filter(
                project=project, snapshot=None, attribute__uri=f'{section}/{field_name}', set_prefix=prefix,
            ).update(text=text)
    return changed


def same_duplicate(report_rows, item_id, qid):
    '''The row of *report_rows* for the item with ID *item_id* and the portal item *qid*, or ``None``.'''
    return next((row for row in report_rows
                 if row.duplicate.qid == qid and item_id in item_ids(row.duplicate.item)), None)

