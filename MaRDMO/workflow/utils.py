'''Utility functions for extracting and normalising workflow-related data.

Provides helpers that read structured answers from the RDMO questionnaire and
derive derived values (data-set sizes, references, archive URLs) needed by
the workflow worker and handler layers.

Provides:

- ``get_size``             — extract the data-set size value from answer options
- ``get_option_text_pair`` — resolve an option label and paired text value from a SPARQL result
'''


def get_size(data, options):
    '''Extract the size unit and value from a data-set answer dict.

    Resolves the unit from either ``size_unit`` (RDMO option URI) or falls
    back to ``items`` when a record count is given.

    Args:
        data:    Answer sub-dict for the data-set size questions.
        options: Options dict mapping RDMO option URIs to string values.

    Returns:
        ``[unit, value]`` if both are present; ``[]`` otherwise.
    '''
    size_unit = data.get('size_unit', {}).get('value', '')
    size_value = data.get('size_value', {}).get('value', '')
    size_record = data.get('size_record', {}).get('value', '')

    unit = options.get(size_unit) if size_unit else (options['items'] if size_record else '')
    value = size_value or size_record

    return [unit, value] if unit and value else []


def get_option_text_pair(data, options, opt_key, *value_keys):
    '''Resolve an option label and the first available text value from a SPARQL result dict.

    Args:
        data:       SPARQL result row dict with nested ``{"value": ...}`` entries.
        options:    Options dict mapping RDMO option URIs to string values.
        opt_key: Key whose resolved option URI is looked up in *options*.
        *value_keys: One or more keys tried left-to-right for the text value;
                    the first non-empty one is used.

    Returns:
        ``[option_label, text]`` if the option is set; ``[]`` otherwise.
    '''
    option_label = options[data[opt_key]['value']] if data.get(opt_key, {}).get('value') else ''
    text = next(
        (data.get(k, {}).get('value', '') for k in value_keys if data.get(k, {}).get('value')),
        ''
    )
    return [option_label, text] if option_label else []
