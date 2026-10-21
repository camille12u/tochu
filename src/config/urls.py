from django.contrib import admin
from django.urls import path, include

from .views import TopPageView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('accounts/', include('accounts.urls')),
    path('learning/', include('learning.urls')),
    path('', TopPageView.as_view(), name='top'),
]
