
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


def _insights_context(request):
    """
    Returns a dict you can ** unpack into your dashboard context.
    Adds:
      • best_topics    : Top 5 with wrong_rate < 25%
      • mid_topics     : 5 random with 25% ≤ wrong_rate ≤ 50%
      • worst_topics   : Top 5 with wrong_rate > 50%
      • coverage_pct, practiced_topics, total_topics
      • total_attempts, correct_attempts, wrong_attempts
    """
    # ── topics universe & user summaries ───────────────────────────
    total_topics = Topic.objects.count()
    tas = (
        TopicAttemptSummary.objects
        .filter(user=request.user, mode="practice")
        .select_related("topic")
    )
    practiced_topics = tas.count()

    # ── coverage % ─────────────────────────────────────────────────
    coverage_pct = round(practiced_topics / total_topics * 100) if total_topics else 0

    # ── aggregate attempt outcomes ──────────────────────────────────
    agg = tas.aggregate(
        total_attempts=Sum("total_attempts"),
        correct_attempts=Sum("correct_attempts"),
        wrong_attempts=Sum("wrong_attempts"),
    )
    total_attempts   = agg["total_attempts"]   or 0
    correct_attempts = agg["correct_attempts"] or 0
    wrong_attempts   = agg["wrong_attempts"]   or 0

    # ── classify best / mid / worst ────────────────────────────────
    best, mid, worst = [], [], []
    for row in tas:
        wr = row.wrong_rate      # already a % (0–100) or 0 if no attempts
        if wr is None or row.total_attempts == 0:
            continue
        if wr < 25:
            best.append((wr, row))
        elif 25 <= wr <= 50:
            mid.append((wr, row))
        else:  # wr > 50
            worst.append((wr, row))

    #counts
    best_no = len(best)
    mid_no  = len(mid)
    worst_no= len(worst)

    # pick & sort
    
    best  = sorted(best,  key=lambda x: x[0])[:5]
    worst = sorted(worst, key=lambda x: x[0], reverse=True)[:5]

    if len(mid) > 5:
        mid = random.sample(mid, 5)

    # helper to dict
    def to_dict(tup):
        return {
            "id":   tup[1].topic.id,
            "name": tup[1].topic.name,
            "pct":  round(tup[0], 1),
        }

    return {
        "coverage_pct":     coverage_pct,
        "practiced_topics": practiced_topics,
        "total_topics":     total_topics,
        "total_attempts":   total_attempts,
        "correct_attempts": correct_attempts,
        "wrong_attempts":   wrong_attempts,
        "best_topics":      [to_dict(x) for x in best],
        "mid_topics":       [to_dict(x) for x in mid],
        "worst_topics":     [to_dict(x) for x in worst],
        "best_no":         best_no if len(best) else 0,
        "mid_no":          mid_no  if len(mid)  else 0, 
        "worst_no":        worst_no if len(worst)else 0,
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