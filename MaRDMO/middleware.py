'''MaRDMO's rendering of LaTeX in RDMO's interview, added to RDMO's page by a middleware.

The formula and symbol questions show the TeX typed rendered below their
field (MaRDMO/js/math-preview.js, #190).  The script comes into RDMO's
interview page here, before its ``</body>``, as the Django Debug Toolbar adds
its own: MaRDMO replaces no template of RDMO, so it does not depend on the
order of ``INSTALLED_APPS``, and another plugin may replace the interview's
template.  Every other response stays as it is.  The settings name it::

    MIDDLEWARE += ['MaRDMO.middleware.InterviewMathPreview']

Without that line ``manage.py check`` warns (:func:`check_middleware`).
'''
from django.conf import settings
from django.core.checks import Warning as CheckWarning
from django.template.loader import render_to_string

PATH = 'MaRDMO.middleware.InterviewMathPreview'
# RDMO's interview page (rdmo.projects.urls)
INTERVIEW = 'project_interview'
SCRIPTS = 'MaRDMO/partials/_math_preview.html'
_BODY_END = b'</body>'


class InterviewMathPreview:
    '''Add MaRDMO's rendering of LaTeX to RDMO's interview page (see the module).'''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self.applies(request, response):
            position = response.content.rfind(_BODY_END)
            scripts = render_to_string(SCRIPTS, request=request).encode(response.charset)
            response.content = response.content[:position] + scripts + response.content[position:]
            if response.has_header('Content-Length'):
                response['Content-Length'] = str(len(response.content))
        return response

    @staticmethod
    def applies(request, response):
        '''Whether *response* is RDMO's interview page as HTML, unchanged so far.'''
        match = getattr(request, 'resolver_match', None)
        return (match is not None and match.url_name == INTERVIEW and request.method == 'GET'
                and response.status_code == 200 and not response.streaming
                and not response.has_header('Content-Encoding')
                and response.get('Content-Type', '').startswith('text/html')
                and _BODY_END in response.content)


def check_middleware(app_configs=None, **kwargs):
    '''Warn when the settings do not name the middleware: the interview would not render LaTeX.'''
    if PATH in getattr(settings, 'MIDDLEWARE', []):
        return []
    return [CheckWarning(
        'MaRDMO\'s middleware is not in MIDDLEWARE: the LaTeX of formulas and symbols is not rendered '
        'in the interview.',
        hint=f"Add MIDDLEWARE += ['{PATH}'] to the settings (config/settings/local.py).",
        id='MaRDMO.W001',
    )]
