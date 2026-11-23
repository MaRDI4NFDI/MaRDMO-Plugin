'''Filling in an item selected in the interview from the MaRDI Portal or Wikidata (#198).

A handler (:class:`~MaRDMO.components.fill.base.BaseInformation` and the
catalogs' handlers) fetches the item's statements and writes them into the
questionnaire (:mod:`~MaRDMO.components.fill.adders`); the relations of
several catalogs share :mod:`~MaRDMO.components.fill.relations`.
'''
