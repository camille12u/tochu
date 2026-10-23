from allauth.account.models import EmailAddress, Login
from allauth.account.internal.stagekit import LOGIN_SESSION_KEY
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import User, Profile
from .views import EmailVerificationStage


class UserManagerTests(TestCase):
    """User作成テスト"""
    def test_create_user_with_valid_credentials(self):
        test_email = 'sample@mail.com'
        test_password = 'django_123'
        test_user = User.objects.create_user(test_email, test_password)

        self.assertEqual(test_user.email, test_email)
        self.assertTrue(test_user.check_password(test_password)) # パスワードが同じならTrueを返す
        self.assertNotEqual(test_user.password, test_password)
        self.assertEqual(Profile.objects.filter(user=test_user).count(), 1)

    def test_create_superuser_sets_required_flags(self):
        test_email = 'root@mail.com'
        test_password = 'root_pass'
        superuser = User.objects.create_superuser(test_email, test_password)

        self.assertIs(superuser.is_staff, True)
        self.assertIs(superuser.is_superuser, True)
        self.assertIs(superuser.is_active, True)

    def test_create_superuser_with_is_staff_false_raises_value_error(self):
        test_email = 'root@mail.com'
        test_password = 'root_pass'

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                test_email, test_password, is_staff=False
                )

    def test_create_superuser_with_is_superuser_false_raises_value_error(self):
        test_email = 'root@mail.com'
        test_password = 'root_pass'

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                test_email, test_password, is_superuser=False
                )

    def test_create_superuser_with_is_active_false_raises_value_error(self):
        test_email = 'root@mail.com'
        test_password = 'root_pass'

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                test_email, test_password, is_active=False
                )

    def test_create_user_without_email_raises_value_error(self):
        test_email = ''
        test_password = 'django_123'
        with self.assertRaises(ValueError):
            User.objects.create_user(test_email, test_password)

        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)

    def test_create_user_without_password_raises_value_error(self):
        test_email = 'sample@mail.com'
        test_password = ''
        with self.assertRaises(ValueError):
            User.objects.create_user(test_email, test_password)

        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)

    def test_create_user_with_duplicate_email_raises_integrity_error(self):
        User.objects.create_user('samle@mail.com', 'django_123')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user('samle@mail.com', 'django_456')

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Profile.objects.count(), 1)

    def test_updating_user_preserves_profile(self):
        test_user = User.objects.create_user('sample@mail.com', 'django_123')
        profile = test_user.profile

        # 作成直後は空欄のため、値を設定
        profile.name = 'tanaka'
        profile.bio = 'エンジニアを目指しています。'
        profile.save()

        # 比較用の変数に入れる(期待値)
        expected_id = profile.pk
        expected_name = profile.name
        expected_bio = profile.bio

        test_user.set_password('django_456')
        test_user.save()

        self.assertEqual(Profile.objects.count(), 1)
        actual = Profile.objects.get(user=test_user)
        self.assertEqual(actual.id, expected_id)
        self.assertEqual(actual.name, expected_name)
        self.assertEqual(actual.bio, expected_bio)


class ResendingEmailViewTests(TestCase):
    # ログイン途中の情報がない状態でPOSTすると、ログイン画面へ転送される検証
    def test_post_without_pending_login_redirects_to_login(self):
        path = reverse('resend_email')
        response = self.client.post(path)

        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)

    # GETは許可されず、メールも送信されない検証
    def test_get_is_not_allowed_and_sends_no_email(self):
        path = reverse('resend_email')
        response = self.client.get(path)
        expected = 405

        self.assertEqual(response.status_code, expected)
        self.assertEqual(len(mail.outbox), 0)

    # 有効なログイン途中情報がある状態でPOSTすると、確認メールを再送する
    def test_post_with_valid_pending_login_resends_verification_email(self):
        # 再送対象のユーザーと、そのユーザーに属する未確認メール情報を用意する
        test_email = 'sample@example.com'
        test_password = 'd_jan_go'
        test_user = User.objects.create_user(test_email, test_password)
        unconfirmed_mail = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=False,
        )

        # 現在の段階をメール確認待ちとした、ログイン途中情報を作る
        login = Login(
            user=unconfirmed_mail.user,
            email=unconfirmed_mail.email,
            state={
                'stages': {
                    'current': EmailVerificationStage.key
                    },
                }
            )

        # 通常ログインによる初回送信と送信制限を避けるため、途中情報を直接セッションに保存する
        test_session = self.client.session
        test_session[LOGIN_SESSION_KEY] = login.serialize()
        test_session.save()

        # 途中情報を保存したクライアントから再送を要求する
        resend_url = reverse('resend_email')
        response = self.client.post(resend_url)

        # 結果の検証
        self.assertRedirects(response, '/accounts/confirm-email/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_email])

    # 対象メールがすでに確認済みかつログインしていない場合、
    # 再送せずにログイン画面に遷移することをテスト
    def test_post_with_verified_email_sends_no_email(self):
        # 再送対象のユーザーと、そのユーザーに属する確認メール情報を用意する
        test_email = 'sample@example.com'
        test_password = 'd_jan_go'
        test_user = User.objects.create_user(test_email, test_password)
        confirmed_mail = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        # 先行する段階を処理済みとし、メール確認待ちの途中情報を再現する
        login = Login(
            user=confirmed_mail.user,
            email=confirmed_mail.email,
            state={
                'stages': {
                    'current': EmailVerificationStage.key,
                    'login_by_code': {
                        'handled': True
                        },
                    'verify_phone': {
                        'handled': True
                        },
                    },
                }
            )

        # 通常ログインによる初回送信と送信制限を避けるため、途中情報を直接セッションに保存する
        test_session = self.client.session
        test_session[LOGIN_SESSION_KEY] = login.serialize()
        test_session.save()

        # 確認済みメールへの再送を拒否することを確認する
        resend_url = reverse('resend_email')
        response = self.client.post(resend_url)

        # 検証
        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)