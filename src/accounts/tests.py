from django.test import TestCase
from django.db import IntegrityError, transaction

from .models import User, Profile


class UserManagerTests(TestCase):
    def test_create_user_with_valid_credentials(self):
        test_email = 'sample@mail.com'
        test_password = 'django_123'
        user = User.objects.create_user(test_email, test_password)

        self.assertEqual(user.email, test_email)
        self.assertTrue(user.check_password(test_password))
        self.assertNotEqual(user.password, test_password)
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

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