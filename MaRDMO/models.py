'''Base dataclasses shared across all MaRDMO documentation sub-packages.

Provides:

- :class:`Relatant` — a lightweight ``(id, label, description)`` triple used
  to represent any referenced entity (model, software, publication, …).
- :class:`RelatantWithClass` — extends :class:`Relatant` with an
  ``item_class`` field for entities whose Wikibase class matters (e.g.
  quantities that are either ``Quantity`` or ``QuantityKind``).

Both classes expose ``from_query``, ``from_triple``, and (for
:class:`Relatant`) ``from_msc`` class methods for constructing instances
from different data sources.

- :class:`RelatantWithQualifier` — entity triple extended with a qualifier
  value and an optional free-form ``other`` field (e.g. parameters).
- :class:`Algorithm` — algorithm entity with relation lists populated from
  SPARQL results (problems solved, implementations, intra-class relations).

'''

from dataclasses import dataclass, field
from typing import Optional

from .constants import software_reference_ids
from .getters import get_options
from .helpers import split_value

@dataclass
class Relatant:
    '''Data Class For Relatant Items'''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]

    @classmethod
    def from_query(cls, raw: str) -> 'Relatant':
        '''Construct a :class:`Relatant` from a pipe-delimited query string.

        Args:
            raw: String in the format ``"id || label || description"``.

        Returns:
            New :class:`Relatant` instance.
        '''
        identifier, label, description = raw.split(" || ")
        return cls(
            id = identifier,
            label = label,
            description = description,
        )

    @classmethod
    def from_triple(cls, identifier: str, label: str, description: str) -> 'Relatant':
        '''Construct a :class:`Relatant` from explicit id, label, description arguments.

        Args:
            identifier:  External ID string (e.g. ``"mardi:Q42"``).
            label:       Human-readable label.
            description: Short description.

        Returns:
            New :class:`Relatant` instance.
        '''
        return cls(
            id = identifier,
            label = label,
            description = description,
        )

@dataclass
class RelatantWithClass:
    '''Data Class For Relatant Items With Class'''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]
    item_class: Optional[str]

    @classmethod
    def from_query(cls, raw: str) -> 'RelatantWithClass':
        '''Parse a ``||``-delimited SPARQL result string into a RelatantWithClass instance.

        Args:
            raw: String with three or four ``" || "``-separated fields:
                 identifier, label, description, and optionally item_class.

        Returns:
            New :class:`RelatantWithClass` instance; ``item_class`` is ``None``
            when only three fields are present.
        '''
        raw_split = raw.split(" || ")
        if len(raw_split) == 3:
            item_class = None
        else:
            item_class = raw_split[3]
        return cls(
            id = raw_split[0],
            label = raw_split[1],
            description = raw_split[2],
            item_class = item_class
        )

@dataclass
class RelatantWithQualifier:
    '''Entity triple extended with a qualifier value.

    The ``qualifier`` field holds the ID of a qualifier entity (e.g. a platform
    or formulation type).
    '''
    id: Optional[str]
    label: Optional[str]
    description: Optional[str]
    qualifier: Optional[str]

    @classmethod
    def from_query(cls, raw: str) -> 'RelatantWithQualifier':
        '''Parse a delimited SPARQL result string into a RelatantWithQualifier instance.

        Args:
            raw: Delimited string with four ``||``-separated fields (identifier,
                 label, description, qualifier).

        Returns:
            RelatantWithQualifier instance populated from the parsed fields.
        '''
        identifier, label, description, qualifier = raw.split(" || ", 3)
        return cls(
            id = identifier,
            label = label,
            description = description,
            qualifier = qualifier,
        )

@dataclass
class Algorithm:
    '''Algorithm entity with relation lists populated from SPARQL results.'''
    component_of: list[Relatant] = field(default_factory=list)
    has_component: list[Relatant] = field(default_factory=list)
    subclass_of: list[Relatant] = field(default_factory=list)
    has_subclass: list[Relatant] = field(default_factory=list)
    related_to: list[Relatant] = field(default_factory=list)
    solves: list[Relatant] = field(default_factory=list)
    implemented_by: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query(cls, raw_data: dict) -> 'Algorithm':
        '''Generate Class Item From Query (single-item, backward-compatible).'''
        return cls.from_query_single(raw_data[0])

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, Algorithm]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

    @classmethod
    def from_query_single(cls, data: dict) -> 'Algorithm':
        '''Parse one SPARQL result row into an Algorithm instance.'''
        return cls(
            solves=split_value(data=data, key='solved_by', transform=Relatant.from_query),
            implemented_by=split_value(data=data, key='implementation_by', transform=Relatant.from_query),
            has_component=split_value(data=data, key='has_parts', transform=Relatant.from_query),
            component_of=split_value(data=data, key='part_of', transform=Relatant.from_query),
            has_subclass=split_value(data=data, key='has_subclass', transform=Relatant.from_query),
            subclass_of=split_value(data=data, key='subclass_of', transform=Relatant.from_query),
            related_to=split_value(data=data, key='similar_to', transform=Relatant.from_query),
            publications=split_value(data=data, key='publication', transform=Relatant.from_query),
        )


@dataclass
class Software:
    '''Software entity with references and relations populated from SPARQL results.'''
    reference: dict[int, list[str]] = field(default_factory=dict)
    programmed_in: list[Relatant] = field(default_factory=list)
    depends_on_software: list[Relatant] = field(default_factory=list)
    tested_by: list[Relatant] = field(default_factory=list)
    publications: list[Relatant] = field(default_factory=list)

    @classmethod
    def from_query_batch(cls, raw_data: list) -> 'dict[str, Software]':
        '''Parse a batch SPARQL result into {external_id: instance} dict.'''
        return {
            row['qid']['value']: cls.from_query_single(row)
            for row in raw_data
            if row.get('qid', {}).get('value')
        }

    @classmethod
    def from_query_single(cls, data: dict) -> 'Software':
        '''Parse one SPARQL result row into a Software instance.'''
        options = get_options()
        return cls(
            reference={
                idx: [options[prop], data[prop]['value']]
                for idx, prop in enumerate(software_reference_ids)
                if data.get(prop, {}).get('value')
            },
            programmed_in=split_value(
                data=data, key='programmed_in', transform=Relatant.from_query
            ),
            depends_on_software=split_value(
                data=data, key='depends_on_software', transform=Relatant.from_query
            ),
            tested_by=split_value(
                data=data, key='tested_by', transform=Relatant.from_query
            ),
            publications=split_value(
                data=data, key='publication', transform=Relatant.from_query
            ),
        )
