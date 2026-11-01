from allauth.account.adapter import DefaultAccountAdapter
from allauth.utils import build_absolute_uri
from allauth.core import context
from django.urls import reverse


class TochuAccountAdapter(DefaultAccountAdapter):
    """allauthの登録済み通知メールをTOCHU用に拡張するAdapter。
    
    ログイン画面の絶対URLを作成してテンプレートへ渡し、
    パスワード再設定の案内とあわせてメールを送信する。
    """
    def send_account_already_exists_mail(self, email: str) -> None:
        from allauth.account.internal import flows

        signup_url = flows.signup.get_signup_url(context.request)
        password_reset_url = flows.password_reset.get_reset_password_url(
            context.request
        )
        login_path = reverse('account_login')
        login_url = build_absolute_uri(self.request, login_path)

        ctx = {
            'signup_url': signup_url,
            'login_url': login_url,
            'password_reset_url': password_reset_url,
        }

        self.send_mail(
            template_prefix='account/email/account_already_exists',
            email=email,
            context=ctx
        )