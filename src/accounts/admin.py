from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin


User = get_user_model()


class TochuUserAdmin(UserAdmin):
    list_display = (
        'email',
        'is_active',
        'is_staff',
        'is_superuser'
        )
    search_fields = ('email',)
    ordering = ('email',)


admin.site.register(User, TochuUserAdmin)