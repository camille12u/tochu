from django.test import TestCase

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