'''Writing a documentation as the interview does: the answers of a page, one by one.

Every answer is placed where the interview puts it (``set_prefix``,
``set_index``, ``collection_index``, ``set_collection`` from the catalog's
pages and question sets), checked by MaRDMO's validator for the question,
saved (MaRDMO gives new items their ID) and announced with RDMO's signal
``value_created``, so MaRDMO's handlers run as in the interview: a portal
item selected on a page fills it and adds the pages of its relations, a
new item typed into a relation gets a page of its own.

Items are selected from the options of the question's provider, searched
by their label, as the user would: a portal item the search does not offer
(another class, say) cannot be selected and stops the build.

    doc = Documentation(project, catalog)
    model = doc.tab('model', 'MM1', New('MaRDMO synthetic model A', 'synthetic model'))
    model.answer('properties', 'is-deterministic', 'is-dynamic')
    model.block('model-to-formulation', {'formulation-relation': 'contains', 'formulation-relatant': [formula]})
'''
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from rdmo.core.plugins import get_plugin
from rdmo.domain.models import Attribute
from rdmo.options.models import Option
from rdmo.projects.models import Value
from rdmo.projects.signals import value_created, value_updated

from MaRDMO.ids import NEW_ITEM, NOT_FOUND
from MaRDMO.router import PRESAVE_VALIDATOR_MAP

from .catalog import DOMAIN, OPTIONS, Catalog


# --- Items to select ------------------------------------------------------------------

@dataclass
class New:
    '''A new item of the user's own, on its page (the option "new item" of the page's ID).'''
    label: str
    description: str


@dataclass
class Portal:
    '''An item of the MaRDI Portal.'''
    qid: str
    label: str
    search: Optional[str] = None     # what to type into the dropdown, if not the label

    @property
    def id(self):
        return f'mardi:{self.qid}'


@dataclass
class Wikidata:
    '''An item of Wikidata.'''
    qid: str
    label: str
    search: Optional[str] = None     # what to type into the dropdown, if not the label

    @property
    def id(self):
        return f'wikidata:{self.qid}'


@dataclass
class Typed:
    '''A new item typed into a relation (the provider's creation); MaRDMO gives it a page of its own.

    After the selection :attr:`id` is the ``user:`` ID it got.
    '''
    label: str
    id: Optional[str] = None


# --- Being polite to the services -------------------------------------------------------

PAUSE = 0.5
_REQUEST = requests.Session.request
SENT = []


def _paused(self, method, url, *args, **kwargs):
    time.sleep(PAUSE)
    SENT.append((method, url))
    return _REQUEST(self, method, url, *args, **kwargs)


def polite(monkeypatch):
    '''Pause before every request to an external service, and count them (:data:`SENT`).'''
    monkeypatch.setattr(requests.Session, 'request', _paused)


# --- The documentation ----------------------------------------------------------------

def _option_uri(key):
    return key if key.startswith('http') else OPTIONS + key


class Documentation:
    '''The project *project* of the catalog *catalog*, written page by page.'''

    def __init__(self, project, catalog: Catalog):
        self.project = project
        self.catalog = catalog
        self.slug = catalog.name
        self.log = []

    # Pages

    def tab(self, section, name, item):
        '''A new page (tab *name*) of *section* for *item* (:class:`New`, :class:`Portal`, :class:`Wikidata`).

        A new item gets its name and short description as the user types them;
        a new publication gets them from its citation (its DOI, see :meth:`Tab.answer`).
        '''
        page = self.catalog.page(section)
        index = self._next_tab(section)
        self._store(page.attribute, '', index, 0, page.is_collection, text=name)
        tab = Tab(self, section, index)
        tab.select('id', item)
        if isinstance(item, New) and section != 'publication':
            tab.answer('name', item.label)
            tab.answer('description', item.description)
        return tab

    def find(self, section, item):
        '''The page of *section* that MaRDMO added for *item* (a :class:`Typed` after its selection, an ID, a :class:`Tab`).'''
        identifier = getattr(item, 'id', item)
        values = Value.objects.filter(project=self.project, snapshot=None, set_prefix='',
                                      attribute__uri=f'{DOMAIN}{section}/id', external_id=identifier)
        assert values.count() == 1, f'{values.count()} pages of {section} with the ID {identifier}'
        return Tab(self, section, values.first().set_index)

    def tabs(self, section):
        '''All pages of *section*, in their order.'''
        indexes = sorted(set(Value.objects.filter(project=self.project, snapshot=None, set_prefix='',
                                                  attribute__uri=f'{DOMAIN}{section}/id')
                             .values_list('set_index', flat=True)))
        return [Tab(self, section, index) for index in indexes]

    def _next_tab(self, section):
        indexes = Value.objects.filter(project=self.project, snapshot=None, set_prefix='',
                                       attribute__uri__in=[f'{DOMAIN}{section}', f'{DOMAIN}{section}/id']
                                       ).values_list('set_index', flat=True)
        return max(indexes, default=-1) + 1

    # Answers

    def _store(self, attribute, set_prefix, set_index, collection_index, set_collection,
               text='', option=None, external_id=''):
        '''Save one answer as the interview does: validate, save, signal.'''
        value = Value(
            project=self.project, snapshot=None,
            attribute=Attribute.objects.get(uri=DOMAIN + attribute),
            set_prefix=set_prefix, set_index=set_index, collection_index=collection_index,
            set_collection=set_collection, text=text, external_id=external_id, value_type='text',
            option=Option.objects.get(uri=_option_uri(option)) if option else None)
        validator = PRESAVE_VALIDATOR_MAP.get(self.slug, {}).get(value.attribute.uri)
        if validator:
            validator(value)
        value.save()
        value_created.send(sender=Value, instance=value)
        self.log.append((attribute, set_prefix, set_index, collection_index, text, external_id, option))
        return value

    def _update(self, value, text='', option=None, external_id=''):
        '''Change one answer as the interview does: validate, save, signal.'''
        value.text, value.external_id = text, external_id
        value.option = Option.objects.get(uri=_option_uri(option)) if option else None
        validator = PRESAVE_VALIDATOR_MAP.get(self.slug, {}).get(value.attribute.uri)
        if validator:
            validator(value)
        value.save()
        value_updated.send(sender=Value, instance=value)
        self.log.append((value.attribute.uri, value.set_prefix, value.set_index, value.collection_index, text,
                         external_id, option))
        return value

    def options(self, question, search):
        '''The options the question's provider offers for *search*.'''
        provider = get_plugin('OPTIONSET_PROVIDERS', question.providers[0])
        return provider.get_options(self.project, search=search)


@dataclass
class Tab:
    '''A page (tab) of a section of the documentation.'''
    doc: Documentation
    section: str
    index: int
    _sets: dict = field(default_factory=dict)

    # What the page holds

    def _value(self, attribute):
        if not any(question.attribute == f'{self.section}/{attribute}' for question in self.doc.catalog.questions()):
            return None
        return Value.objects.filter(project=self.doc.project, snapshot=None,
                                    attribute__uri=f'{DOMAIN}{self.section}/{attribute}', **self._place(attribute)).first()

    @property
    def id(self):
        value = self._value('id')
        return value.external_id if value else ''

    @property
    def label(self):
        value = self._value('name')
        return value.text if value else ''

    @property
    def description(self):
        value = self._value('description')
        return value.text if value else ''

    def answered(self, key, within=()):
        '''Whether the question *key* of this page has an answer (e.g. one MaRDMO filled in).'''
        return Value.objects.filter(project=self.doc.project, snapshot=None,
                                    attribute__uri=f'{DOMAIN}{self.section}/{key}',
                                    **self._place(key, within)).exists()

    # Where an answer goes

    def _question(self, key):
        return self.doc.catalog.question(f'{self.section}/{key}')

    def _questionset(self, key):
        found = [element for element in self.doc.catalog.page(self.section).walk()
                 if element.kind == 'questionset' and element.key.endswith(key)]
        assert len(found) == 1, f'{len(found)} question sets of {self.section} ending with {key}'
        return found[0]

    def _indexes(self, element, within):
        '''The set indexes of *element*'s sets: the page's, then 0 or the next of *within* per question set.'''
        indexes, given = [self.index], list(within)
        for questionset in element.sets[1:]:
            if questionset.is_collection:
                assert given, f'{element.key}: in a block of {questionset.key}, give its index (within=...)'
                indexes.append(given.pop(0))
            else:
                indexes.append(0)
        assert not given, f'{element.key}: more block indexes than blocks ({within})'
        return indexes

    def _place(self, attribute, within=()):
        question = self._question(attribute)
        indexes = self._indexes(question, within)
        return {'set_prefix': '|'.join(map(str, indexes[:-1])), 'set_index': indexes[-1]}

    def _next_collection_index(self, question, place):
        values = Value.objects.filter(project=self.doc.project, snapshot=None,
                                      attribute__uri=DOMAIN + question.attribute, **place)
        return max(values.values_list('collection_index', flat=True), default=-1) + 1

    # Writing

    def answer(self, key, *answers, within=()):
        '''Answer the question *key* of this page (e.g. ``name``, ``element/symbol``).

        An answer is a text, an option (its key or the end of it, e.g.
        ``contains``), an option with its text (``('doi', '10.1/x')``), or an
        item to select (:class:`Portal`, :class:`Wikidata`, :class:`Typed`, a
        :class:`Tab` of the documentation).  A question of several answers
        takes them all; *within* are the indexes of the blocks it is in.
        '''
        question = self._question(key)
        assert answers, f'{question.key}: no answer'
        assert question.is_collection or len(answers) == 1, f'{question.key} takes one answer'
        place = self._place(key, within)
        set_collection = question.parent.is_collection
        stored = []
        for answer in answers:
            fields = self._fields(question, answer)
            if question.widget == 'checkbox':
                # RDMO's checkbox stores each option at its position in the option list
                index = question.options.index(fields['option'])
            elif question.is_collection:
                index = self._next_collection_index(question, place)
            else:
                index = 0
            # A question has one answer in one place: the interview changes it (e.g. one MaRDMO filled in)
            existing = Value.objects.filter(project=self.doc.project, snapshot=None,
                                            attribute__uri=DOMAIN + question.attribute,
                                            collection_index=index, **place).first()
            if existing is not None:
                stored.append(self.doc._update(existing, **fields))
            else:
                stored.append(self.doc._store(question.attribute, place['set_prefix'], place['set_index'], index,
                                              set_collection, **fields))
            if isinstance(answer, Typed):
                answer.id = stored[-1].external_id
        return stored

    def change(self, key, text, within=(), collection_index=0):
        '''Change the text of an answer (e.g. one MaRDMO filled in), as the user edits it.'''
        value = Value.objects.get(project=self.doc.project, snapshot=None,
                                  attribute__uri=f'{DOMAIN}{self.section}/{key}',
                                  collection_index=collection_index, **self._place(key, within))
        return self.doc._update(value, text=text, option=value.option.uri if value.option else None,
                                external_id=value.external_id)

    def references(self):
        '''The option keys of this page's references (``reference`` answers).'''
        return [uri.rsplit('/options/', 1)[-1] for uri in Value.objects.filter(
            project=self.doc.project, snapshot=None, attribute__uri=f'{DOMAIN}{self.section}/reference',
            **self._place('reference')).exclude(option=None).values_list('option__uri', flat=True)]

    def texts(self, key, within=()):
        '''The texts of the answers to *key* of this page.'''
        return list(Value.objects.filter(project=self.doc.project, snapshot=None,
                                         attribute__uri=f'{DOMAIN}{self.section}/{key}', **self._place(key, within))
                    .order_by('collection_index').values_list('text', flat=True))

    def select(self, key, item, within=()):
        return self.answer(key, item, within=within)[0]

    def block(self, questionset, answers, within=()):
        '''A new block of the question set *questionset* (the end of its key) with *answers* ``{question key: answer(s)}``.

        Returns the block's index, for the questions and blocks inside it (``within``).
        '''
        element = self._questionset(questionset)
        parent = self._indexes(element, list(within) + [0])[:-1]
        prefix = '|'.join(map(str, parent))
        attributes = [question.attribute for question in element.walk() if question.kind == 'question']
        used = Value.objects.filter(project=self.doc.project, snapshot=None, set_prefix=prefix,
                                    attribute__uri__in=[DOMAIN + attribute for attribute in attributes])
        index = max(used.values_list('set_index', flat=True), default=-1) + 1
        for key, value in answers.items():
            values = value if isinstance(value, list) else [value]
            self.answer(key, *values, within=list(within) + [index])
        return index

    def blocks(self, questionset, within=()):
        '''The indexes of the blocks of the question set *questionset* this page has.'''
        element = self._questionset(questionset)
        prefix = '|'.join(map(str, self._indexes(element, list(within) + [0])[:-1]))
        attributes = [DOMAIN + question.attribute for question in element.walk() if question.kind == 'question']
        return sorted(set(Value.objects.filter(project=self.doc.project, snapshot=None, set_prefix=prefix,
                                               attribute__uri__in=attributes).values_list('set_index', flat=True)))

    def _fields(self, question, answer):
        '''The text, option and external ID of *answer* to *question*.'''
        if question.providers:
            return self._selection(question, answer)
        if question.options:
            key, text = answer if isinstance(answer, tuple) else (answer, '')
            option = self._option(question, key)
            needs = self.doc.catalog.inputs.get(option)
            assert not text or needs, f'{question.key}: the option {option} takes no text'
            return {'option': option, 'text': text}
        assert isinstance(answer, str), f'{question.key}: a text, not {answer!r}'
        return {'text': answer}

    def _option(self, question, key):
        found = [option for option in question.options if option == key or option.endswith('/' + key)]
        assert len(found) == 1, f'{question.key}: {len(found)} options match {key!r} of {question.options}'
        return found[0]

    def _selection(self, question, item):
        '''Select *item* from the options the question's provider offers, as the user would.'''
        if isinstance(item, New):
            search, wanted = item.label, (NOT_FOUND, NEW_ITEM)
        elif isinstance(item, Typed):
            search, wanted = item.label, (NOT_FOUND, item.label)
        elif isinstance(item, Tab):
            search, wanted = item.label, (item.id, None)
        else:
            search, wanted = item.search or item.label, (item.id, None)
        options = self.doc.options(question, search)
        found = [option for option in options
                 if option['id'] == wanted[0] and (wanted[1] is None or option['text'] == wanted[1])]
        assert found, (f'{question.key}: {item!r} is not offered when searching {search!r}; '
                       f'offered: {[(option["id"], option["text"]) for option in options][:12]}')
        return {'text': found[0]['text'], 'external_id': found[0]['id']}
