
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.utils import timezone
from tests.models import QuestionLog, TopicAttemptSummary
from tests.models import Test
from django.db.models import Max
from practice.models import PracticeSession
from syllabus.models import *
from django.http import HttpResponseBadRequest
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.contrib import messages
import random

from django.db.models import (
    Sum, F, ExpressionWrapper, DecimalField, Max, Min, FloatField, Q
)
from django.utils import timezone
from syllabus.models import Subject
from django.db.models.functions import Coalesce
from .models import TopicStatus


from practice.models import PracticeSession
from analysis.models import TopicStatus
from syllabus.models import Topic  # adjust if your import path differs

# import your existing PMI function
from practice.views import _compute_and_update_topic_pmi
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model

User = get_user_model()


@staff_member_required
def user_pmi_recalc(request):
    """
    Staff-only utility:
    - Render a dropdown of users (only those with completed PracticeSessions).
    - On submit, recompute PMI for last-N sessions for each topic attempted by that user.
    - Redirect back with a success message and show the updated TopicStatus rows
      with Subject and Section.
    """
    # limit to users who actually have completed sessions
    user_choices = (
        User.objects
        .filter(practicesession__status="completed")
        .distinct()
        .order_by("username")
    )

    selected_user = None
    topic_status_list = []

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        try:
            selected_user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Invalid user selected.")
            return redirect(reverse("analysis:user_pmi_recalc"))

        # All topics this user has attempted (completed sessions only)
        topic_ids = (
            PracticeSession.objects
            .filter(user=selected_user, status="completed")
            .values_list("topic_id", flat=True)
            .distinct()
        )

        # Recompute PMI for each topic
        topics = Topic.objects.filter(id__in=topic_ids).select_related(
            "section", "section__subject"
        )
        for t in topics:
            _compute_and_update_topic_pmi(selected_user, t)

        messages.success(
            request,
            f"PMI recomputed for {topics.count()} topics for user “{selected_user}”."
        )

        # Fetch updated TopicStatus with subject/section for display
        topic_status_list = (
            TopicStatus.objects
            .filter(user=selected_user, topic_id__in=topic_ids)
            .select_related("topic", "section", "subject")  # TopicStatus already stores these
            .order_by("subject__name", "section__name", "topic__name")
        )

        # render the same page with results (no extra redirect needed)
        return render(
            request,
            "analysis/compute_user_pmi.html",
            {
                "user_choices": user_choices,
                "selected_user": selected_user,
                "topic_status_list": topic_status_list,
            },
        )

    # GET — initial render or after redirect without selection
    return render(
        request,
        "analysis/compute_user_pmi.html",
        {"user_choices": user_choices, "selected_user": selected_user}
    )




@require_POST
@login_required
def delete_test(request, test_id):
    """
    Delete a *pending* test (status='pending') that belongs to the user.
    HTMX: returns 204/empty so the row disappears.
    Non-HTMX: redirects back to dashboard with a flash message.
    """
    test = get_object_or_404(Test, pk=test_id, user=request.user)

    if test.status != "pending":
        return HttpResponseForbidden("Only pending tests can be deleted.")

    test.delete()
    messages.success(request, "Pending test deleted.")

    # HTMX request? send empty 204 so client swaps out the row
    if request.headers.get("HX-Request") == "true":
        return HttpResponse(status=204)

    # Fallback for normal POST
    return redirect("dashboard")

@login_required
def test_history_page(request):
    page_number = int(request.GET.get("page", 1))

    qs = (
        Test.objects
        .filter(user=request.user)               # this user only
        .exclude(end_time__isnull=True)          # keep rows where end_time IS NOT NULL
        .order_by("-end_time")                   # most-recent first
    )

    paginator = Paginator(qs, 5)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "analysis/partials/_test_history_page.html",
        {
            "page_obj": page_obj,
        },
    )




@login_required
def test_filter_form(request):
    ttype = request.GET.get("type")
    if ttype == "exam_year":
        ctx = {
            "exams": Exam.objects.all(),
            "years": range(2000, 2024)
        }
        return render(request, "analysis/partials/_exam_year_form.html", ctx)

    elif ttype == "subject":
        ctx = {"subjects": Subject.objects.all()}

        return render(request, "analysis/partials/_subject_form.html", ctx)

    return HttpResponseBadRequest("Unknown test type")

def _get_mode(request):
    """Return session-stored mode or fall back to profile default.
    Also update session if ?mode= is present in the URL."""
    # If the user clicked a switch button with ?mode=..., store it
    mode_param = request.GET.get("mode")
    if mode_param in ("practice", "test"):
        request.session["dash_mode"] = mode_param

    return request.session.get("dash_mode", request.user.profile.mode)


import random
from django.db.models import Sum

# PMI category colors
CATEGORY_TEXT_CLASS = {
    "strong":     "text-green-700 dark:text-green-300",
    "transition": "text-yellow-600 dark:text-yellow-300",
    "weak":       "text-red-700 dark:text-red-300",
}

# Tier-based styles (uniform casing + same base size)
TIER_TEXT_CLASS = {
    "most":    "text-base font-extrabold tracking-wide",  # removed uppercase
    "general": "text-base font-semibold",
    "rare":    "text-base italic",
    "never":   "text-base opacity-80",
}

# Tier symbols and labels
TIER_SYMBOL = {
    "most":    "★",  # Most Asked
    "general": "■",  # Generally Asked
    "rare":    "▲",  # Rarely Asked
    "never":   "●",  # Never Asked
}

TIER_LABEL = {
    "most":    "Most Asked",
    "general": "Generally Asked",
    "rare":    "Rarely Asked",
    "never":   "Never Asked",
}

def _insights_context(request):
    """
    PMI-based Insights with uniform casing, balanced font size, and tier-specific emphasis.
    """
    user = request.user
    total_topics = Topic.objects.count()

    # Coverage info
    tas = (
        TopicAttemptSummary.objects
        .filter(user=user, mode="practice")
        .select_related("topic")
    )
    practiced_topics = tas.count()
    coverage_pct = round(practiced_topics / total_topics * 100) if total_topics else 0

    # Aggregate attempts
    agg = tas.aggregate(
        total_attempts=Sum("total_attempts"),
        correct_attempts=Sum("correct_attempts"),
        wrong_attempts=Sum("wrong_attempts"),
    )
    total_attempts   = agg["total_attempts"]   or 0
    correct_attempts = agg["correct_attempts"] or 0
    wrong_attempts   = agg["wrong_attempts"]   or 0

    # PMI-based topic grouping
    statuses = (
        TopicStatus.objects
        .filter(user=user)
        .select_related("topic")
        .exclude(pmi__isnull=True)
    )

    strong, transition, weak = [], [], []
    for ts in statuses:
        pmi = float(ts.pmi)
        tier_key = (ts.topic.tier or "general").lower()

        item = {
            "id":   ts.topic.id,
            "name": ts.topic.name,
            "pmi":  round(pmi, 1),
            "tier": tier_key,
            "tier_label": TIER_LABEL.get(tier_key, "Generally Asked"),
            "tier_symbol": TIER_SYMBOL.get(tier_key, "■"),
            "tier_text_class": TIER_TEXT_CLASS.get(tier_key, "text-base font-semibold"),
        }

        # classify by PMI
        if pmi >= 80:
            item["category_text_class"] = CATEGORY_TEXT_CLASS["strong"]
            strong.append(item)
        elif pmi <= 40:
            item["category_text_class"] = CATEGORY_TEXT_CLASS["weak"]
            weak.append(item)
        else:
            item["category_text_class"] = CATEGORY_TEXT_CLASS["transition"]
            transition.append(item)

    # sort & limit
    strong = sorted(strong, key=lambda x: x["pmi"], reverse=True)[:5]
    weak   = sorted(weak,   key=lambda x: x["pmi"])[:5]
    if len(transition) > 5:
        transition = random.sample(transition, 5)

    # counts for headers and mastery
    strong_n     = TopicStatus.objects.filter(user=user, pmi__gte=80).count()
    transition_n = TopicStatus.objects.filter(user=user, pmi__gt=40, pmi__lt=80).count()
    weak_n       = TopicStatus.objects.filter(user=user, pmi__lte=40).count()
    mastery_pct  = round((strong_n / total_topics) * 100) if total_topics else 0

    return {
        "coverage_pct":       coverage_pct,
        "practiced_topics":   practiced_topics,
        "total_topics":       total_topics,
        "total_attempts":     total_attempts,
        "correct_attempts":   correct_attempts,
        "wrong_attempts":     wrong_attempts,

        "strong_topics":      strong,
        "transition_topics":  transition,
        "weak_topics":        weak,

        "strong_n":           strong_n,
        "transition_n":       transition_n,
        "weak_n":             weak_n,

        "mastery_pct":        mastery_pct,
        "strong_count":       strong_n,
    }



def _test_insights(user):
    """
    Return a dict of high-level test-performance insights for the dashboard.
    """

    # ── 1. Per-subject aggregates ────────────────────────────────────────
    summaries = (
        TopicAttemptSummary.objects
        .filter(user=user, mode="test")
        .select_related("topic__section__subject")
        .annotate(subject=F("topic__section__subject__name"))
        .values("subject")
        .annotate(
            total_count    = Sum("total_attempts"),
            sureshot_count = Sum("sureshot_attempts"),
            wrong_count    = Sum("wrong_attempts"),
        )
        .annotate(
            sureshot_pct = ExpressionWrapper(
                100 * F("sureshot_count") / F("total_count"),
                output_field=FloatField()
            ),
            wrong_pct    = ExpressionWrapper(
                100 * F("wrong_count") / F("total_count"),
                output_field=FloatField()
            ),
        )
    )

    subj_stats = list(summaries)

    def pick_max(key):
        valid = [s for s in subj_stats if s.get(key) is not None]
        return max(valid, key=lambda s: s[key]) if valid else {}

    def pick_min(key):
        valid = [s for s in subj_stats if s.get(key) is not None]
        return min(valid, key=lambda s: s[key]) if valid else {}

    hi_sureshot = pick_max("sureshot_pct")
    lo_wrong    = pick_min("wrong_pct")
    hi_wrong    = pick_max("wrong_pct")

    # ── 2. Aggregate question counts from all test-mode topics ─────────
    test_agg = (
        Test.objects
            .filter(user=user, status="completed")
            .aggregate(
                total_questions  = Sum("total_questions"),
                correct_answers  = Sum("correct_answers"),
                unattempted      = Sum("unattempted"),
            )
    )

    total_questions   = test_agg["total_questions"]  or 0
    correct_attempts  = test_agg["correct_answers"]  or 0
    total_unattempted = test_agg["unattempted"]      or 0


    attempted = total_questions - total_unattempted
    wrong     = attempted - correct_attempts

    # ── 3. Count of full-length tests completed ────────────────────────
    total_tests = Test.objects.filter(
        user=user,
        status="completed",
        test_type="full_length"
    ).count()

    # ── 4. Test-level max/min marks ────────────────────────────────────
    marks_agg = Test.objects.filter(
        user=user,
        status="completed"
    ).aggregate(
        max_marks=Max("total_score"),
        max_id   =Max("id"),
        min_marks=Min("total_score"),
        min_id   =Min("id"),
    )

    def fetch_test(prefix):
        tid = marks_agg.get(f"{prefix}_id")
        if not tid:
            return {"marks": None, "label": None, "date": None}
        t = Test.objects.get(id=tid)
        return {
            "marks": marks_agg.get(f"{prefix}_marks"),
            "label": t.name or "",
            "date":  t.end_time.date() if t.end_time else None,
        }

    insights = {
        "highest_sureshot": {
            "pct":     round(hi_sureshot.get("sureshot_pct", 0), 2),
            "subject": hi_sureshot.get("subject") or "—",
        },
        "lowest_wrong": {
            "pct":     round(lo_wrong.get("wrong_pct", 0), 2),
            "subject": lo_wrong.get("subject") or "—",
        },
        "highest_wrong": {
            "pct":     round(hi_wrong.get("wrong_pct", 0), 2),
            "subject": hi_wrong.get("subject") or "—",
        },
        "question_stats": {
            "attempted": attempted or 0,
            "correct":   correct_attempts or 0,
            "wrong":     wrong or 0,
        },
        "total_tests":  total_tests,
        "max_marks":    fetch_test("max"),
        "min_marks":    fetch_test("min"),
    }

    # ── 5. Optional average marks ───────────────────────────────────────
    completed = marks_agg["max_id"] and marks_agg["min_id"]
    if completed:
        total_score = Test.objects.filter(
            user=user,
            status="completed"
        ).aggregate(sum=Sum("total_score"))["sum"] or 0
        count = total_tests
        insights["average_marks"] = round(total_score / count, 2) if count else None

    return insights


@login_required
def dashboard(request):
    mode = _get_mode(request)
    user = request.user

    profile   = request.user.profile
    exam_date = profile.exam_date
    
    days_left = (exam_date - timezone.now().date()).days if exam_date else "--"



    context = {
        "profile":     profile,
        "current_mode":  mode,
        "days_left":     days_left,
        

    }

    if mode == "test":
        pending_test= Test.objects.filter(user=user,status='pending')
        template = "analysis/test_dash.html"
        # Allow new test creation only if fewer than 2 are active
        can_create = pending_test.count() < 2

        # Build (test, next_serial) tuples
        pending_tests_with_next_serial = []
        for t in pending_test:
            highest = (
                t.questionlog_set
                .filter(user_answered__isnull=False)
                .aggregate(Max("serial"))["serial__max"]
            )
            next_serial = (highest + 1) if highest and highest < t.total_questions else 1
            pending_tests_with_next_serial.append((t, next_serial))

        insights = _test_insights(request.user)


        context.update({
            "pending_tests":   pending_tests_with_next_serial,
            'can_create':        can_create,
            "test_insights": insights,

        })


    else:  # fallback to practice
        # 1. Ongoing (pending) practice sessions
        pending_sessions = PracticeSession.objects.filter(
            user=user,
            status='pending'
        )

        # Allow new session creation only if fewer than 2 are active
        can_create = pending_sessions.count() < 2

        # 2. Previous (completed) sessions, most recent first
        previous_sessions = PracticeSession.objects.filter(
            user=user,
            status='completed'
        ).order_by('-end_time')

        # 3. All subjects for the chained form and subject-tree nav
        subjects = Subject.objects.all().order_by('name')

        # 4. All OLT types for the dropdown


        template = "analysis/practice_dash.html"

        context.update({
            'pending_sessions':  pending_sessions,
            'can_create':        can_create,
            'previous_sessions': previous_sessions,
            'subjects':          subjects,
            **_insights_context(request),

        })

    return render(request, template, context)


@login_required
def toggle_mode(request):
    print("Toggling mode for user:", request.user.username)
    if request.method != "POST":
        return HttpResponseForbidden()

    # flip session mode
    current = _get_mode(request)
    new_mode = "Test" if current == "Practice" else "Practice"
    request.session["dash_mode"] = new_mode

    # re-render *both* button and partial in one go
    html = render_to_string(
        "analysis/partials/mode_section.html",
        {"current_mode": new_mode},
        request=request,
    )
    return HttpResponse(html)