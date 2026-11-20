'''URL configuration for the MaRDMO plugin.

Registers the endpoints used for the background export and the preview.  Paths are
relative to the prefix under which the instance includes ``MaRDMO.urls`` in its
``config/urls.py`` (e.g. ``services/``); MaRDMO itself only refers to them by name.

- ``progress/<job_id>/``        — ``show_progress``: render the live progress page
- ``progress/<job_id>/status/`` — ``get_progress``: JSON progress for polling
- ``success/<job_id>/``         — ``show_success``: render the export result page
- ``reuse/<project_id>/``       — ``reuse_portal_item``: the preview's "Use this item" (#141)
- ``tex-check/``                 — ``check_tex``: the portal's verdict on a formula typed into the interview (#190)
'''

from django.urls import path
from .views import check_tex, get_progress, reuse_portal_item, show_progress, show_success

urlpatterns = [
    path("progress/<str:job_id>/", show_progress, name="show_progress"),
    path("progress/<str:job_id>/status/", get_progress, name="get_progress"),
    path("success/<str:job_id>/", show_success, name="show_success"),
    path("reuse/<int:project_id>/", reuse_portal_item, name="reuse_portal_item"),
    path("tex-check/", check_tex, name="tex_check"),
]
