'''What went wrong when the MaRDI Portal rejected a request of the export, in words for the user.

:func:`explain_error` names the rejected value and its item,
:func:`handle_policy_violation` turns a refused item (HTTP 422) into
:class:`DuplicateOnPortal` or an error, :func:`extract_error_message`
reads the portal's own message.
'''
import re

from django.utils.translation import gettext_lazy as _

from ..core.config import get_properties

# Field path in a Wikibase REST API 400 error, e.g.
# "Invalid value at '/item/statements/P69/0/value/content'"
_PORTAL_INVALID_VALUE_RE = re.compile(r"Invalid value at '(/[^']+)'")

# Plain-language reasons for Wikibase REST API data policy violations (HTTP 422)
_POLICY_VIOLATIONS = {
    'label-description-same-value': 'label and description must not be identical',
    'item-label-description-duplicate':
        'an item with the same label and description already exists',
    'property-label-duplicate': 'a property with the same label already exists',
    'sitelink-conflict': 'the sitelink is already used by another item',
}


class DuplicateOnPortal(RuntimeError):
    '''The portal did not create an item: one with its label and description exists (#141).

    The export looked its items up before (:func:`~MaRDMO.export.duplicates.look_up`),
    so the item was probably created in the meantime.  MaRDMO does not link
    it silently: the user decides in the preview (or, for an author or
    journal of a publication, the next export does).
    '''
    def __init__(self, label, description, qid, part=None):
        super().__init__(f"'{label}' ({description}) exists on the MaRDI Portal as {qid}")
        self.label, self.description, self.qid, self.part = label, description, qid, part

    def message(self, sent):
        '''The message for the user; *sent*: whether something was created before.'''
        if self.part:
            part = {'author': _('author'), 'journal': _('journal')}.get(self.part, self.part)
            parts = [_('The MaRDI Portal did not create the {part} "{label}" ({description}): an item with this '
                       'name and description now exists there ({qid}), probably created in the meantime.').format(
                           part=part, label=self.label, description=self.description, qid=self.qid)]
            last = _('Please export again: MaRDMO then handles the {part} itself.').format(part=part)
        else:
            parts = [_('The MaRDI Portal did not create "{label}" ({description}): an item with this label and '
                       'description now exists there ({qid}). It was not there when MaRDMO checked before the '
                       'export, so it was probably created in the meantime.').format(
                           label=self.label, description=self.description, qid=self.qid)]
            last = _('Open the preview again: under "Items already on the MaRDI Portal" you can use {qid} or '
                     'redefine your item. Then export again; the export adds the rest.').format(qid=self.qid)
        # The result page of an incomplete export says what was created
        if not sent:
            parts.append(str(_('Nothing was sent to the MaRDI Portal.')))
        return ' '.join([*parts, last])


def explain_error(key, jsons, err):
    '''Turn a failed POST for payload entry *key* into a message for users.

    When the portal names the rejected field (``Invalid value at
    '/item/statements/P69/0/value/content'``), the property and the value
    are looked up in the payload, e.g. *The MaRDI Portal rejected the
    value 'https://exa mple.org' for "source code repository URL" of the
    new item 'sso1'. …*.  Otherwise the entry is described generically
    and the portal message is appended unchanged.
    '''
    match = _PORTAL_INVALID_VALUE_RE.search(str(err))
    if match:
        try:
            field_name, value, target = locate_rejected_value(
                key, jsons, match.group(1).strip('/').split('/')
            )
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            pass
        else:
            if value:
                return _("The MaRDI Portal rejected the value '{value}' for \"{field}\" of {target}. Please "
                         "correct it in the questionnaire and export again. (Portal message: Invalid value)"
                         ).format(value=value, field=field_name, target=target)
            return _("The MaRDI Portal rejected the value for \"{field}\" of {target}. Please correct it in "
                     "the questionnaire and export again. (Portal message: Invalid value)"
                     ).format(field=field_name, target=target)
    return f"{describe_entry(key, jsons)}: {err}"


def locate_rejected_value(key, jsons, path):
    '''Resolve a portal error *path* to ``(field name, short value, target)``.

    Args:
        key:   Payload key of the failed entry (``Item…`` or ``RELATION…``).
        jsons: Payload dict at the time of the failure.
        path:  Path segments reported by the portal, e.g.
               ``['item', 'statements', 'P69', '0', 'value', 'content']``
               or ``['statement', 'qualifiers', '0', 'value', 'content']``.

    Raises:
        ValueError: If the path does not match the payload (or KeyError,
            IndexError, TypeError); :func:`explain_error` then falls back to
            the generic message.
    '''
    entry = jsons[key]
    if key.startswith('Item') and path[0] == 'item':
        item = entry['payload']['item']
        target = _("the new item '{label}'").format(label=entry.get('label', key))
        if path[1] in ('labels', 'descriptions'):
            field = _('label') if path[1] == 'labels' else _('description')
            return field, short_value(item[path[1]][path[2]], jsons), target
        if path[1] != 'statements':
            raise ValueError(path)
        statement, rest = item['statements'][path[2]][int(path[3])], path[4:]
    elif key.startswith('RELATION') and path[0] == 'statement':
        statement, rest = entry['payload']['statement'], path[1:]
        target = _("the existing item '{label}'").format(label=item_label(entry, jsons))
    else:
        raise ValueError(path)

    pid_to_name = {pid: name for name, pid in get_properties().items()}
    field = pid_to_name.get(statement['property']['id'], statement['property']['id'])
    if rest[0] == 'qualifiers':
        qualifier = statement['qualifiers'][int(rest[1])]
        q_id = qualifier['property']['id']
        field = _('{property}, qualifier {qualifier}').format(property=field, qualifier=pid_to_name.get(q_id, q_id))
        return field, short_value(qualifier['value']['content'], jsons), target
    return field, short_value(statement['value']['content'], jsons), target


def item_label(entry, jsons):
    '''Return the label of the item a RELATION/ALIAS *entry* is posted to.'''
    item_ref = entry.get('url', '').split('/items/')[-1].split('/')[0]
    labels_by_qid = {
        v['id']: v.get('label') for k, v in jsons.items() if k.startswith('Item') and v.get('id')
    }
    return jsons.get(item_ref, {}).get('label') or labels_by_qid.get(item_ref) or item_ref


def short_value(value, jsons):
    '''Return *value* as a single-line string of at most 60 characters.

    Item references (QIDs or ``Item<n>`` keys) are shown by label.
    '''
    if isinstance(value, dict):
        value = value.get('text') or value.get('amount') or value.get('time') or value
    if isinstance(value, str):
        labels_by_qid = {
            v['id']: v.get('label')
            for k, v in jsons.items() if k.startswith('Item') and v.get('id')
        }
        value = jsons.get(value, {}).get('label') or labels_by_qid.get(value) or value
    value = ' '.join(str(value).split())
    return f'{value[:57]}...' if len(value) > 60 else value


def describe_entry(key, jsons):
    '''Return a readable description of the payload entry *key* for error messages.

    Items are named by their label; statements and aliases by property,
    item label, and a shortened value — instead of internal keys such as
    ``RELATION3``.
    '''
    entry = jsons.get(key, {})
    if key.startswith('Item'):
        return _("Error creating item '{label}'").format(label=entry.get('label', key))

    subject = item_label(entry, jsons)
    if key.startswith('ALIAS'):
        aliases = ', '.join(entry.get('payload', {}).get('aliases', []))
        return _("Error adding alias '{aliases}' to '{label}'").format(aliases=aliases, label=subject)

    statement = entry.get('payload', {}).get('statement', {})
    prop_id = statement.get('property', {}).get('id', '')
    prop_name = {pid: name for name, pid in get_properties().items()}.get(prop_id, prop_id)
    value = short_value(statement.get('value', {}).get('content', ''), jsons)
    return _("Error adding statement '{property}' to '{label}' (value: '{value}')").format(
        property=prop_name, label=subject, value=value)


def extract_error_message(response):
    """Extract a human-readable error message from an API response.

    Handles both the Wikibase REST API (``message``, ``code``/``context``)
    and the Wikibase Action API (``error.info``, ``error.code``) response
    formats.

    Args:
        response: :class:`requests.Response` object from a failed API call.

    Returns:
        Error message string; falls back to the raw response text (up to
        200 characters) or ``"Error details unavailable"`` if parsing fails.
    """
    try:
        error_data = response.json()

        # Try to get the most informative error message
        # Wikibase API returns 'message' (REST API) or 'info' (Action API)
        if 'message' in error_data:
            error_msg = error_data['message']
        elif 'error' in error_data:
            # Action API: error.info or error.code
            error_obj = error_data['error']
            error_msg = error_obj.get('info') or error_obj.get('code', 'Unknown error')
        elif 'code' in error_data:
            # REST API: code + optional context
            error_msg = error_data['code']
            if 'context' in error_data:
                context = error_data['context']
                if isinstance(context, dict):
                    try:
                        context_str = ', '.join(f"{k}: {v}" for k, v in context.items())
                        error_msg = f"{error_msg} ({context_str})"
                    except Exception:
                        pass
        else:
            error_msg = str(error_data)[:500]

        return error_msg
    except (ValueError, AttributeError, TypeError, KeyError):
        # If response is not JSON or has unexpected structure
        try:
            return response.text[:200] if response.text else "No error details available"
        except Exception:
            return "Error details unavailable"


def handle_policy_violation(response, key, jsons):
    """Handle an HTTP 422 (``data-policy-violation``) error from the Wikibase API.

    Every violation stops the export: silently continuing would leave the
    item uncreated and break later references to it.  An item that exists
    already (``item-label-description-duplicate``) is not linked either
    (#141): :class:`DuplicateOnPortal` tells the user what to do.

    Args:
        response: :class:`requests.Response` object with a 422 status.
        key:      Payload key that caused the violation.
        jsons:    Full payload dict.

    Raises:
        DuplicateOnPortal: For an item with the label and description of a portal item.
        RuntimeError: For any other violation.
    """
    try:
        error_json = response.json()
    except ValueError:
        error_json = {}
    context = error_json.get("context") if isinstance(error_json.get("context"), dict) else {}
    violation = context.get("violation", "")

    if violation == 'item-label-description-duplicate' and key.startswith('Item'):
        entry = jsons[key]
        raise DuplicateOnPortal(
            entry.get('label', key), entry.get('description', ''),
            context.get("violation_context", {}).get("conflicting_item_id", ''),
            {'Author': 'author', 'Journal': 'journal'}.get(entry.get('class')),
        )

    reason = _POLICY_VIOLATIONS.get(violation) or extract_error_message(response)
    raise RuntimeError(
        _("The MaRDI Portal rejected the request (HTTP 422): %(reason)s") % {'reason': reason}
    )
