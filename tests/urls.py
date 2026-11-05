'''URL configuration of an RDMO app with MaRDMO (as in the README), for pages rendered in tests.'''
from django.contrib import admin
from django.urls import include, path
from rdmo.core.views import about, api, home

urlpatterns = [
    path('', home, name='home'),
    path('about/', about, name='about'),
    path('api/', api, name='api'),
    path('', include('rdmo.core.urls')),
    path('api/v1/', include('rdmo.core.urls.v1')),
    path('admin/', admin.site.urls),
    path('services/', include('MaRDMO.urls')),
]
