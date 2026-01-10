from django.contrib import admin
from .models import Profile, Subscription, UserDailyStats
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'mobile_number')
    search_fields = ('user__username', 'mobile_number')


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "total_attempts_booked",
        "total_attempts_limit",
        "daily_attempts_booked",
        "daily_attempts_limit",
        "expiry_datetime",
        "start_datetime",
    )
    list_filter = ("plan",)
    search_fields = ("user__username",)
    date_hierarchy = "start_datetime"
    ordering = ("-start_datetime",)

@admin.register(UserDailyStats)
class UserDailyStatsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "total_attempts",
        "total_correct",
        "total_wrong",
        "sureshot_attempts",
        "applied_attempts",
        "guesswork_attempts",
    )
    list_filter = ("date",)
    search_fields = ("user__username",)
    ordering = ("-date",)
