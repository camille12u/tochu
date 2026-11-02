import time
from unittest.mock import patch

from allauth.account import app_settings
from allauth.account.models import EmailAddress, Login
from allauth.account.internal.stagekit import LOGIN_SESSION_KEY
from django.contrib.messages import WARNING, get_messages
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.test.utils import override_settings
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
    # セッション内の途中情報がない状態でPOSTすると、ログイン画面へ転送される検証
    def test_post_without_pending_login_redirects_to_login(self):
        path = reverse('resend_email')
        response = self.client.post(path, follow=True)
        # follow=Trueを与えると、クライアントはすべてのリダイレクトを辿り、
        # 途中のURLとステータスコードのタプルが、レスポンスオブジェクトの、
        # redirect_chain 属性に追加される
        # print(response.redirect_chain)

        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)

        # 警告メッセージがあることを検証
        result = any(
            msg.level == WARNING for msg in get_messages(response.wsgi_request)
            )
        self.assertTrue(result)

        # 警告メッセージがログイン画面に表示されているか検証
        expected_message = '確認手続きを続けられませんでした。もう一度ログインしてください。'
        self.assertContains(response, expected_message)

    # 登録済みメールで再登録を試み、案内画面から再送した場合の動作を検証
    def test_resend_after_signup_with_existing_email_redirects_to_top(self):
        # 再送対象のユーザーと、そのユーザーに属する確認メール情報を用意する
        test_email = 'sampleee@example.com'
        test_password = 'dddjango_123'
        test_user = User.objects.create_user(test_email, test_password)
        confirmed_mail = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        # 同じメールアドレスを登録フォームにPOSTする
        signup_url = reverse('account_signup')
        response = self.client.post(signup_url, data={
            'email': test_email,
            'password1': test_password,
            'password2': test_password,
        })

        # 確認メール送信画面へ遷移したか検証
        self.assertRedirects(response, '/accounts/confirm-email/')

        # 同じメールアドレスのユーザーが1件のままを検証
        user_count = User.objects.filter(email=test_email).count()
        self.assertEqual(user_count, 1)
        mail_count_before_resend = len(mail.outbox) # 1

        # メール本文にログインURLとパスワードリセットURLがあることを検証
        # print(mail.outbox[-1].body)
        login_url = f'http://testserver{reverse('account_login')}'
        password_reset_url = f'http://testserver{reverse('account_reset_password')}'
        self.assertIn(login_url, mail.outbox[-1].body)
        self.assertIn(password_reset_url, mail.outbox[-1].body)

        # 再送URLへPOST
        resend_url = reverse('resend_email')
        response = self.client.post(resend_url, follow=True)

        # トップページに遷移、メール件数が増えていないことを検証
        self.assertRedirects(response, '/')
        self.assertEqual(len(mail.outbox), mail_count_before_resend)

        # 警告メッセージが存在し、表示されていることを確認
        result = any(
            msg.level == WARNING for msg in get_messages(response.wsgi_request)
            )
        self.assertTrue(result)
        expected_message = '確認手続きを続けられませんでした。ログイン、または会員登録からやり直してください'
        self.assertContains(response, expected_message)


    # セッション内の途中情報が期限切れの場合、再送しないことを検証
    def test_post_with_expired_pending_login_redirects_to_login(self):
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
        # 許可時間を1秒超えた過去の時刻にし、期限切れを再現する
        login = Login(
            user=unconfirmed_mail.user,
            email=unconfirmed_mail.email,
            initiated_at=time.time() - (app_settings.LOGIN_TIMEOUT + 1), 
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
        response = self.client.post(resend_url, follow=True)

        # 結果の検証
        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)

        # ログイン画面に期待するメッセージが表示されるか検証
        expected = '確認手続きを続けられませんでした。もう一度ログインしてください。'
        self.assertContains(response, expected)

    # GETは許可されず、メールも送信されない検証
    def test_get_is_not_allowed_and_sends_no_email(self):
        path = reverse('resend_email')
        response = self.client.get(path)
        expected = 405

        self.assertEqual(response.status_code, expected)
        self.assertEqual(len(mail.outbox), 0)


    # 再送だけでは未確認・未ログインの状態が維持され、
    # 再送メールのリンクで所有確認後、ログインして学習記録一覧を利用できることを検証
    def test_user_can_confirm_resent_email_and_access_log_list(self):
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

        # 再送しただけでは、メール確認もログインも完了しないことを検証
        unconfirmed_mail.refresh_from_db()
        self.assertFalse(unconfirmed_mail.verified)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        # 確認メールのリンクを取得
        values = mail.outbox[-1].body.splitlines()
        target_url = [value for value in values if '/accounts/confirm-email/' in value]
        url_idx = target_url[0].find('http')
        resend_email_url = target_url[0][url_idx:].split()[0]

        # メール確認が完了し、ログインができ一覧画面に遷移することを検証
        response = self.client.post(resend_email_url)
        unconfirmed_mail.refresh_from_db()
        self.assertTrue(unconfirmed_mail.verified)

        login_url = reverse('account_login')
        response = self.client.post(
            login_url, 
            data={'login': test_email, 'password': test_password}, 
            follow=True
            )
        # print(response.redirect_chain)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertRedirects(response, '/learning/')
        self.assertEqual(response.status_code, 200)

    # 対象メール情報を取得できない場合、ログイン画面に遷移
    @patch('accounts.views.get_address_for_login', return_value=None)
    def test_post_without_target_email_redirects_to_login(
        self, mock_get_address_for_login
        ):
        # 再送対象のユーザーと、そのユーザーに属する未確認メール情報を用意する
        test_email = 'sample@example.com'
        test_password = 'd_jan_go'
        test_user = User.objects.create_user(test_email, test_password)
        unconfirmed_mail = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=False,
        )

        # 先行する段階を処理済みとし、メール確認待ちの途中情報を再現する
        login = Login(
            user=unconfirmed_mail.user,
            email=unconfirmed_mail.email,
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

        # 途中情報を保存したクライアントから再送を要求する
        resend_url = reverse('resend_email')
        response = self.client.post(resend_url, follow=True)

        # ログイン画面に遷移、メールが送信されていない、メッセージが適切に表示されるか検証
        message = '確認手続きを続けられませんでした。もう一度ログインしてください。'
        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(response, message)

        mock_get_address_for_login.assert_called_once()

    # 対象メールがすでに確認済みかつログインしていない場合、
    # 再送せずにログイン画面に遷移することを検証
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
        response = self.client.post(resend_url, follow=True)

        # 検証
        self.assertRedirects(response, '/accounts/login/')
        self.assertEqual(len(mail.outbox), 0)

        # ログイン画面に遷移することを検証
        message = 'メールアドレスの確認はすでに完了しています。'
        self.assertContains(response, message)

    # ログイン済みかつメール確認済みで、古いタブから再送POSTした場合、ログイン状態を維持し
    # 学習一覧画面に遷移することを検証
    def test_post_with_verified_logged_in_user_redirects_to_log_list(self):
        # テストユーザー作成
        email = 'tochu_user@example.com'
        password = 'django_4545'
        test_user = User.objects.create_user(email, password)

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        # ログイン処理
        login_url = reverse('account_login')
        response = self.client.post(login_url, data={
            'login': confirmed_mail_user.email,
            'password': password,
        })

        # ログイン成功し、学習記録一覧へ遷移することを確認
        self.assertRedirects(response, '/learning/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        # 再送URLへ直接POST(再送ボタンを押す)
        url = reverse('resend_email')
        response = self.client.post(url)

        # 次の4点を検証。
        # 一覧へ直接転送される。メール0通。ログイン状態が維持される。警告なし。
        self.assertRedirects(response, '/learning/')
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        result = any(
            msg.level == WARNING for msg in get_messages(response.wsgi_request)
            )
        self.assertFalse(result)


    # 途中情報はあるが、対象のユーザーを取得できない場合、トップページへ遷移することを検証
    def test_post_with_deleted_user_redirects_to_top(self):
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

        # 対象のユーザーを削除
        test_user.delete()

        # 対象ユーザーを取得できないため、再送を拒否
        resend_url = reverse('resend_email')
        response = self.client.post(resend_url, follow=True)

        # トップページに遷移できたか、メールが0件か検証
        self.assertRedirects(response, '/')
        self.assertEqual(len(mail.outbox), 0)

        # 案内画面に期待するメッセージが表示されるか検証
        expected = '確認手続きを続けられませんでした。ログイン、または会員登録からやり直してください'
        self.assertContains(response, expected)


    # 送信制限の際に確認メール送信済みの案内画面に警告メッセージが表示されるか検証
    # このテスト中だけキャッシュ設定を変更し、他のテストの送信履歴と分離する。
    # 終了後は元の設定に戻るが、専用キャッシュのデータが自動で消えるわけではない。
    @override_settings(
        CACHES={
            # allauthの送信制限が使用する標準キャッシュを設定する。
            'default': {
                # データをプロセス内のメモリに保存する仕組みを使う。
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                # メモリ内の保存先を識別する名前。ファイルのパスではなく、他のテストと分けるための名前。
                'LOCATION': 'test-email-resend-rate-limit',
            },
        }
    )
    def test_warning_message_is_displayed_when_a_sending_limit(self):
        # 専用キャッシュに前の実行履歴が残っていても、空の状態から検証を始める。
        # 1回目の送信履歴で2回目を制限するため、2回のPOSTの間では消さない。
        cache.clear()
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

        # 正常な遷移先、メールの件数、宛先メールアドレスの結果の検証
        self.assertRedirects(response, '/accounts/confirm-email/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_email])

        # 送信制限
        expected = '続けて再送することはできません。しばらく待ってから、もう一度お試しください。'
        response = self.client.post(resend_url, follow=True)
        self.assertRedirects(response, '/accounts/confirm-email/')
        self.assertContains(response, expected)
        self.assertEqual(len(mail.outbox), 1)

    # CSRFトークンなしの再送POSTが拒否されることを検証
    def test_post_without_csrf_token_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        resend_url = reverse('resend_email')
        response = csrf_client.post(resend_url)
        expected_status_code = 403

        self.assertEqual(response.status_code, expected_status_code)
        self.assertEqual(len(mail.outbox), 0)

    # 正しいトークンを付ければ再送できることを検証
    def test_post_with_valid_csrf_token_resends_verification_email(self):
        # 再送対象のユーザーと、そのユーザーに属する未確認メール情報を用意する
        test_email = 'csrf-test@example.com'
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
        csrf_client = Client(enforce_csrf_checks=True)
        test_session = csrf_client.session
        test_session[LOGIN_SESSION_KEY] = login.serialize()
        test_session.save()

        path = reverse('account_email_verification_sent')
        resposnse_with_cookeie = csrf_client.get(path)
        csrf_token = resposnse_with_cookeie.cookies['csrftoken'].value

        resend_url_post = reverse('resend_email')
        response_post = csrf_client.post(
            resend_url_post,
            data={'csrfmiddlewaretoken': csrf_token},
            )

        # 再送できたことを検証
        self.assertRedirects(response_post, '/accounts/confirm-email/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_email])


class SignupViewTests(TestCase):
    # 登録のPOST処理によってユーザーが作られることを検証
    def test_post_with_valid_data_creates_user(self):
        test_mail = 'user@example.com'
        test_password = 'test_123_django'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # 登録の後に確認メール案内画面に遷移することを検証
        expected_url = reverse('account_email_verification_sent')
        self.assertRedirects(response, expected_url)

        # 入力したメールアドレスのユーザーが1件作成されたことを検証
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 1)

        # 確認メールの件数と宛先を検証
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_mail])

    # パスワードが不一致の場合、ユーザーが作成されないことを検証
    def test_password_not_match(self):
        test_mail = 'user@example.com'
        test_password = 'test_123_django'
        test_unfair_password = 'test_django'

        # パスワードが不一致でPOSTリクエストを実行
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url,
            data={
                'email': test_mail,
                'password1': test_password,
                'password2': test_unfair_password,
            }
        )

        # ステータスコードが200
        # 入力したメールアドレスで、ユーザが作成されない
        # メール送信が0
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # パスワードの不一致によるエラーメッセージが表示されるか検証
        expected_msg = '同じパスワードを入力してください。'
        self.assertContains(response, expected_msg)

    # メールアドレスの形式が不正な場合に、登録を拒否することを検証
    def test_invalid_email_address(self):
        test_mail = 'userexample.com'
        test_password = 'test_123_django'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # ステータスコードが200
        # ユーザが作成されず、メールも0件
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # 不正なメールアドレスによるエラーメッセージが表示されるか検証
        # print(response.context['form'].errors) でdjangoのフォームのエラーを確認
        error_message = '有効なメールアドレスを入力してください。'
        self.assertContains(response, error_message)

    # 短すぎるパスワードでは登録できないことを検証
    def test_password_too_short(self):
        test_mail = 'user@example.com'
        test_password = 'test_00'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # ステータスコードが200
        # ユーザが作成されず、メールも0件
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # 短すぎるパスワードによるエラーメッセージが表示されるか検証
        error_msg = 'このパスワードは短すぎます。最低 8 文字以上必要です。'
        self.assertContains(response, error_msg)

    # 一般的なパスワードでは登録できないことを検証
    def test_password_too_common(self):
        test_mail = 'user@example.com'
        test_password = 'password'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # ステータスコードが200
        # ユーザが作成されず、メールも0件
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # 一般的すぎるパスワードによるエラーメッセージが表示されるか検証
        error_msg = 'このパスワードは一般的すぎます。'
        self.assertContains(response, error_msg)

    # 数字のみのパスワードで登録できないことを検証
    def test_password_only_numbers(self):
        test_mail = 'user@example.com'
        test_password = '45451919'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # ステータスコードが200
        # ユーザが作成されず、メールも0件
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # 数字だけのパスワードによるエラーメッセージが表示されるか検証
        error_msg = 'このパスワードは数字しか使われていません。'
        self.assertContains(response, error_msg)

    # メールアドレスに似すぎるパスワードでは登録できないことを検証
    def test_password_too_similar_to_email(self):
        test_mail = 'coco0707@example.com'
        test_password = 'coco0707'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )
        # print(response.context['form'].errors)

        # ステータスコードが200
        # ユーザが作成されず、メールも0件
        self.assertEqual(response.status_code, 200)
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 0)
        self.assertEqual(len(mail.outbox), 0)

        # メールアドレスに似すぎるパスワードのエラーメッセージが表示されるか検証
        error_msg = 'このパスワードは email と似すぎています。'
        self.assertContains(response, error_msg)


class LoginViewTests(TestCase):
    # メール確認済みのユーザーが、正しい情報でログインできること
    def test_email_confirmed_user_can_log_in_successfully(self):
        test_user = User.objects.create_user(
            email='test_user@example.com',
            password='django_123'
            )

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        login_url = reverse('account_login')
        response = self.client.post(login_url, data={
            'login': confirmed_mail_user.email,
            'password': 'django_123',
        })

        log_list_url = reverse('log_list')
        self.assertRedirects(response, log_list_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        # print(response.wsgi_request.user, response.wsgi_request.user.is_authenticated)


    # メール確認済みのユーザーが、間違ったパスワードではログインできないことを検証
    def test_cannot_login_with_an_incorrect_password(self):
        email = 'test_user@example.com'
        password = 'django_123'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        login_url = reverse('account_login')
        response = self.client.post(login_url, data={
            'login': confirmed_mail_user.email,
            'password': 'Python_123',
        })
        error_msg = '入力されたメールアドレスもしくはパスワードが正しくありません。'
        # print(response.context['form'].errors)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, error_msg)
        # print(response.wsgi_request.user, response.wsgi_request.user.is_authenticated)

    # メール未確認のユーザーが、正しいパスワードでもログインを完了できないことを検証
    def test_user_with_unverified_email_cannot_log_in(self):
        email = 'test_user@example.com'
        password = 'django_123'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール未確認済みユーザーを作成
        unconfirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=False,
        )

        login_url = reverse('account_login')
        response = self.client.post(login_url, data={
            'login': unconfirmed_mail_user.email,
            'password': password,
        })

        email_confirm_url = reverse('account_email_verification_sent')
        self.assertRedirects(response, email_confirm_url)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # メール未確認のユーザーが、学習記録一覧へ直接アクセスしても利用できないことを検証
    def test_user_with_unverified_email_cannot_access_log_list(self):
        email = 'test_user@example.com'
        password = 'django_123'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール未確認済みユーザーを作成
        unconfirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=False,
        )

        login_url = reverse('account_login') # /accounts/login/
        response_post = self.client.post(
            login_url, data={
                'login': unconfirmed_mail_user.email,
                'password': password
            })

        email_confirm_url = reverse('account_email_verification_sent')
        self.assertRedirects(response_post, email_confirm_url)

        log_list_url = reverse('log_list') # /learning/
        response_get = self.client.get(log_list_url)
        # print(f'STATUS_CODE : {response_get.status_code}')
        # print(f'URL: {response_get.url}, {type(response_get.url)}')
        expected_url = login_url + '?next=' + log_list_url
        self.assertEqual(response_get.status_code, 302)
        self.assertEqual(response_get.url, expected_url)


class LogoutViewTests(TestCase):
    """ログアウト処理と、ログアウト後のアクセス制限を検証するクラス"""

    # ログアウト処理が正常に動作するか検証
    def test_post_logs_out_user_and_redirects_to_top(self):
        email = 'logout_user@example.com'
        password = 'django_123'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        login_url = reverse('account_login') # /accounts/login/
        response = self.client.post(
            login_url, data={
                'login': confirmed_mail_user.email,
                'password': password
            })

        # ログインでき、学習一覧画面に遷移することを検証
        log_list_url = reverse('log_list')
        self.assertRedirects(response, log_list_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        # ログアウトをし、トップページに遷移することを検証
        logout_url = reverse('account_logout')
        response = self.client.post(logout_url)
        self.assertRedirects(response, '/')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # ログアウト後のユーザーは学習記録一覧を利用できないことを検証
    def test_logged_out_user_cannot_access_log_list(self):
        email = 'logout_user@example.com'
        password = 'django_123'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        login_url = reverse('account_login') # /accounts/login/
        response = self.client.post(
            login_url, data={
                'login': confirmed_mail_user.email,
                'password': password
            })

        # ログインでき、学習一覧画面に遷移することを検証
        log_list_url = reverse('log_list')
        self.assertRedirects(response, log_list_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        # ログアウトをし、トップページに遷移することを検証
        logout_url = reverse('account_logout')
        response = self.client.post(logout_url)
        self.assertRedirects(response, '/')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        # 学習記録一覧にアクセスできずに、ログイン画面に遷移することを検証
        response = self.client.get(log_list_url)
        url = login_url + '?next=' + log_list_url
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, url)


class EmailConfirmationViewTests(TestCase):
    """メール所有確認テスト
    
    確認処理、確認完了後の利用、無効・期限切れリンクへの対応を検証する
    """
    # 確認メールのリンクからメール所有確認を完了するテスト
    def test_valid_confirmation_link_verifies_email(self):
        test_mail = 'user123@example.com'
        test_password = 'test_123_django'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # 登録の後に確認メール案内画面に遷移することを検証
        expected_url = reverse('account_email_verification_sent')
        self.assertRedirects(response, expected_url)

        # 入力したメールアドレスのユーザーが1件作成されたことを検証
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 1)

        # 確認メールの件数と宛先を検証
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_mail])

        # 送信されたメールの本文からメール確認用のURLのみを取得
        # print(f'mail: {mail.outbox[0].body}')
        confirm_mail = mail.outbox[0].body.splitlines()
        for value in confirm_mail:
            if '/accounts/confirm-email/' in value:
                confirm_mail_url = value

        # print(f'メール確認URL: {confirm_mail_url}')
        http_idx = confirm_mail_url.find('http')
        confirm_mail_url = confirm_mail_url[http_idx:].split()[0]
        # print(confirm_mail_url)

        # メール確認リンクをGETリクエストで成功するか検証
        response = self.client.get(confirm_mail_url)
        self.assertEqual(response.status_code, 200)

        # DBからtest_userのemailを取得
        email = EmailAddress.objects.filter(email=test_mail).get()
        self.assertFalse(email.verified)

        # 同じ確認URLへPOSTし、verifiedがTrueになることを検証
        response = self.client.post(confirm_mail_url)
        email.refresh_from_db() # DBの最新状態をにする
        self.assertTrue(email.verified)

    # 確認完了後に、正しい情報でログインして学習記録一覧を利用できることを確認
    def test_user_can_log_in_and_access_log_list_after_email_confirmation(self):
        test_mail = 'user456@example.com'
        test_password = 'test_456_django'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # 登録の後に確認メール案内画面に遷移することを検証
        expected_url = reverse('account_email_verification_sent')
        self.assertRedirects(response, expected_url)

        # 入力したメールアドレスのユーザーが1件作成されたことを検証
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 1)

        # 確認メールの件数と宛先を検証
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_mail])

        # 送信されたメールの本文からメール確認用のURLのみを取得
        confirm_mail = mail.outbox[0].body.splitlines()
        for value in confirm_mail:
            if '/accounts/confirm-email/' in value:
                confirm_mail_url = value

        http_idx = confirm_mail_url.find('http')
        confirm_mail_url = confirm_mail_url[http_idx:].split()[0]

        # メール確認リンクをGETリクエストで成功するか検証
        response = self.client.get(confirm_mail_url)
        self.assertEqual(response.status_code, 200)

        # DBからtest_userのemailを取得
        email = EmailAddress.objects.filter(email=test_mail).get()
        self.assertFalse(email.verified)

        # 同じ確認URLへPOSTし、verifiedがTrueになることを検証
        response = self.client.post(confirm_mail_url)
        email.refresh_from_db() # DBの最新状態をにする
        self.assertTrue(email.verified)

        # ログインして学習記録一覧に遷移することができる検証
        login_url = reverse('account_login')
        response = self.client.post(
            login_url, data={
                'login': test_mail,
                'password':test_password
                })
        self.assertRedirects(response, '/learning/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.get('/learning/')
        self.assertEqual(response.status_code, 200)

    # 無効なメール確認リンク(キーが正しくない)では、所有確認が完了しないことを検証
    def test_invalid_confirmation_link_does_not_verify_email(self):
        email = 'django_user@example.com'
        password = 'un_un_1919'
        test_user = User.objects.create_user(
            email=email,
            password=password
            )

        # メール未確認済みユーザーを作成
        unconfirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=False,
        )

        # 無効な確認キーを含むURLを作成
        invalid_link = reverse(
            'account_confirm_email', 
            kwargs={
                'key': 'invalid-key'
            }
            )

        response = self.client.get(invalid_link)
        # print(f'ページ本文: {response.content.decode()}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'メールアドレス確認用のリンクが無効か、期限が切れています。')

        # メールが未確認のままなのを検証
        unconfirmed_mail_user.refresh_from_db()
        self.assertFalse(unconfirmed_mail_user.verified)

    # 期限切れの確認リンクでは、所有確認が完了しないことを検証
    def test_expired_confirmation_link_does_not_verify_email(self):
        test_mail = 'user789@example.com'
        test_password = 'test_789_django'

        # 登録処理のURLを取得
        signup_url = reverse('account_signup')
        response = self.client.post(
            signup_url, data={
            'email': test_mail,
            'password1': test_password,
            'password2': test_password,
            }
            )

        # 登録の後に確認メール案内画面に遷移することを検証
        expected_url = reverse('account_email_verification_sent')
        self.assertRedirects(response, expected_url)

        # 入力したメールアドレスのユーザーが1件作成されたことを検証
        number = User.objects.filter(email=test_mail).count()
        self.assertEqual(number, 1)

        # 確認メールの件数と宛先を検証
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [test_mail])

        # 送信されたメールの本文からメール確認用のURLのみを取得
        confirm_mail = mail.outbox[0].body.splitlines()
        for value in confirm_mail:
            if '/accounts/confirm-email/' in value:
                confirm_mail_url = value

        http_idx = confirm_mail_url.find('http')
        confirm_mail_url = confirm_mail_url[http_idx:].split()[0]

        # print(f'リンクの有効期限: {app_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS}日')
        seconds_of_expiry = 86400 * app_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS
        # print(second_of_expiry)

        # 有効期限を1秒過ぎた未来の時刻を設定
        # print(f'現在時刻: {time.time()}')
        expired = time.time() + seconds_of_expiry + 1

        # 期限判定に使う時計を一時的に差し替える
        with patch('django.core.signing.time.time', return_value=expired):
            response = self.client.get(confirm_mail_url)

        self.assertEqual(response.status_code, 200)
        # print(f'内容: {response.content.decode()}')
        self.assertContains(response, 'メールアドレス確認用のリンクが無効か、期限が切れています。')

        # GET後にDBからメール情報を取得しても、verifiedがFalse
        email = EmailAddress.objects.filter(email=test_mail).get()
        self.assertFalse(email.verified)

    # 無効リンクの案内文に、ログインへのリンクが表示されることを検証
    def test_invalid_confirmation_page_provides_login_link(self):
        # 無効な確認キーを含むURLを作成
        invalid_link = reverse(
            'account_confirm_email', 
            kwargs={
                'key': 'invalid-key'
            }
            )

        # GETリクエストが200になることを検証
        response = self.client.get(invalid_link)
        self.assertEqual(response.status_code, 200)

        # print(response.content.decode())
        login_url = reverse('account_login')
        expected_html = f'''
        <p>メールアドレス確認用のリンクが無効か、期限が切れています。 <a href="{login_url}">ログイン</a>から確認手続きをやり直してください。
        また、確認メールを再送するには、ログイン画面で登録したメールアドレスとパスワードを入力してください。メールアドレスが未確認の場合、新しい確認メールを送信します。</p>
        '''
        self.assertContains(response, expected_html, html=True)


class TochuEmailVerificationSentViewTests(TestCase):
    """メール確認済みユーザーテスト
    
    確認済みメールのユーザーでログインし、案内画面へGETして、
    一覧への転送・メール0通・警告なし・ログイン状態維持を検証するクラス
    """

    # メール確認済みかつログイン済みがメール確認案内画面にアクセスすると一覧に遷移することを検証
    def test_verified_logged_in_user_is_redirected_from_verification_sent_page(self):
        # テストユーザー作成
        email = 'tochu_user@example.com'
        password = 'django_4545'
        test_user = User.objects.create_user(email, password)

        # メール確認済みユーザーを作成
        confirmed_mail_user = EmailAddress.objects.create(
            user=test_user,
            email=test_user.email,
            verified=True,
        )

        # ログイン処理
        login_url = reverse('account_login')
        response = self.client.post(login_url, data={
            'login': confirmed_mail_user.email,
            'password': password,
        })

        # ログイン成功し、学習記録一覧へ遷移することを確認
        self.assertRedirects(response, '/learning/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        # 案内画面へGET
        url = reverse('account_email_verification_sent')
        response = self.client.get(url, follow=True) # リダイレクトするからfollow=True
        # print(f'結果: {response.content.decode()}')

        # 一覧画面に遷移、メールが送信されない、ログイン状態が維持されることを検証
        self.assertRedirects(response, '/learning/')
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        # 警告メッセージがないことを検証
        result = any(
            msg.level == WARNING for msg in get_messages(response.wsgi_request)
            )
        self.assertFalse(result)