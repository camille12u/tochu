from django.urls import path

from .views import ResendingEmailView, TochuEmailVerificationSentView

urlpatterns = [
    # 再送POST用のURL
    path('resend_email/', ResendingEmailView.as_view(), name='resend_email'),

    # 案内画面GET用のURL
    path(
        'confirm-email/', 
        TochuEmailVerificationSentView.as_view(),
        name='account_email_verification_sent'
        ),
]
