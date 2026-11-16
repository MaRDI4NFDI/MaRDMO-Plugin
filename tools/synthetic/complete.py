'''What the user adds to pages MaRDMO filled or added, before the checks pass.

The checks ask every page for its required answers, also the pages MaRDMO
filled from the MaRDI Portal or Wikidata (a selected item, the relations of
a selected workflow) and the pages of items typed into a relation.  These
functions answer what is still missing, as the user does in the interview;
answers that are there stay.  They do nothing once MaRDMO asks less of
such pages.
'''


def descriptions(doc, *sections):
    for section in sections:
        for page in doc.tabs(section):
            if not page.description:
                page.answer('description', f'{page.label} (completed for the MaRDMO tests)')


def references(doc, *sections, option='described-at-url', text='https://portal.mardi4nfdi.de/'):
    '''A reference for every page of *sections* without one (software, benchmarks).'''
    for section in sections:
        for page in doc.tabs(section):
            if not page.answered('reference'):
                page.answer('reference', (option, text))


def publication_dois(doc):
    '''Remove the leading "/" of DOIs some portal publications have (as imported into the portal).'''
    for page in doc.tabs('publication'):
        for index, doi in enumerate(page.texts('reference')):
            if doi.startswith('/'):
                page.change('reference', doi.lstrip('/'), collection_index=index)


def missing(page, answers, within=()):
    '''Answer each ``{question: answer}`` of *answers* the page has no answer to.'''
    for key, answer in answers.items():
        if not page.answered(key, within=within):
            values = answer if isinstance(answer, list) else [answer]
            page.answer(key, *values, within=within)
