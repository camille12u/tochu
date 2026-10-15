from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser

from .managers import UserManager

class User(AbstractUser):
    username = None
    email = models.EmailField(max_length=254, unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    name = models.CharField(max_length=30, blank=True)
    bio = models.TextField(max_length=500, blank=True)