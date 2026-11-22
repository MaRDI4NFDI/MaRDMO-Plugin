'''Looking up ontology properties and reference answers.'''


def find_reference(references, option_uri):
    '''Return the ``[option_uri, text]`` entry for *option_uri* in a reference dict, or ``None``.

    Reference and documentation answers are stored as
    ``{collection_index: [option_uri, text]}``.  The collection index is the
    option's position in the questionnaire, so entries are looked up by
    option rather than by position.
    '''
    for entry in (references or {}).values():
        if entry and entry[0] == option_uri:
            return entry
    return None


class PropertyRegistry:
    """Registry class to look up MathModDB / MathAlgoDB properties by key, label, or URL.

    Each entry in *properties* must be a dict with ``key``, ``label``, and
    ``url`` fields.  The registry builds three internal indices so that any
    of the three identifiers can be used for O(1) lookups via :meth:`get`.
    """
    def __init__(self, properties):
        '''Build lookup indices from *properties*.

        Args:
            properties: Iterable of dicts, each containing ``key``,
                        ``label``, and ``url`` string fields.
        '''
        self._by_key = {}
        self._by_label = {}
        self._by_url = {}

        for item in properties:
            entry = {
                "key":   item["key"],
                "label": item["label"],
                "url":   item["url"],
            }
            self._by_key[item["key"]]     = entry
            self._by_label[item["label"]] = entry
            self._by_url[item["url"]]     = entry

    def get(self, *, key=None, label=None, url=None) -> dict | None:
        """Look up a property by any field. Pass exactly one keyword arg."""
        if key is not None:
            return self._by_key.get(key)
        if label is not None:
            return self._by_label.get(label)
        if url is not None:
            return self._by_url.get(url)
        raise ValueError("Provide exactly one of: key, label, url")
