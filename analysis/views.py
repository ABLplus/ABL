
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

from syllabus.models import Subject
from django.db.models.functions import Coalesce
from .models import TopicStatus
from user.models import UserOverallStats
from collections import defaultdict

from practice.views import _compute_and_update_topic_pmi
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldError

import logging
import math
from typing import Dict, List, Any

logger = logging.getLogger(__name__)




# import your existing PMI function



PMI_STRONG_MIN = 70.0
PMI_WEAK_MAX   = 40.0

User = get_user_model()





# ---------- Helpers ----------

def _resolve_topicstatus_method(request) -> str:
    
    method = "MAS"
    
    return method if method in ("MAS", "PCT") else "MAS"


def _topics_queryset_for_exam(profile):
    """
    Exam-scoped Topic queryset (best effort).
    Adjust if your schema is different.
    """
    if not profile.exam:
        return Topic.objects.all()

    # Option A: Topic has FK 'exam'
    try:
        return Topic.objects.filter(exam=profile.exam)
    except FieldError:
        pass

    # Option B: Topic -> Subject -> Exam
    try:
        return Topic.objects.filter(subject__exam=profile.exam)
    except FieldError:
        pass

    # fallback
    return Topic.objects.all()


def _practice_ts_base_qs(user):
    """
    Base TopicStatus QS that represents "has practice data".
    practice_rounds__gt=0 is your clean practice signal.
    """
    return (
        TopicStatus.objects
        .filter(user=user, practice_rounds__gt=0)
        .select_related("topic")
    )




DEFAULT_SORT = "-pmi"  # High → Low


@login_required
def user_topic_metrics(request):
    users = User.objects.order_by("username")

    selected_user = None
    topic_statuses = []

    # Sorting (validate against SORT_MAP values)
    sort = request.GET.get("sort", DEFAULT_SORT)
    sort_field = sort.lstrip("-")
    if sort_field not in SORT_MAP.values():  # expects SORT_MAP values are actual ORM fields
        sort = DEFAULT_SORT

    # Support both POST (form submit) and GET (links)
    user_id = request.POST.get("user_id") if request.method == "POST" else request.GET.get("user_id")

    if user_id:
        selected_user = User.objects.filter(id=user_id).first()

        if selected_user:
            # ✅ Updated to match your current TopicStatus model:
            # - remove pctwrong_practice filter (field doesn't exist now)
            # - keep pmi__isnull=False since this page is "metrics"
            topic_statuses = (
                TopicStatus.objects
                .select_related("topic", "subject", "section", "exam")
                .filter(
                    user=selected_user,
                    pmi__isnull=False,
                )
                .order_by(sort)
            )

    context = {
        "users": users,
        "selected_user": selected_user,
        "topic_statuses": topic_statuses,
        "sort": sort,
    }
    return render(request, "analysis/user_topic_metrics.html", context)

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
    
    elif ttype == "section":
        ctx = {"sections": Section.objects.all()}

        return render(request, "analysis/partials/_section_form.html", ctx)

    return HttpResponseBadRequest("Unknown test type")

def _get_mode(request):
    """Return session-stored mode or fall back to profile default.
    Also update session if ?mode= is present in the URL."""
    # If the user clicked a switch button with ?mode=..., store it
    mode_param = request.GET.get("mode")
    if mode_param in ("practice", "test"):
        request.session["dash_mode"] = mode_param

    return request.session.get("dash_mode", request.user.profile.mode)




# PMI category colors
CATEGORY_TEXT_CLASS = {
    "strong":     "text-green-700 dark:text-green-300",
    "transition": "text-yellow-600 dark:text-yellow-300",
    "weak":       "text-red-700 dark:text-red-300",
}



CATEGORY_TEXT_CLASS = {
    "strong": "text-green-600 dark:text-green-400",
    "transition": "text-orange-600 dark:text-orange-400",
    "weak": "text-red-600 dark:text-red-400",
}


def _jget(d: dict, key: str) -> int:
    """Safe getter for JSONField dicts."""
    return int((d or {}).get(key, 0))


def practice_insights_context(request) -> Dict[str, Any]:
    """
    Optimized / corrected version of your practice_insights_context.

    Expectations and outputs unchanged from your original docstring.
    """
    user = request.user
    method = _resolve_topicstatus_method(request)  # keep your existing resolver

    # ---- Query 1: overall stats (get_or_create)
    uos, _ = UserOverallStats.objects.get_or_create(user=user)
    total_attempts = int(uos.practice_attempts or 0)
    correct_attempts = int(uos.practice_correct or 0)
    wrong_attempts = int(uos.practice_wrong or 0)

    logger.debug(
        "UserOverallStats for %s: %d attempts, %d correct, %d wrong",
        getattr(user, "username", str(user)),
        total_attempts,
        correct_attempts,
        wrong_attempts,
    )

    # ---- Query 2: load ALL topics but only required fields to save memory
    # fields: topic id, topic name, subject id, subject name
    # path: Topic -> Section -> Subject (adjust keys if models differ)
    topic_rows = list(
        Topic.objects.values(
            "id",
            "name",
            "section__subject__id",
            "section__subject__name",
        )
    )

    total_topics = len(topic_rows)

    # ---- Query 3: load TopicStatus rows for this user as a mapping topic_id -> pmi
    ts_qs = TopicStatus.objects.filter(user=user).values_list("topic_id", "pmi")
    pmi_by_topic = {topic_id: pmi for (topic_id, pmi) in ts_qs}

    # ---- Accumulators
    subj_counts: Dict[int, Dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "strong": 0, "transition": 0, "weak": 0, "unstarted": 0, "name": ""}
    )

    strong: List[Dict[str, Any]] = []
    transition: List[Dict[str, Any]] = []
    weak: List[Dict[str, Any]] = []

    strong_n = transition_n = weak_n = 0
    practiced_topics = 0

    # Single pass over topics
    for row in topic_rows:
        t_id = row["id"]
        t_name = row.get("name") or "Untitled"
        subj_id = row.get("section__subject__id")
        subj_name = row.get("section__subject__name") or "Unknown"

        if subj_id is not None:
            sc = subj_counts[subj_id]
            sc["name"] = subj_name
            sc["total"] += 1

        pmi = pmi_by_topic.get(t_id, None)

        # Unstarted if no status row or pmi is null
        if pmi is None:
            if subj_id is not None:
                subj_counts[subj_id]["unstarted"] += 1
            continue

        practiced_topics += 1
        try:
            pmi_f = float(pmi)
        except (TypeError, ValueError):
            # treat invalid pmi as unstarted
            if subj_id is not None:
                subj_counts[subj_id]["unstarted"] += 1
            continue

        # metric only relevant for MAS method
        metric = round(pmi_f, 1) if method == "MAS" else None
        item = {"id": t_id, "name": t_name, "metric": metric}

        if pmi_f >= PMI_STRONG_MIN:
            strong_n += 1
            strong.append(item)
            if subj_id is not None:
                subj_counts[subj_id]["strong"] += 1
        elif pmi_f <= PMI_WEAK_MAX:
            weak_n += 1
            weak.append(item)
            if subj_id is not None:
                subj_counts[subj_id]["weak"] += 1
        else:
            transition_n += 1
            transition.append(item)
            if subj_id is not None:
                subj_counts[subj_id]["transition"] += 1

    # ---- Percent calculations (safe with zero checks)
    def pct(part: int, whole: int, ndigits: int = 1) -> float:
        if whole <= 0:
            return 0.0
        return round((part / whole) * 100, ndigits)

    coverage_pct = int(round((practiced_topics / total_topics) * 100)) if total_topics else 0
    mastery_pct = int(round((strong_n / total_topics) * 100)) if total_topics else 0

    # ---- Top lists for UI
    # strong: sort desc by metric (metric may be None when method != MAS)
    strong = sorted(
        strong, key=lambda x: (x["metric"] is not None, x["metric"]), reverse=True
    )[:5]

    # weak: sort asc by metric (smaller PMI worse)
    weak = sorted(
        weak, key=lambda x: (x["metric"] is not None, x["metric"] if x["metric"] is not None else math.inf)
    )[:5]

    if len(transition) > 5:
        transition = random.sample(transition, 5)

    # ---- Build subject pills (sorted by subject name)
    subject_pills: List[Dict[str, Any]] = []
    for sid, c in subj_counts.items():
        total = c["total"] or 1  # avoid div-by-zero visually; templates can treat total=0 specially
        subject_pills.append(
            {
                "id": sid,
                "name": c["name"],
                "total": c["total"],
                "strong": c["strong"],
                "transition": c["transition"],
                "weak": c["weak"],
                "unstarted": c["unstarted"],
                "pct_strong": pct(c["strong"], total, 1),
                "pct_transition": pct(c["transition"], total, 1),
                "pct_weak": pct(c["weak"], total, 1),
                "pct_unstarted": pct(c["unstarted"], total, 1),
            }
        )

    subject_pills.sort(key=lambda x: (x["name"] or "").lower())

    all_unstarted = total_topics - (strong_n + transition_n + weak_n)
    all_subjects_pill = {
        "name": "All Subjects",
        "total": total_topics,
        "strong": strong_n,
        "transition": transition_n,
        "weak": weak_n,
        "unstarted": all_unstarted,
        "pct_strong": pct(strong_n, total_topics, 1),
        "pct_transition": pct(transition_n, total_topics, 1),
        "pct_weak": pct(weak_n, total_topics, 1),
        "pct_unstarted": pct(all_unstarted, total_topics, 1),
    }

    return {
        # Part 1 counters
        "total_attempts": total_attempts,
        "correct_attempts": correct_attempts,
        "wrong_attempts": wrong_attempts,
        # Part 2 coverage
        "coverage_pct": coverage_pct,
        "mastery_pct": mastery_pct,
        "practiced_topics": practiced_topics,
        "total_topics": total_topics,
        # Part 2 buckets (top 5)
        "strong_topics": strong,
        "transition_topics": transition,
        "weak_topics": weak,
        # header counts
        "strong_n": strong_n,
        "transition_n": transition_n,
        "weak_n": weak_n,
        # subject pills
        "subject_pills": subject_pills,
        "all_subjects_pill": all_subjects_pill,
    }

@login_required
def dashboard(request):
    mode = _get_mode(request)  # your util
    user = request.user
    profile = user.profile

    exam_date = profile.exam_date
    days_left = (exam_date - timezone.now().date()).days if exam_date else "--"
    days_since_joined = (timezone.now().date() - profile.date_joined).days

    context = {
        "profile": profile,
        "current_mode": mode,
        "days_left": days_left,
        "days_since_joined": days_since_joined,
        "topicstatus_method": _resolve_topicstatus_method(request),
    }

    if mode == "test":
        pending_test = Test.objects.filter(user=user, status="pending")
        template = "analysis/test_dash.html"

        can_create = pending_test.count() < 2

        pending_tests_with_next_serial = []
        for t in pending_test:
            highest = (
                t.questionlog_set
                 .filter(user_answered__isnull=False)
                 .aggregate(Max("serial"))["serial__max"]
            )
            next_serial = (highest + 1) if highest and highest < t.total_questions else 1
            pending_tests_with_next_serial.append((t, next_serial))

        insights = _test_insights(user)  # your existing function

        context.update({
            "pending_tests": pending_tests_with_next_serial,
            "can_create": can_create,
            "test_insights": insights,
        })

    else:
        # Practice mode
        pending_sessions = PracticeSession.objects.filter(user=user, status="pending")
        can_create = pending_sessions.count() < 2

        # Not used directly in your pasted template (history is htmx),
        # but you may need it elsewhere; safe to keep
        previous_sessions = (
            PracticeSession.objects
            .filter(user=user, status="completed")
            .order_by("-end_time")
        )

        subjects = Subject.objects.filter(exam=profile.exam).order_by("name")
        template = "analysis/practice_dash.html"

        context.update({
            "pending_sessions": pending_sessions,
            "can_create": can_create,
            "previous_sessions": previous_sessions,
            "subjects": subjects,
        })
        context.update(practice_insights_context(request))

    return render(request, template, context)



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
        status="completed"
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


# @login_required
# def dashboard(request):
#     mode = _get_mode(request)
#     user = request.user
#     profile = user.profile

#     exam_date = profile.exam_date
#     days_left = (exam_date - timezone.now().date()).days if exam_date else "--"
#     days_since_joined = (timezone.now().date() - profile.date_joined).days

#     context = {
#         "profile": profile,
#         "current_mode": mode,
#         "days_left": days_left,
#         "days_since_joined": days_since_joined,
#         "topicstatus_method": _resolve_topicstatus_method(request),
#     }

#     if mode == "test":
#         pending_test = Test.objects.filter(user=user, status="pending")
#         template = "analysis/test_dash.html"

#         can_create = pending_test.count() < 2

#         pending_tests_with_next_serial = []
#         for t in pending_test:
#             highest = (
#                 t.questionlog_set
#                  .filter(user_answered__isnull=False)
#                  .aggregate(Max("serial"))["serial__max"]
#             )
#             next_serial = (highest + 1) if highest and highest < t.total_questions else 1
#             pending_tests_with_next_serial.append((t, next_serial))

#         insights = _test_insights(user)

#         context.update({
#             "pending_tests": pending_tests_with_next_serial,
#             "can_create": can_create,
#             "test_insights": insights,
#         })

#     else:
#         pending_sessions = PracticeSession.objects.filter(user=user, status="pending")
#         can_create = pending_sessions.count() < 2

#         previous_sessions = PracticeSession.objects.filter(
#             user=user, status="completed"
#         ).order_by("-end_time")

#         subjects = Subject.objects.all().order_by("name")

#         template = "analysis/practice_dash.html"

#         context.update({
#             "pending_sessions": pending_sessions,
#             "can_create": can_create,
#             "previous_sessions": previous_sessions,
#             "subjects": subjects,
#             **_insights_context(request),
#         })

#     return render(request, template, context)


@login_required
def practice_bucket_modal(request):
    """
    HTMX modal: full list of topics in a bucket (strong / transition / weak).

    Rules:
    - Bucket is derived ONLY from PMI
    - No pct-wrong logic here
    - Tier is passed as topic.tier (tier1 / tier2 / tier3)
    - No symbols, labels, or UI decoration
    """

    user = request.user
    method = _resolve_topicstatus_method(request)

    bucket = (request.GET.get("bucket") or "transition").lower()
    if bucket not in ("strong", "transition", "weak"):
        bucket = "transition"

    ts_qs = (
        TopicStatus.objects
        .filter(user=user)
        .select_related("topic")
        .exclude(pmi__isnull=True)
    )

    # Bucket logic (STRICT)
    if bucket == "strong":
        ts_qs = ts_qs.filter(pmi__gte=PMI_STRONG_MIN).order_by("-pmi", "topic__name")
    elif bucket == "weak":
        ts_qs = ts_qs.filter(pmi__lte=PMI_WEAK_MAX).order_by("pmi", "topic__name")
    else:
        ts_qs = ts_qs.filter(pmi__gt=PMI_WEAK_MAX, pmi__lt=PMI_STRONG_MIN).order_by("-pmi", "topic__name")
    rows = ts_qs.only("topic__id", "topic__name", "topic__tier", "pmi")

    def pack(ts: TopicStatus) -> dict:
        return {
            "id": ts.topic.id,
            "name": ts.topic.name,
            "tier": ts.topic.tier,       # tier1 / tier2 / tier3
            "metric": round(float(ts.pmi), 1) if ts.pmi is not None else None,
        }

    context = {
        "bucket": bucket,
        "method": method,
        "metric_field": "pmi",
        "rows": [pack(ts) for ts in rows],
    }

    return render(
        request,
        "analysis/partials/practice_bucket_modal.html",
        context
    )



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