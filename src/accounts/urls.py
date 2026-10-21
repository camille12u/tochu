from django.urls import path

from .views import ResendingEmailView

urlpatterns = [
    path('resend_email/', ResendingEmailView.as_view(), name='resend_email')
]
