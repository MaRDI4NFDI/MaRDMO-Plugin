'''OAuth2-based export provider with live progress tracking for MaRDMO.

Provides :class:`OauthProviderMixin`, the abstract base class that handles:

- OAuth2 authorisation flow against the MaRDI Portal (``/authorize`` →
  ``/callback`` → token exchange).
- Background export job execution with progress reported via
  :mod:`~MaRDMO.store` and streamed to the browser.
- Wikibase REST API posting: :meth:`~OauthProviderMixin._post_data` retries
  failed requests, handles duplicate-item policy violations, and substitutes
  temporary ``Item<n>`` placeholders with the real Wikibase QIDs.

Subclasses must implement :meth:`~OauthProviderMixin.get_authorize_params`
and :meth:`~OauthProviderMixin.post_success` to supply catalog-specific
export logic.
'''

import logging
import copy
import time
import random
import threading

from urllib.parse import urlencode

import requests
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from rdmo.projects.models import Project

from .constants import BASE_URI
from .getters import get_items, get_properties
from .helpers import replace_in_dict, compare_items, replace_ids, collect_statements
from .store import _register_job_for_session

logger = logging.getLogger(__name__)

# Global in-memory progress store
_progress_store = {}


class OauthProviderMixin:
    '''Mixin providing a full OAuth2 authorization-code flow with async Wikibase posting.

    Subclasses must implement :meth:`get_authorize_params`, :meth:`get_callback_auth`,
    :meth:`get_callback_headers`, :meth:`get_callback_params`,
    :meth:`get_callback_data`, and :meth:`post_success`.  The mixin handles
    state validation, token exchange, background upload, and progress tracking.
    '''

    # ------------------- OAUTH FLOW -------------------

    def post(self, request, jsons=None, dependency=None):
        '''Persist posting arguments in the session and start the OAuth flow.

        Args:
            request:    Django HTTP request.
            jsons:      Payload dict to upload (serialisable).
            dependency: Ordered iterable of item keys to post before relations.

        Returns:
            Redirect to the OAuth authorization endpoint.
        '''
        self.store_in_session(request, 'request', ('post', jsons, dependency))
        self.store_in_session(request, 'project_id', self.project.pk)
        return self.authorize(request)

    def authorize(self, request):
        '''Redirect the user to the OAuth authorization endpoint.

        Generates a random CSRF *state* token, stores it in the session, and
        builds the redirect URL from :meth:`get_authorize_params`.

        Args:
            request: Django HTTP request.

        Returns:
            :class:`~django.http.HttpResponseRedirect` to the authorization URL.
        '''
        state = get_random_string(length=32)
        self.store_in_session(request, 'state', state)
        url = self.authorize_url + '?' + urlencode(self.get_authorize_params(request, state))
        return HttpResponseRedirect(url)

    def callback(self, request):
        '''Handle the OAuth callback, exchange the code for a token, and start posting.

        Validates the *state* parameter, exchanges the authorization code for an
        access token, then launches :meth:`_background_post` in a daemon thread
        and redirects to the live-progress page.

        Args:
            request: Django HTTP request (must contain ``code`` and ``state``
                     GET parameters set by the authorization server).

        Returns:
            Redirect to the progress page on success, or an error page on
            state-mismatch or token-exchange failure.
        '''
        if request.GET.get('state') != self.pop_from_session(request, 'state'):
            return self.render_error(
                request,
                _('OAuth authorization not successful'),
                _('State parameter did not match.')
            )

        # Exchange the authorization code for an access token
        url = self.token_url + '?' + urlencode(self.get_callback_params(request))
        response = requests.post(
            url,
            self.get_callback_data(request),
            auth=self.get_callback_auth(request),
            headers=self.get_callback_headers(request),
            timeout=10
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error('callback error: %s (%s)', response.content, response.status_code)
            return self.render_error(
                request,
                _('OAuth process failed'),
                e
            )

        response_data = response.json()
        access_token = response_data.get('access_token')

        # Retrieve the original post request data
        data = self.pop_from_session(request, 'request')
        if not data:
            return self.render_error(
                request,
                _('OAuth authorization successful'),
                _('But no redirect could be found.'),
            )

        _method, jsons, dependency = data

        # ------------------- ASYNC POSTING -------------------

        # Generate job ID and store initial progress in the cache
        job_id = get_random_string(16)
        _register_job_for_session(request, job_id)
        _progress_store[job_id] = {
            "progress": 0,
            "done": False,
            "phase": "starting",
            "error": None,
        }

        project_id = self.pop_from_session(request, 'project_id')
        project = Project.objects.get(pk=project_id) if project_id else None

        # Start posting thread
        thread = threading.Thread(
            target=self._background_post,
            args=(request, access_token, jsons, dependency, job_id, project),
            daemon=True,
        )
        thread.start()

        # Immediately render progress page
        return HttpResponseRedirect(
            reverse("show_progress", args=[job_id])
        )

    # ------------------- BACKGROUND PROCESS -------------------

    def _background_post(self, request, access_token, jsons, dependency, job_id, project):
        """
        Run the Wikibase posting in the background.
        Posts all 'Item*' payloads first, then all 'RELATION*' payloads.
        Updates _progress_store[job_id] continuously with phase and progress info.
        """

        logger.info("[%s] Background posting started", job_id)

        try:
            keys = list(jsons.keys())

            # --- Separate item and relation keys
            item_keys = list(dependency)
            relation_keys = [k for k in keys if k.startswith(("RELATION", "ALIAS"))]

            num_items = len(item_keys)
            num_relations = len(relation_keys)
            total = num_items + num_relations
            completed = 0

            init = copy.deepcopy(jsons)

            # --- Phase 1: Items
            _progress_store[job_id] = {"progress": 0, "done": False, "phase": "items"}
            logger.info("[%s] Starting item upload: %s items", job_id, num_items)

            for key in item_keys:
                try:
                    jsons = self._post_data(key, jsons, access_token)
                except RuntimeError as err:
                    label = jsons.get(key, {}).get('label', key)
                    logger.exception(
                        "[%s] Failed posting item %s (%s): %s",
                        job_id, key, label, err
                    )
                    _progress_store[job_id] = {
                        "progress": int((completed / total) * 100),
                        "done": True,
                        "phase": "error",
                        "error": f"Error posting item '{label}': {err}",
                    }
                    return

                completed += 1
                _progress_store[job_id] = {
                    "progress": int((completed / total) * 100),
                    "done": False,
                    "phase": "items",
                }
                time.sleep(0.1)

            # --- Phase 2: Relations
            _progress_store[job_id] = {
                "progress": int((completed / total) * 100),
                "done": False,
                "phase": "relations",
            }
            logger.info("[%s] Starting relation upload: %s relations", job_id, num_relations)

            for key in relation_keys:
                try:
                    jsons = self._post_data(key, jsons, access_token)
                except RuntimeError as err:
                    logger.exception("[%s] Failed posting relation %s: %s", job_id, key, err)
                    _progress_store[job_id] = {
                        "progress": int((completed / total) * 100),
                        "done": True,
                        "phase": "error",
                        "error": f"Error posting relation {key}: {err}",
                    }
                    return

                completed += 1
                _progress_store[job_id] = {
                    "progress": int((completed / total) * 100),
                    "done": False,
                    "phase": "relations",
                }
                time.sleep(0.1)

            # --- All done
            wikidata_qid_prop = get_properties().get('Wikidata QID')
            created = compare_items(init, jsons, wikidata_qid_prop)
            replace_ids(project, created, BASE_URI)
            ids = [
                [info.get('class', ''), f'{label} ({desc})' if desc else label, info['new_qid']]
                for (label, desc), info in created.items()
            ]
            pid_to_name = {qid: name for name, qid in get_properties().items()}
            qid_to_name = {qid: name for name, qid in get_items().items()}
            statements = collect_statements(init, jsons, pid_to_name, qid_to_name)
            _progress_store[job_id] = {
                "progress": 100,
                "done": True,
                "phase": "done",
                "error": None,
                "ids": ids,
                "statements": statements,
                "redirect": request.build_absolute_uri(
                    reverse("show_success", args=[job_id])
                ),
            }

            logger.info(
                "[%s] Posting complete. Redirect -> /services/success/%s/",
                job_id,
                job_id,
            )

        except Exception as e:
            logger.exception("[%s] Unexpected error: %s", job_id, e)
            _progress_store[job_id] = {
                "progress": int((completed / total) * 100) if total else 0,
                "done": True,
                "phase": "error",
                "error": str(e),
            }

    # ------------------- CORE POST LOGIC -------------------

    def _post_data(self, key, jsons, access_token):
        """Post the payload entry for *key* to the Wikibase REST API.

        Skips entries that already have an ID (items) or are marked as
        existing (relations).  Retries up to five times on timeout or
        connection errors with exponential back-off.

        Args:
            key:          Payload key string (e.g. ``'Item0000000001'`` or
                          ``'RELATION_…'``).
            jsons:        Full payload dict; may be mutated in place when a
                          placeholder is replaced by a real QID.
            access_token: OAuth2 bearer token string.

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

        session = getattr(self, "_session", None)
        if session is None:
            session = requests.Session()
            self._session = session

        url = item['url']
        payload = item['payload']
        headers = self.get_authorization_headers(access_token)
        response = None
        for attempt in range(1, 6):
            try:
                response = session.post(url, json=payload, headers=headers, timeout=120)
                response.raise_for_status()
                wait = 0.1 + random.uniform(0, 0.5)
                time.sleep(wait)
                return self._handle_response(response, key, jsons)

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
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    time.sleep(retry_after)
                    continue
                if status == 403:
                    time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                    continue
                if isinstance(status, int) and status >= 500:
                    time.sleep(1.5 ** attempt + random.uniform(0, 0.5))
                    continue
                if status == 422:
                    return self._handle_policy_violation(resp, key, jsons)
                # Extract detailed error message from response
                error_detail = self._extract_error_message(resp)
                raise RuntimeError(
                    _("POST request failed (HTTP %(status)s): %(detail)s") % {
                        'status': status,
                        'detail': error_detail
                    }
                ) from exc

        if response is not None:
            error_detail = self._extract_error_message(response)
            raise RuntimeError(
                _("POST request failed after %(attempts)s retries: %(detail)s") % {
                    'attempts': 5,
                    'detail': error_detail
                }
            )

        raise RuntimeError(_("POST request failed after multiple retries (no response)"))

    def _extract_error_message(self, response):
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

    def _handle_response(self, response, key, jsons):
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

    def _handle_policy_violation(self, response, key, jsons):
        """Handle a ``data-policy-violation`` HTTP 422 error from the Wikibase API.

        When the violation is ``item-label-description-duplicate``, the
        conflicting existing item's ID is extracted and used as the resolved
        QID so the export can proceed without creating a duplicate.

        Args:
            response: :class:`requests.Response` object with a 422 status and a
                      JSON body containing ``code`` and ``context`` fields.
            key:      Payload key that caused the violation.
            jsons:    Full payload dict; mutated in place when a duplicate is resolved.

        Returns:
            Updated payload dict, or the original *jsons* if the violation
            could not be resolved.
        """
        error_json = response.json()
        if error_json.get("code") == "data-policy-violation":
            violation = error_json.get("context", {}).get("violation")
            if violation == 'item-label-description-duplicate':
                conflict_id = (
                    error_json["context"]
                    .get("violation_context", {})
                    .get("conflicting_item_id")
                )
                if conflict_id:
                    jsons[key]['id'] = conflict_id
                    return replace_in_dict(jsons, key, conflict_id)
        return jsons

    # ------------------- HELPERS -------------------

    def render_error(self, request, title, message):
        '''Render the ``core/error.html`` template with *title* and *message*.

        Args:
            request: Django HTTP request.
            title:   Short error heading (translated string).
            message: Detailed error description (translated string or exception).

        Returns:
            :class:`~django.http.HttpResponse` (status 200) rendering the error page.
        '''
        return render(
            request,
            'core/error.html',
            {
                'title': title,
                'errors': [message]
            },
            status=200
        )

    def get_session_key(self, key):
        '''Return the namespaced session key ``"<class_name>.<key>"``.

        Args:
            key: Logical key name (e.g. ``"state"`` or ``"request"``).

        Returns:
            String combining :attr:`class_name` and *key* with a dot separator.
        '''
        return f'{self.class_name}.{key}'

    def store_in_session(self, request, key, data):
        '''Write *data* under the namespaced *key* into the Django session.

        Args:
            request: Django HTTP request whose session is updated.
            key:     Logical key name passed through :meth:`get_session_key`.
            data:    Serialisable value to store.
        '''
        request.session[self.get_session_key(key)] = data

    def pop_from_session(self, request, key):
        '''Remove and return a value from the Django session.

        Args:
            request: Django HTTP request.
            key:     Logical key name passed through :meth:`get_session_key`.

        Returns:
            The stored value, or ``None`` if the key is absent.
        '''
        return request.session.pop(self.get_session_key(key), None)

    def get_from_session(self, request, key):
        '''Read (without removing) a value from the Django session.

        Args:
            request: Django HTTP request.
            key:     Logical key name passed through :meth:`get_session_key`.

        Returns:
            The stored value, or ``None`` if the key is absent.
        '''
        session_key = self.get_session_key(key)
        return request.session.get(session_key)

    def get_authorization_headers(self, access_token):
        '''Build the ``Authorization: Bearer …`` header dict.

        Args:
            access_token: OAuth2 access token string.

        Returns:
            Dict ``{"Authorization": "Bearer <access_token>"}``.
        '''
        return {'Authorization': f'Bearer {access_token}'}

    def get_authorize_params(self, request, state):
        '''Return query parameters for the OAuth authorization redirect URL.

        Must be overridden by subclasses to supply provider-specific parameters
        such as ``client_id``, ``redirect_uri``, ``response_type``, and ``scope``.

        Args:
            request: Django HTTP request.
            state:   CSRF state token generated by :meth:`authorize`.

        Returns:
            Dict of query-string parameters.

        Raises:
            NotImplementedError: Always — subclasses must implement this method.
        '''
        raise NotImplementedError

    def get_callback_auth(self, request):
        '''Return the HTTP Basic-Auth credentials for the token-exchange request.

        Default implementation returns ``None`` (no Basic-Auth).  Subclasses
        may override to supply ``(client_id, client_secret)``.

        Args:
            request: Django HTTP request.

        Returns:
            ``None`` or a ``(username, password)`` tuple.
        '''
        return None

    def get_callback_headers(self, request):
        '''Return HTTP headers for the token-exchange POST request.

        Default implementation returns ``Accept: application/json`` and a
        ``User-Agent`` identifying the MaRDMO plugin.  Subclasses may override.

        Args:
            request: Django HTTP request.

        Returns:
            Dict of HTTP header name → value pairs.
        '''
        return {'Accept': 'application/json',
                'User-Agent': 'MaRDMO (https://zib.de; reidelbach@zib.de)'}

    def get_callback_params(self, request):
        '''Return URL query parameters appended to the token-exchange endpoint.

        Default implementation returns an empty dict.  Subclasses may override
        to pass provider-specific parameters (e.g. ``grant_type``).

        Args:
            request: Django HTTP request.

        Returns:
            Dict of query-string parameters.
        '''
        return {}

    def get_callback_data(self, request):
        '''Return the POST body data for the token-exchange request.

        Default implementation returns an empty dict.  Subclasses may override
        to supply ``code``, ``redirect_uri``, or other required fields.

        Args:
            request: Django HTTP request.

        Returns:
            Dict of form-body fields.
        '''
        return {}

    def post_success(self, request, init, final):
        '''Handle a completed upload and render the success page.

        Called after all items and relations have been posted.  Must be
        overridden by subclasses to display provider-specific results.

        Args:
            request: Django HTTP request.
            init:    Deep copy of the original payload dict (before posting).
            final:   Updated payload dict containing assigned Wikibase IDs.

        Raises:
            NotImplementedError: Always — subclasses must implement this method.
        '''
        raise NotImplementedError
