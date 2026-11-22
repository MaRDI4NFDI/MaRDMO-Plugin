'''OAuth2 authorization of the export to the MaRDI Portal.

Provides :class:`OauthProviderMixin`: the authorization flow against the
MaRDI Portal (``/authorize`` → ``/callback`` → token exchange), after which
the export runs in the background (:class:`~MaRDMO.upload.Upload`) and the
browser shows its progress.
'''

import logging
import threading

from urllib.parse import urlencode

import requests
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from rdmo.projects.models import Project

from .store import _progress_store, _register_job_for_session
from .upload import Upload, in_language

logger = logging.getLogger(__name__)


class OauthProviderMixin:
    '''Mixin providing a full OAuth2 authorization-code flow with async Wikibase posting.

    Subclasses implement :meth:`get_authorize_params` and may override
    :meth:`get_callback_auth`, :meth:`get_callback_headers`,
    :meth:`get_callback_params` and :meth:`get_callback_data`.  The mixin
    handles state validation and token exchange, then starts the upload
    (:class:`~MaRDMO.upload.Upload`) and shows its progress.
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
        access token, then launches :meth:`~MaRDMO.upload.Upload.run` in a daemon thread
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

        # Start posting thread; its messages are in the language of the request
        thread = threading.Thread(
            target=in_language(translation.get_language(),
                               Upload(job_id, self.get_authorization_headers(access_token)).run),
            args=(request, jsons, dependency, project),
            daemon=True,
        )
        thread.start()

        # Immediately render progress page
        return HttpResponseRedirect(
            reverse("show_progress", args=[job_id])
        )

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

    def get_from_session(self, request, key):
        '''Read (without removing) a value from the Django session.

        RDMO's OAuth callback view (``rdmo.services.views.oauth_callback``)
        calls it to find the provider that started the authorization: without
        it the callback fails before :meth:`callback` runs.

        Args:
            request: Django HTTP request.
            key:     Logical key name passed through :meth:`get_session_key`.

        Returns:
            The stored value, or ``None`` if the key is absent.
        '''
        return request.session.get(self.get_session_key(key), None)

    def pop_from_session(self, request, key):
        '''Remove and return a value from the Django session.

        Args:
            request: Django HTTP request.
            key:     Logical key name passed through :meth:`get_session_key`.

        Returns:
            The stored value, or ``None`` if the key is absent.
        '''
        return request.session.pop(self.get_session_key(key), None)

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
