'''The export to the MaRDI Portal: a background job that posts the payload.

:class:`Upload` posts the entries of the payload and reports its progress;
afterwards the project gets the IDs of the created items
(:func:`~MaRDMO.export.items.replace_ids`) and the result page lists them and the
statements (:func:`collect_statements`).  :mod:`MaRDMO.export.oauth2` starts it
after the authorization.
'''

import copy
import logging
import random
import time

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from django.db import connection
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from ..core.config import get_items, get_properties
from .items import compare_items, replace_ids
from ..core.ids import item_text
from .portal_errors import DuplicateOnPortal, explain_error, extract_error_message, handle_policy_violation
from .store import _progress_store
from ..core.values import replace_in_dict

logger = logging.getLogger(__name__)


def in_language(language, function):
    """*function*, run in *language* (Django's language is per thread; a new thread has the default)."""
    def run(*args, **kwargs):
        with translation.override(language):
            return function(*args, **kwargs)
    return run


class Upload:
    '''One export to the MaRDI Portal, run in the background (:meth:`run`), its progress in :mod:`~MaRDMO.export.store`.

    Posts all ``Item*`` entries of the payload, then all ``RELATION*`` and
    ``ALIAS*`` entries (:meth:`post_data`), with retries, and replaces the
    ``Item<n>`` placeholders by the QIDs of the created items.
    '''

    def __init__(self, job_id, headers, session=None):
        '''Prepare the export *job_id*.

        Args:
            job_id:  Key of the job in :data:`~MaRDMO.export.store._progress_store`.
            headers: The authorization headers of the requests (the user's token).
            session: The :class:`requests.Session` of the requests; one is
                     opened with the first request if not given.
        '''
        self.job_id = job_id
        self.headers = headers
        self.session = session

    def run(self, request, jsons, dependency, project):
        """
        Run the Wikibase posting in the background.
        Posts all 'Item*' payloads first, then all 'RELATION*' / 'ALIAS*' payloads.
        Updates _progress_store[job_id] continuously with phase and progress info.

        If posting fails midway, whatever was created up to that point is
        still written back to the project (so a retry continues where it
        stopped) and reported as an incomplete export.
        """
        job_id = self.job_id

        logger.info("[%s] Background posting started", job_id)

        init = copy.deepcopy(jsons)
        item_keys = list(dependency)
        relation_keys = [k for k in jsons if k.startswith(("RELATION", "ALIAS"))]
        total = len(item_keys) + len(relation_keys)
        completed = 0
        current_key = None
        error = None

        try:
            for phase, keys in (("items", item_keys), ("relations", relation_keys)):
                logger.info("[%s] Starting %s upload: %s entries", job_id, phase, len(keys))
                self.set_progress(completed, total, phase)
                for key in keys:
                    current_key = key
                    jsons = self.post_data(key, jsons)
                    completed += 1
                    self.set_progress(completed, total, phase)
                    time.sleep(0.1)
            current_key = None
        except DuplicateOnPortal as err:
            logger.warning("[%s] Stopped at %s: %s", job_id, current_key, err)
            error = err
            current_key = None
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.exception("[%s] Failed posting %s: %s", job_id, current_key, err)
            error = _('Unexpected error: {error}').format(error=err)
            if current_key:
                try:
                    error = explain_error(current_key, jsons, err)
                except Exception:  # pylint: disable=broad-exception-caught
                    # Never let message formatting hide the actual error
                    logger.exception("[%s] Could not describe error for %s", job_id, current_key)
                    error = _('Error while posting to the MaRDI Portal: {error}').format(error=err)

        try:
            self.finish(request, project, init, jsons, error, completed, total)
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.exception("[%s] Failed finishing export: %s", job_id, err)
            _progress_store[job_id] = {
                "progress": int((completed / total) * 100) if total else 0,
                "done": True,
                "phase": "error",
                # Whether something was created is not known here
                "error": (error.message(sent=True) if isinstance(error, DuplicateOnPortal) else error)
                         or _('Unexpected error: {error}').format(error=err),
            }
        finally:
            # The thread opened its own DB connection; Django only closes
            # connections of request threads automatically
            connection.close()

    def set_progress(self, completed, total, phase):
        '''Store an intermediate progress entry of the job.'''
        _progress_store[self.job_id] = {
            "progress": int((completed / total) * 100) if total else 0,
            "done": False,
            "phase": phase,
        }

    def finish(self, request, project, init, jsons, error, completed, total):
        '''Write created IDs back to *project* and store the final job result.

        Outcomes stored in the progress entry:

        - ``done``    — everything posted; redirect to the result page
        - ``partial`` — failed after something was created; redirect to the
          result page, which shows the error and what was created
        - ``error``   — failed before anything was created

        *error* is a message, or a :class:`DuplicateOnPortal` whose message
        depends on whether something was created.
        '''
        job_id = self.job_id
        created = compare_items(init, jsons, get_properties().get('Wikidata QID'))
        if created and project is not None:
            replace_ids(project, created)
        ids = [
            [info.get('class', ''), item_text(info['label'], info['description']), info['new_qid']]
            for info in created.values()
        ]
        pid_to_name = {qid: name for name, qid in get_properties().items()}
        qid_to_name = {qid: name for name, qid in get_items().items()}
        statements = collect_statements(init, jsons, pid_to_name, qid_to_name)
        if isinstance(error, DuplicateOnPortal):
            error = error.message(sent=bool(ids or statements))

        if error and not (ids or statements):
            _progress_store[job_id] = {
                "progress": int((completed / total) * 100) if total else 0,
                "done": True,
                "phase": "error",
                "error": error,
            }
            return

        relations_planned = [
            k for k, v in init.items() if k.startswith('RELATION') and v.get('exists') != 'true'
        ]
        _progress_store[job_id] = {
            "progress": 100 if not error else int((completed / total) * 100),
            "done": True,
            "phase": "partial" if error else "done",
            "error": error,
            "ids": ids,
            "statements": statements,
            "counts": {
                "items_created": len(ids),
                "items_planned": sum(
                    1 for k, v in init.items() if k.startswith('Item') and not v['id']
                ),
                "relations_created": sum(1 for k in relations_planned if jsons[k].get('id')),
                "relations_planned": len(relations_planned),
            },
            "redirect": request.build_absolute_uri(reverse("show_success", args=[job_id])),
        }
        logger.info("[%s] Export finished (%s)", job_id, "incomplete" if error else "complete")

    def post_data(self, key, jsons):
        """Post the payload entry for *key* to the Wikibase REST API.

        Skips entries that already have an ID (items) or are marked as
        existing (relations).  Relations marked ``'partial'`` are on the
        portal already; their missing qualifiers are added to the statement
        with a PATCH instead.  Retries up to five times on timeout or
        connection errors with exponential back-off.

        Args:
            key:          Payload key string (e.g. ``'Item0000000001'`` or
                          ``'RELATION_…'``).
            jsons:        Full payload dict; may be mutated in place when a
                          placeholder is replaced by a real QID.

        Returns:
            Updated payload dict with the new QID substituted for *key*.

        Raises:
            RuntimeError: If all retry attempts fail with no response.
        """

        # No Post, if key not in Payload
        if not jsons.get(key):
            return jsons

        item = jsons[key]

        # No Post, if item already on Portal
        if key.startswith('Item') and item.get('id'):
            return replace_in_dict(jsons, key, item['id'])

        # No Post, if relation already on Portal
        if key.startswith('RELATION') and item.get('exists') == 'true':
            return jsons

        if self.session is None:
            self.session = requests.Session()
        session = self.session

        url = item['url']
        payload = item['payload']
        method = 'post'
        if key.startswith('RELATION') and item.get('exists') == 'partial':
            # The statement is on the portal already: only add the qualifiers it lacks
            method = 'patch'
            url = f"{url}/{item['statement_id']}"
            payload = {'patch': [
                {'op': 'add', 'path': '/qualifiers/-',
                 'value': {'property': {'id': q['property']['id']}, 'value': q['value']}}
                for q in item['add_qualifiers']
            ]}
        headers = self.headers
        response = None
        for attempt in range(1, 6):
            try:
                response = session.request(method, url, json=payload, headers=headers, timeout=120)
                response.raise_for_status()
                wait = 0.1 + random.uniform(0, 0.5)
                time.sleep(wait)
                return handle_response(response, key, jsons)

            except requests.exceptions.Timeout:
                time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                continue

            except requests.exceptions.ConnectionError:
                time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                continue

            except requests.HTTPError as exc:
                resp = exc.response
                status = resp.status_code if resp is not None else "no_response"
                if status == 429:
                    time.sleep(retry_after_seconds(resp))
                    continue
                if status == 403:
                    # The portal sometimes answers 403 when it is merely
                    # unstable, so 403 is retried like a server error
                    time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                    continue
                if isinstance(status, int) and status >= 500:
                    time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                    continue
                if status == 422:
                    return handle_policy_violation(resp, key, jsons)
                # Extract detailed error message from response
                error_detail = extract_error_message(resp)
                raise RuntimeError(
                    _("POST request failed (HTTP %(status)s): %(detail)s") % {
                        'status': status,
                        'detail': error_detail
                    }
                ) from exc

        if response is not None:
            if response.status_code == 403:
                raise RuntimeError(
                    _("The MaRDI Portal refused the request %(attempts)s times (HTTP 403: "
                      "%(detail)s). This is usually temporary; please try again later. If it "
                      "keeps happening, check that your account may edit the MaRDI Portal.") % {
                        'attempts': 5,
                        'detail': extract_error_message(response),
                    }
                )
            if response.status_code >= 500:
                raise RuntimeError(
                    _("The MaRDI Portal did not accept the request after %(attempts)s attempts "
                      "(HTTP %(status)s). This is usually temporary; please try again later.") % {
                        'attempts': 5,
                        'status': response.status_code,
                    }
                )
            error_detail = extract_error_message(response)
            raise RuntimeError(
                _("POST request failed after %(attempts)s retries: %(detail)s") % {
                    'attempts': 5,
                    'detail': error_detail
                }
            )

        raise RuntimeError(
            _("The MaRDI Portal could not be reached (no response after several attempts). "
              "Please try again later.")
        )


def retry_after_seconds(response, default=5, maximum=60):
    '''Return the wait time requested by a 429 response's ``Retry-After`` header.

    The header is either a number of seconds or an HTTP date; anything
    unparsable falls back to *default*.  The wait is capped at *maximum*.
    '''
    value = (response.headers.get('Retry-After') or '').strip()
    if value.isdigit():
        seconds = int(value)
    else:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError):
            seconds = default
    return min(max(seconds, 1), maximum)


def handle_response(response, key, jsons):
    """Process a successful POST response and replace the placeholder with the new QID.

    Args:
        response: Successful :class:`requests.Response` object.
        key:      Payload key that was just posted (e.g. ``'Item0000000001'``).
        jsons:    Full payload dict; mutated in place for non-alias keys.

    Returns:
        Updated payload dict with the new Wikibase ID substituted for *key*.
    """
    response.raise_for_status()
    if not key.startswith("ALIAS"):
        jsons[key]['id'] = response.json().get('id')
        jsons = replace_in_dict(jsons, key, jsons[key]['id'])
    return jsons


def collect_statements(init, jsons, pid_to_name=None, qid_to_name=None):
    """Extract newly added statements as human-readable triples after a portal export.

    Covers two sources:

    - ``RELATION<n>`` entries that were posted to existing items (the portal
      returned a statement id; entries that already existed or were not
      reached before an aborted export have none).
    - Statements embedded in newly created ``Item<n>`` entries (items that had
      no id before posting).

    Args:
        init:         Deep copy of the payload taken *before* posting (used to
                      distinguish new vs. pre-existing items).
        jsons:        Payload dict *after* posting (all ``Item<n>`` placeholders
                      replaced with real QIDs by :func:`~MaRDMO.core.values.replace_in_dict`).
        pid_to_name:  Dict mapping Wikibase property IDs to human-readable names
                      (i.e. the inverse of ``get_properties()``).
        qid_to_name:  Dict mapping Wikibase item QIDs to human-readable names
                      (i.e. the inverse of ``get_items()``).

    Returns:
        List of ``[subject_label, subject_qid, property_name, object_label,
        object_qid, qualifiers, unit_label, unit_qid, qualifiers_added]``
        lists, JSON-serializable.  ``object_qid`` is an empty string for
        non-item value types.  ``qualifiers`` is a list of
        ``{"prop": name, "obj": label, "obj_qid": qid}`` dicts.
        ``qualifiers_added`` is ``True`` for a statement that was on the
        portal already and only got the listed qualifiers.
    """
    pid_to_name = pid_to_name or {}
    qid_to_name = qid_to_name or {}

    qid_to_label = {
        v['id']: v['label']
        for k, v in jsons.items()
        if k.startswith('Item') and v.get('id') and v.get('label')
    }

    def _resolve(qid):
        """Return a human-readable label for *qid*, falling back to the raw QID."""
        return qid_to_label.get(qid) or qid_to_name.get(qid) or qid

    def _format_value(datatype, value):
        """Convert a Wikibase statement value to a ``(display_string, obj_qid)`` pair.

        *obj_qid* is non-empty only for ``wikibase-item`` values so the caller
        can render a portal link.  Special handling per datatype:

        - ``wikibase-item``    — resolves QID to label via ``_resolve``
        - ``quantity``         — strips leading ``+`` from amount (unit handled separately)
        - ``monolingualtext``  — extracts the ``text`` field
        - ``time``             — extracts the date portion (``YYYY-MM-DD``)
        - ``math``             — wraps in ``\\(…\\)`` for MathJax inline rendering
        """
        if datatype == 'wikibase-item' and isinstance(value, str):
            return _resolve(value), value
        if datatype == 'quantity' and isinstance(value, dict):
            return value.get('amount', '').lstrip('+'), ''
        if datatype == 'monolingualtext' and isinstance(value, dict):
            return value.get('text', str(value)), ''
        if datatype == 'time' and isinstance(value, dict):
            return value.get('time', '').lstrip('+').split('T')[0], ''
        if datatype == 'math':
            return f'\\({value}\\)', ''
        return str(value), ''

    def _get_unit(datatype, value):
        """Return ``(unit_label, unit_qid)`` for a quantity value with a named unit.

        Returns ``('', '')`` for non-quantity values or dimensionless quantities
        (unit ``"1"``).  The unit QID is extracted from the tail of the unit URL
        and resolved to a label via ``_resolve``.
        """
        if datatype != 'quantity' or not isinstance(value, dict):
            return '', ''
        u_qid = value.get('unit', '').rsplit('/', 1)[-1]
        if u_qid == '1':
            return '', ''
        return _resolve(u_qid), u_qid

    def _format_qualifiers(quals_raw):
        """Format a list of raw Wikibase qualifier dicts into display-ready dicts.

        Each output dict has keys ``prop`` (property label), ``obj`` (formatted
        value string), and ``obj_qid`` (portal QID or empty string).
        """
        result = []
        for q in quals_raw:
            q_prop_id = q.get('property', {}).get('id', '')
            q_dtype   = q.get('property', {}).get('data_type', 'string')
            q_val     = q.get('value', {}).get('content', '')
            q_prop_name      = pid_to_name.get(q_prop_id, q_prop_id)
            q_obj, q_obj_qid = _format_value(q_dtype, q_val)
            result.append({'prop': q_prop_name, 'obj': q_obj, 'obj_qid': q_obj_qid})
        return result

    statements = []

    # --- RELATION entries posted to existing items
    for key, entry in jsons.items():
        if not key.startswith('RELATION'):
            continue
        if entry.get('exists') == 'true' or not entry.get('id'):
            continue
        url = entry.get('url', '')
        parts = url.split('/items/')
        if len(parts) < 2:
            continue
        subject_qid   = parts[1].split('/')[0]
        subject_label = _resolve(subject_qid)
        stmt     = entry['payload']['statement']
        prop_id  = stmt['property']['id']
        datatype = stmt['property']['data_type']
        value    = stmt['value']['content']
        prop_name          = pid_to_name.get(prop_id, prop_id)
        obj_label, obj_qid = _format_value(datatype, value)
        unit_label, unit_qid = _get_unit(datatype, value)
        # A statement that was on the portal already only got the qualifiers it lacked
        added = entry.get('exists') == 'partial'
        quals = _format_qualifiers(entry['add_qualifiers'] if added else stmt.get('qualifiers', []))
        statements.append([subject_label, subject_qid, prop_name, obj_label, obj_qid, quals, unit_label, unit_qid,
                           added])

    # --- Statements embedded in newly created items
    for key, entry in jsons.items():
        if not key.startswith('Item'):
            continue
        if init.get(key, {}).get('id'):  # was already on portal before posting
            continue
        subject_qid = entry.get('id', '')
        if not subject_qid:
            continue
        subject_label = entry.get('label', subject_qid)
        for stmt_tuple in entry.get('statements', []):
            if len(stmt_tuple) < 3:
                continue
            prop_id, datatype, value = stmt_tuple[0], stmt_tuple[1], stmt_tuple[2]
            quals_raw = stmt_tuple[3] if len(stmt_tuple) >= 4 else []
            prop_name          = pid_to_name.get(prop_id, prop_id)
            obj_label, obj_qid = _format_value(datatype, value)
            unit_label, unit_qid = _get_unit(datatype, value)
            quals = _format_qualifiers(quals_raw)
            statements.append([subject_label, subject_qid, prop_name, obj_label, obj_qid, quals, unit_label, unit_qid,
                               False])

    return statements
