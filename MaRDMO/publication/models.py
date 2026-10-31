'''Dataclasses that represent bibliographic entities in the Publication catalog.

Each class maps to one entity type retrieved from external sources (Crossref,
ZbMATH, Wikidata, ORCID) during publication metadata collection. Instances
are populated from API responses and carry all fields needed to fill
questionnaire answers and produce export entries.

Provides:

- :class:`Author`      — person entity with ORCID, ZbMATH, and Wikidata identifiers
- :class:`Journal`     — publication venue with ISSN and portal identifiers
- :class:`Publication` — central bibliographic record linking authors and journal
'''

from dataclasses import dataclass, field
from typing import Optional, ClassVar

from ..getters import get_items, get_options
from ..helpers import date_format, split_value


def _first(values):
    '''Return the first element of a list (``None`` if empty); other values unchanged.

    External APIs deliver some fields sometimes as list, sometimes as plain
    value, and sometimes as empty list.
    '''
    if isinstance(values, list):
        return values[0] if values else None
    return values
from ..models import Relatant, RelatantWithClass

@dataclass
class Author:
    '''Data Class For Authors'''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]
    orcid_id: Optional[str]
    zbmath_id: Optional[str]
    wikidata_id: Optional[str]

    @classmethod
    def from_query(cls, raw: str) -> 'Author':
        '''Parse a ``<|>``-delimited SPARQL result string into an Author instance.

        Args:
            raw: Space-and-pipe-delimited string with six fields:
                 identifier, label, description, orcid_id, zbmath_id, wikidata_id.

        Returns:
            Author instance populated from the parsed fields.
        '''
        identifier, label, description, orcid_id, zbmath_id, wikidata_id = raw.split(" <|> ")

        if label and not identifier:
            identifier = 'no author found'

        if not description:
            if orcid_id:
                description = f'scientist (ORCID iD {orcid_id})'
            elif zbmath_id:
                description = f'scientist (zbMath ID {zbmath_id})'
            else:
                description = 'scientist'

        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

    @classmethod
    def from_crossref(cls, raw: str) -> 'Author':
        '''Build an Author instance from a single Crossref contributor dict.

        Args:
            raw: Dict-like object from the Crossref ``author`` list with optional
                 keys ``given``, ``family``, and ``ORCID``.

        Returns:
            Author instance; ``id`` is ``'no author found'`` when a name is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if raw.get('given') and raw.get('family'):
            label = f"{raw['given']} {raw['family']}"

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no author found'

        # Get ORCID ID
        orcid_id = None
        if raw.get('ORCID'):
            orcid_id = raw.get('ORCID').split('/')[-1]

        # Get ZBMath ID
        zbmath_id = None

        # Get Wikidata ID
        wikidata_id = None

        # Get Description
        description = None
        if label:
            if orcid_id:
                description = f'scientist (ORCID iD {orcid_id})'
            else:
                description = 'scientist'


        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

    @classmethod
    def from_datacite(cls, raw: str) -> 'Author':
        '''Build an Author instance from a single DataCite creator dict.

        Args:
            raw: Dict-like object from the DataCite ``creators`` list with optional
                 keys ``givenName``, ``familyName``, and ``nameIdentifiers``.

        Returns:
            Author instance; ``id`` is ``'no author found'`` when a name is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if raw.get('givenName') and raw.get('familyName'):
            label = f"{raw['givenName']} {raw['familyName']}"

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no author found'

        # Get ORCID ID
        orcid_id = None
        for name_identifier in raw.get('nameIdentifiers', []):
            if name_identifier.get('nameIdentifierScheme') == 'ORCID':
                orcid_uri = name_identifier.get('nameIdentifier', '')
                orcid_id = orcid_uri.split('/')[-1]
                break

        # Get ZBMath ID
        zbmath_id = None

        # Get Wikidata ID
        wikidata_id = None

        # Get Description
        description = None
        if label:
            if orcid_id:
                description = f'scientist (ORCID iD {orcid_id})'
            else:
                description = 'scientist'

        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

    @classmethod
    def from_doi(cls, raw: str) -> 'Author':
        '''Build an Author instance from a single DOI API author dict.

        Args:
            raw: Dict-like object from the DOI API ``author`` list with optional
                 keys ``given``, ``family``, and ``ORCID``.

        Returns:
            Author instance; ``id`` is ``'no author found'`` when a name is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if raw.get('given') and raw.get('family'):
            label = f"{raw['given']} {raw['family']}"

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no author found'

        # Get ORCID ID
        orcid_id = None
        if raw.get('ORCID'):
            orcid_id = raw.get('ORCID').split('/')[-1]

        # Get ZBMath ID
        zbmath_id = None

        # Get Wikidata ID
        wikidata_id = None

        # Get Description
        description = None
        if label:
            if orcid_id:
                description = f'scientist (ORCID iD {orcid_id})'
            else:
                description = 'scientist'

        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

    @classmethod
    def from_zbmath(cls, raw: str) -> 'Author':
        '''Build an Author instance from a single zbMath author dict.

        Args:
            raw: Dict-like object from the zbMath ``contributors.authors`` list
                 with optional keys ``name`` and ``codes``.

        Returns:
            Author instance; ``id`` is ``'no author found'`` when a name is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if raw.get('name'):
            label = " ".join(reversed(raw['name'].split(", ")))

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no author found'

        # Get ORCID ID
        orcid_id = None

        # Get zbMath ID
        zbmath_id = None
        if raw.get('codes'):
            zbmath_id = raw['codes'][0]

        # Get Wikidata ID
        wikidata_id = None

        # Get Description
        description = None
        if label:
            if zbmath_id:
                description = f'scientist (zbMath ID {zbmath_id})'
            else:
                description = 'scientist'

        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

    @classmethod
    def from_orcid(cls, raw: str) -> 'Author':
        '''Build an Author instance from an ORCID expanded-search record.

        Args:
            raw: Dict-like entry of the ``expanded-result`` list with
                 ``orcid-id``, ``given-names``, and ``family-names``.

        Returns:
            Author instance; ``id`` is ``'no author found'`` when a name is present
            but no MaRDI Portal entry exists yet.
        '''

        label = None
        zbmath_id = wikidata_id = None

        # Get Name & ORCID ID
        given = raw.get('given-names')
        family = raw.get('family-names')
        orcid_id = raw.get('orcid-id')
        if given and family:
            label = f"{given} {family}"

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no author found'

        # Get Description
        description = None
        if label:
            if orcid_id:
                description = f'scientist (ORCID iD {orcid_id})'
            else:
                description = 'scientist'

        return cls(
            id = identifier,
            label = label,
            description = description,
            orcid_id = orcid_id,
            zbmath_id = zbmath_id,
            wikidata_id = wikidata_id
        )

@dataclass
class Journal:
    '''Data Class For Journals'''
    id: str
    issn: str
    label: str
    description: str

    @classmethod
    def from_query(cls, raw: str) -> 'Journal':
        '''Parse a ``<|>``-delimited SPARQL result string into a Journal instance.

        Args:
            raw: Space-and-pipe-delimited string with three or four fields:
                 identifier, label, description, and optionally issn.

        Returns:
            Journal instance populated from the parsed fields.
        '''
        raw_splitted = raw.split(" <|> ")

        identifier = raw_splitted[0]
        label = raw_splitted[1]
        description = raw_splitted[2]
        if len(raw_splitted) == 4:
            issn = raw_splitted[3]
        else:
            issn = None

        if not description:
            if issn:
                description = f'scientific journal (ISSN {issn})'
            else:
                description = 'scientific journal'

        return cls(
            id = identifier,
            issn = issn,
            label = label,
            description = description
        )

    @classmethod
    def from_crossref(cls, ids: list, item: list) -> 'Journal':
        '''Build a Journal instance from Crossref ISSN and title data.

        Args:
            ids:  List of ISSN strings from the Crossref response (may be empty).
            item: List of container-title strings from the Crossref response (may be empty).

        Returns:
            Journal instance; ``id`` is ``'no journal found'`` when a title is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if item:
            label = item[0]

        # Get ISSN
        issn = None
        if ids:
            issn = ids[0]

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no journal found'

        # Get Description
        description = None
        if label:
            if issn:
                description = f'scientific journal (ISSN {issn})'
            else:
                description = 'scientific journal'

        return cls(
            id = identifier,
            issn = issn,
            label = label,
            description = description,
        )

    @classmethod
    def from_datacite(cls, ids: list, item: list) -> 'Journal':
        '''Build a Journal instance from DataCite related-identifier and related-item data.

        Args:
            ids:  List of relatedIdentifier dicts from the DataCite response (may be empty).
            item: List of relatedItem dicts from the DataCite response (may be empty).

        Returns:
            Journal instance; ``id`` is ``'no journal found'`` when a title is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if item:
            label = (item[0].get('titles') or [{}])[0].get('title')

        # Get ISSN
        issn = None
        if ids:
            if ids[0].get('relatedIdentifierType') == 'ISSN':
                issn = ids[0].get('relatedIdentifier')

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no journal found'

        # Get Description
        description = None
        if label:
            if issn:
                description = f'scientific journal (ISSN {issn})'
            else:
                description = 'scientific journal'

        return cls(
            id = identifier,
            issn = issn,
            label = label,
            description = description,
        )

    @classmethod
    def from_doi(cls, ids: list, item: str) -> 'Journal':
        '''Build a Journal instance from DOI API ISSN and container-title data.

        Args:
            ids:  List of ISSN strings from the DOI API response (may be empty).
            item: Container-title string from the DOI API response (may be None).

        Returns:
            Journal instance; ``id`` is ``'no journal found'`` when a title is present
            but no MaRDI Portal entry exists yet.
        '''
        # Get Label
        label = None
        if item:
            label = item

        # Get ISSN
        issn = None
        if ids:
            issn = ids[0]

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no journal found'

        # Get Description
        description = None
        if label:
            if issn:
                description = f'scientific journal (ISSN {issn})'
            else:
                description = 'scientific journal'

        return cls(
            id = identifier,
            issn = issn,
            label = label,
            description = description,
        )

    @classmethod
    def from_zbmath(cls, raw: dict) -> 'Journal':
        '''Build a Journal instance from a zbMath source dict.

        Args:
            raw: The ``source`` dict from a zbMath result entry, expected to contain
                 an optional ``series`` list with ``title`` and ``issn`` entries.

        Returns:
            Journal instance; ``id`` is ``'no journal found'`` when a title is present
            but no MaRDI Portal entry exists yet.
        '''
        series = (raw.get('series') or [{}])[0]

        # Get Label
        label = None
        if series.get('title'):
            label = series['title']

        # Get ISSN
        issn = None
        if (series.get('issn') or [{}])[0].get('number'):
            issn = series['issn'][0]['number']

        # Get MaRDI Portal ID
        identifier = None
        if label:
            identifier = 'no journal found'

        # Get Description
        description = None
        if label:
            if issn:
                description = f'scientific journal (ISSN {issn})'
            else:
                description = 'scientific journal'

        return cls(
            id = identifier,
            issn = issn,
            label = label,
            description = description,
        )


@dataclass
class Publication:
    '''Data Class For Publications'''
    id: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    entrytype: Optional[str] = None
    title: Optional[str] = None
    date: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    page: Optional[str] = None
    reference: Optional[str] = None
    journal: list[Journal] = field(default_factory=list)
    authors: list[Author] = field(default_factory=list)
    language: list[Relatant] = field(default_factory=list)
    applies: list[RelatantWithClass] = field(default_factory=list)
    analyzes: list[RelatantWithClass] = field(default_factory=list)
    documents: list[RelatantWithClass] = field(default_factory=list)
    invents: list[RelatantWithClass] = field(default_factory=list)
    studies: list[RelatantWithClass] = field(default_factory=list)
    surveys: list[RelatantWithClass] = field(default_factory=list)
    uses: list[RelatantWithClass] = field(default_factory=list)

    options: ClassVar[Optional[dict]] = None

    @classmethod
    def get_options(cls) -> dict:
        '''Return the cached option-label mapping used by all class generators.

        Returns:
            Dict mapping option keys (e.g. ``'DOI'``) to their display labels,
            loaded once and cached as a class variable.
        '''
        if cls.options is None:
            cls.options = get_options()
        return cls.options

    @classmethod
    def from_query(cls, raw_data: dict) -> 'Publication':
        '''Build a Publication instance from a SPARQL query result list.

        Args:
            raw_data: List of SPARQL result row dicts; the first element is used.
                      Expected keys include ``id``, ``label``, ``description``,
                      ``entrytypelabel``, ``title``, ``date``, ``doi``,
                      ``journalInfo``, ``authorInfos``, and relation keys such as
                      ``applies``, ``analyzes``, ``documents``, etc.

        Returns:
            Publication instance populated from the SPARQL result.
        '''
        options = cls.get_options()
        items = get_items()

        data = raw_data[0]

        publication = {
            # Get ID
            'id': data.get('id', {}).get('value'),
            # Get Label
            'label': data.get('label', {}).get('value'),
            # Get Description
            'description': data.get('description', {}).get('value'),
            # Get Entrytype
            'entrytype': data.get('entrytypelabel', {}).get('value'),
            # Get Language
            'language': (
                [
                    Relatant.from_triple(
                        f"mardi:{items['english']}",
                        "English",
                        "West Germanic language"
                    )
                ]
                if data.get('languagelabel', {}).get('value', '').lower()
                    in {"en", "eng", "english"}
                else []
            ),
            # Get Title
            'title': data.get('title', {}).get('value'),
            # Get Date
            'date': data.get('date', {}).get('value', ''),
            # Get Volume
            'volume': data.get('volume', {}).get('value'),
            # Get Issue
            'issue': data.get('issue', {}).get('value'),
            # Get Page
            'page': data.get('page', {}).get('value'),
            # Get Reference
            'reference': {
                idx: [options['DOI'], data[prop]['value']]
                for idx, prop in enumerate(['doi'])
                if data.get(prop, {}).get('value')
            },
            # Get Journal
            'journal': 
                [
                    Journal.from_query(
                        data.get('journalInfo', {}).get('value')
                    )
                ]
                if 'journalInfo' in data else [],
            # Get Authors
            'authors': 
                [
                    Author.from_query(
                        author
                    )
                    for author in data.get('authorInfos', {}).get('value', '').split(" || ")
                    if author
                ]
                if 'authorInfos' in data else [],
            # Get Applies Relation(s)
            'applies': split_value(
                data = data,
                key = 'applies',
                transform = RelatantWithClass.from_query
            ),
            # Get Analyzes Relation(s)
            'analyzes': split_value(
                data = data,
                key = 'analyzes',
                transform = RelatantWithClass.from_query
            ),
            # Get Documents Relation(s)
            'documents': split_value(
                data = data,
                key = 'documents',
                transform = RelatantWithClass.from_query
            ),
            # Get Invents Relation(s)
            'invents': split_value(
                data = data,
                key = 'invents',
                transform = RelatantWithClass.from_query
            ),
            # Get Studies Relation(s)
            'studies': split_value(
                data = data,
                key = 'studies',
                transform = RelatantWithClass.from_query
            ),
            # Get Surveys Relation(s)
            'surveys': split_value(
                data = data,
                key = 'surveys',
                transform = RelatantWithClass.from_query
            ),
            # Get Uses Relation(s)
            'uses': split_value(
                data = data,
                key = 'uses',
                transform = RelatantWithClass.from_query
            ),
        }

        return cls(
            **publication
            )

    @classmethod
    def from_crossref(cls, raw_data: dict) -> 'Publication':
        '''Build a Publication instance from a Crossref API response.

        Args:
            raw_data: Response object whose ``.json()['message']`` contains
                      Crossref metadata fields such as ``title``, ``author``,
                      ``DOI``, ``ISSN``, ``volume``, ``issue``, ``page``,
                      ``published``, and ``container-title``.

        Returns:
            Publication instance populated from the Crossref metadata.
        '''
        options = cls.get_options()
        items = get_items()

        data = raw_data.json().get('message', {})

        publication = {
            # Get ID
            'id': None,
            # Get Label
            'label': _first(data.get('title')),
            # Get Description
            'description': 
                f'scientific article (doi: {data["DOI"]})'
                if data.get("DOI") else 'scientific article',
            # Get Entrytype
            'entrytype':
                'scholarly article'
                if data.get('type') == 'journal-article' else 'publication',
            # Get Language
            'language': (
                [
                    Relatant.from_triple(
                        f"mardi:{items['english']}",
                        "English",
                        "West Germanic language"
                    )
                ]
                if (data.get('language') or '').lower()
                    in {"en", "eng", "english"}
                else []
            ),
            # Get Title
            'title': _first(data.get('title')),
            # Get Date
            'date': date_format(
                _first((data.get('published') or {}).get('date-parts'))
            ),
            # Get Volume
            'volume': data.get('volume'),
            # Get Issue
            'issue': data.get('issue'),
            # Get Page
            'page': data.get('page'),
            # Get Reference
            'reference': {
                idx: [options['DOI'], data[prop]]
                for idx, prop in enumerate(['DOI'])
                if data.get(prop, {})
            },
            # Get Journal
            'journal':
                [
                    Journal.from_crossref(
                        data.get('ISSN', []),
                        data.get('container-title', [])
                    )
                ]
                if 'ISSN' in data or 'container-title' in data else [],
            # Get Authors
            'authors': 
                [
                    Author.from_crossref(
                        author
                    )
                    for author in data.get('author', [])
                    if author
                ]
                if 'author' in data else [],
        }

        return cls(
            **publication
        )

    @classmethod
    def from_datacite(cls, raw_data: dict) -> 'Publication':
        '''Build a Publication instance from a DataCite API response.

        Args:
            raw_data: Response object whose ``.json()['data']['attributes']`` contains
                      DataCite metadata fields such as ``titles``, ``creators``,
                      ``doi``, ``dates``, ``relatedItems``, and ``relatedIdentifiers``.

        Returns:
            Publication instance populated from the DataCite metadata.
        '''
        options = cls.get_options()
        items = get_items()

        data = raw_data.json().get('data', {}).get('attributes', {})

        publication = {
            # Get ID
            'id': None,
            # Get Label
            'label': (data.get('titles') or [{}])[0].get('title'),
            # Get Description
            'description': 
                f'scientific article (doi: {data["doi"]})'
                if data.get("doi") else 'scientific article',
            # Get Entrytype
            'entrytype':
                'scholarly article'
                if data.get('types', {}).get('bibtex') == 'article' else 'publication',
            # Get Language
            'language': (
                [
                    Relatant.from_triple(
                        f"mardi:{items['english']}",
                        "English",
                        "West Germanic language"
                    )
                ]
                if (data.get('language') or '').lower()
                    in {"en", "eng", "english"}
                else []
            ),
            # Get Title
            'title': (data.get('titles') or [{}])[0].get('title'),
            # Get Date
            'date': 
                next(
                    (
                        # A range ("2019/2020") counts from its start
                        date_format(date_part['date'].split('/')[0].split('-'))
                        for date_part in data.get('dates', [])
                        if date_part.get('dateType') == 'Issued' and date_part.get('date')
                    ),
                    None,
                ),
            # Get Volume
            'volume': (data.get('relatedItems') or [{}])[0].get('volume'),
            # Get Issue
            'issue': (data.get('relatedItems') or [{}])[0].get('issue'),
            # Get Page
            'page':
                (
                    f"{data['relatedItems'][0].get('firstPage', '')}-"
                    f"{data['relatedItems'][0].get('lastPage', '')}"
                )
                if data.get('relatedItems') else None,
            # Get Reference
            'reference': {
                idx: [options['DOI'], data[prop]]
                for idx, prop in enumerate(['doi'])
                if data.get(prop, {})
            },
            # Get Journal
            'journal': 
                [
                    Journal.from_datacite(
                        data.get('relatedIdentifiers') or [{}],
                        data.get('relatedItems') or [{}],
                    )
                ]
                if 'relatedIdentifiers' in data or 'relatedItems' in data else [],
            # Get Authors
            'authors':
                [
                    Author.from_datacite(author)
                    for author in data.get('creators', [])
                    if author
                ]
                if 'creators' in data else [],
        }

        return cls(
            **publication
        )

    @classmethod
    def from_doi(cls, raw_data: dict) -> 'Publication':
        '''Build a Publication instance from a DOI resolution API response.

        Args:
            raw_data: Response object whose ``.json()`` contains DOI metadata
                      fields such as ``title``, ``author``, ``DOI``, ``ISSN``,
                      ``volume``, ``issue``, ``page``, ``published``, and
                      ``container-title``.

        Returns:
            Publication instance populated from the DOI metadata.
        '''
        options = cls.get_options()
        items = get_items()

        data = raw_data.json()

        publication = {
            # Get ID
            'id': None,
            # Get Label
            'label': data.get('title'),
            # Get Description
            'description': 
                f'scientific article (doi: {data["DOI"]})'
                if data.get("DOI") else 'scientific article',
            # Get Entrytype
            'entrytype': (
                'scholarly article'
                if data.get('type') in ('journal-article', 'article-journal')
                else 'publication'
            ),
            # Get Language
            'language': (
                [
                    Relatant.from_triple(
                        f"mardi:{items['english']}",
                        "English",
                        "West Germanic language"
                    )
                ]
                if (data.get('language') or '').lower()
                    in {"en", "eng", "english"}
                else []
            ),
            # Get Title
            'title': data.get('title'),
            # Get Date ('issued' is the CSL standard, 'published' Crossref-specific)
            'date': date_format(
                _first((data.get('published') or data.get('issued') or {}).get('date-parts'))
            ),
            # Get Volume
            'volume': data.get('volume'),
            # Get Issue
            'issue': data.get('issue'),
            # Get Page
            'page': data.get('page'),
            # Get Reference
            'reference': {
                idx: [options['DOI'], data[prop]]
                for idx, prop in enumerate(['DOI'])
                if data.get(prop, {})
            },
            # Get Journal
            'journal':
                [
                    Journal.from_doi(
                        data.get('ISSN', []),
                        data.get('container-title', [])
                    )
                ]
                if 'ISSN' in data or 'container-title' in data else [],
            # Get Authors
            'authors':
                [
                    Author.from_doi(author)
                    for author in data.get('author', [])
                    if author
                ]
                if 'author' in data else [],
        }

        return cls(
            **publication
        )

    @classmethod
    def from_zbmath(cls, raw_data: dict) -> 'Publication':
        '''Build a Publication instance from a zbMath API response.

        Args:
            raw_data: Response object whose ``.json()['result'][0]`` contains
                      zbMath metadata fields such as ``title``, ``year``,
                      ``document_type``, ``language``, ``source``, ``links``,
                      and ``contributors``.

        Returns:
            Publication instance populated from the zbMath metadata.
        '''
        options = cls.get_options()
        items = get_items()

        data = _first(raw_data.json().get('result')) or {}

        publication = {
            # Get ID
            'id': None,
            # Get Label
            'label': (data.get('title') or {}).get('title'),
            # Get Description
            'description': (
                f"scientific article (doi: {doi})"
                if (doi := next(
                    (
                        link.get("identifier")
                        for link in data.get("links", [])
                        if link.get("type") == "doi"
                    ),
                    None,
                ))
                else "scientific article"
            ),
            # Get Entrytype
            'entrytype': (
                'scholarly article'
                if data.get('document_type', {}).get('description') == 'journal article'
                else 'publication'
            ),
            # Get Language
            'language':(
                [
                    Relatant.from_triple(
                        f"mardi:{items['english']}",
                        "English",
                        "West Germanic language"
                    )
                ]
                if any(
                    code.lower() in {"en", "eng", "english"}
                    for code in (data.get("language", {}).get("languages") or [""])
                )
                else []
            ),
            # Get Date
            'date': date_format([data.get('year')]),
            # Get Title
            'title': (data.get('title') or {}).get('title'),
            # Get Volume
            'volume': (_first((data.get('source') or {}).get('series')) or {}).get('volume'),
            # Get Issue
            'issue': (_first((data.get('source') or {}).get('series')) or {}).get('issue'),
            # Get Page
            'page': data.get('source', {}).get('page'),
            # Get Reference
            'reference': (
                {0: [options['DOI'], doi]}
                if (
                    doi := next(
                    (
                        link.get('identifier')
                        for link in data.get('links', [])
                        if link.get('type') == 'doi'
                    ),
                    None
                    )
                )
                else {}
            ),
            # Get Journal
            'journal': 
                [
                    Journal.from_zbmath(
                        data.get('source', {})
                    )
                ]
                if 'source' in data else [],
            # Get Authors
            'authors':
                [
                    Author.from_zbmath(author)
                    for author in data.get('contributors', {}).get('authors', [])
                    if author
                ]
                if 'contributors' in data else [],
        }

        return cls(
            **publication
        )
