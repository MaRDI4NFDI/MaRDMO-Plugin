'''URL configuration for the MaRDMO plugin.

Registers the three endpoints used for the background export.  Paths are
relative to the prefix under which the instance includes ``MaRDMO.urls`` in its
``config/urls.py`` (e.g. ``services/``); MaRDMO itself only refers to them by name.

- ``progress/<job_id>/``        — ``show_progress``: render the live progress page
- ``progress/<job_id>/status/`` — ``get_progress``: JSON progress for polling
- ``success/<job_id>/``         — ``show_success``: render the export result page
'''

from django.urls import path
from .views import get_progress, show_progress, show_success

urlpatterns = [
    path("progress/<str:job_id>/", show_progress, name="show_progress"),
    path("progress/<str:job_id>/status/", get_progress, name="get_progress"),
    path("success/<str:job_id>/", show_success, name="show_success"),
]
