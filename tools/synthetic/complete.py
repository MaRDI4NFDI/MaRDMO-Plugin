'''What the user adds to pages MaRDMO filled or added, before the checks pass.

The export creates the items of the user and of Wikidata, so the checks ask
their pages for every required answer: also the pages MaRDMO filled from
Wikidata (with name and description only, #166) and the pages of items typed
into a relation.  These functions answer what is still missing there, as the
user does in the interview; answers that are there stay.  Pages of MaRDI
Portal items are left as MaRDMO filled them: what they lack is a hint, it
does not prevent the export (#167).
'''


def created(page):
    '''Whether the export creates the item of *page* (not a MaRDI Portal item).'''
    return not (page.id or '').startswith('mardi:')


def descriptions(doc, *sections):
    for section in sections:
        for page in doc.tabs(section):
            if created(page) and not page.description:
                page.answer('description', f'{page.label} (completed for the MaRDMO tests)')


def references(doc, *sections, option='described-at-url', text='https://portal.mardi4nfdi.de/'):
    '''A reference for every page of *sections* without one (software, benchmarks).'''
    for section in sections:
        for page in doc.tabs(section):
            if created(page) and not page.answered('reference'):
                page.answer('reference', (option, text))


def publication_dois(doc):
    '''Remove the leading "/" of DOIs some Wikidata publications have (portal publications keep theirs, #167).'''
    for page in filter(created, doc.tabs('publication')):
        for index, doi in enumerate(page.texts('reference')):
            if doi.startswith('/'):
                page.change('reference', doi.lstrip('/'), collection_index=index)


def missing(page, answers, within=()):
    '''Answer each ``{question: answer}`` of *answers* the page has no answer to (pages of created items only).'''
    if not created(page):
        return
    for key, answer in answers.items():
        if not page.answered(key, within=within):
            values = answer if isinstance(answer, list) else [answer]
            page.answer(key, *values, within=within)
