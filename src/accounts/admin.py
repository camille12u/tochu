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
    fieldsets = (
        (
            '認証情報', {
                'fields': ('email', 'password')
            }
        ),
        (
            '権限', {
                'fields': (
                    'is_active', 
                    'is_staff', 
                    'is_superuser',
                    'groups',
                    'user_permissions'
                    )
            }
        )
    )
    add_fieldsets = (
        (
            'ユーザー情報', {
                'fields': ('email', 'password1', 'password2')
            }
        ),
    )


admin.site.register(User, TochuUserAdmin)