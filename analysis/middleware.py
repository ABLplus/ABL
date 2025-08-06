# analysis/middleware.py

from django.utils import timezone

class DailyCountersMiddleware:
    """
    Resets daily counters and breaks streaks on the first request of each
    calendar day for authenticated users.

    Relies on Profile.reset_if_new_day() to:
      • zero last_attempt_count
      • reset streak_days if yesterday’s target wasn’t met
      • update last_seen_on to today
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            try:
                user.profile.reset_if_new_day()
            except AttributeError:
                # If the Profile row doesn’t exist yet, skip gracefully
                pass

        return self.get_response(request)
