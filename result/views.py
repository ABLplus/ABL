# Create your views here.
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from collections import Counter
from question.models import Subject
from tests.models import QuestionLog, Test, TopicAttemptSummary
from django.contrib.auth.decorators import login_required
from django.db.models import F, Case, When, IntegerField, OuterRef, Subquery, ExpressionWrapper, FloatField, Value
from django.db.models.functions import Greatest
from django.contrib.auth.models import User
from django.utils.http import urlencode
from analysis.models import TopicStatus
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from user.models import Profile
from practice.models import PracticeSession

from django.utils import timezone

from collections import OrderedDict

from django.contrib.auth import get_user_model
from syllabus.models import Topic, Section  # adjust if needed

User = get_user_model()





def question_log_history_view(request):
    """
    Loads QuestionLog data ONLY on POST to avoid huge datasets on GET.

    POST fields:
      - user_id (required)
      - mode: "" | "test" | "practice"
      - topic_id: "" | <id>
      - page (optional)
    """

    users = User.objects.order_by("username")
    sections= Section.objects.order_by("name")
    topics = Topic.objects.order_by("name")

    selected_user = None
    selected_topic = None
    mode = ""
    rows = []
    submitted = False

    if request.method == "POST":
        submitted = True

        user_id = request.POST.get("user_id")
        mode = (request.POST.get("mode") or "").strip().lower()
        topic_id = request.POST.get("topic_id") or ""
        page_number = request.POST.get("page", 1)
        section_id = request.POST.get("Section_id") or ""

        # Fetch selected user/topic efficiently
        selected_user = User.objects.filter(id=user_id).only("id", "username").first()
        selected_topic = Topic.objects.filter(id=topic_id).only("id", "name").first() if topic_id else None

        if section_id:
            topics = topics.filter(section_id=section_id)

        



        if selected_user:
            qs = (
                QuestionLog.objects
                .filter(user_id=selected_user.id)
                .select_related("question", "topic")
                .only(
                    "question_id",
                    "question__id",
                    "question__question_html",
                    "topic__id",
                    "topic__name",
                    "serial",
                    "user_answered",
                    "attempt_result",
                    "attempt_type",
                    "timestamp",
                    "time_taken_seconds",
                    "test_id",
                )
                .order_by("question_id", "timestamp")
            )

            if selected_topic:
                qs = qs.filter(question__topic_id=selected_topic.id)
            
            if section_id:
                qs = qs.filter(question__topic__in=topics.values_list('id', flat=True))

            if mode == "test":
                qs = qs.filter(test_id__isnull=False)
            elif mode == "practice":
                qs = qs.filter(practiceSession__isnull=False)




            # -----------------------
            # PAGINATION (CRITICAL)
            # -----------------------
            paginator = Paginator(qs, 2000)  # tune page size as needed
            page = paginator.get_page(page_number)

            # -----------------------
            # GROUP ATTEMPTS PER QUESTION
            # -----------------------
            grouped = OrderedDict()

            for log in page:
                qid = log.question_id

                if qid not in grouped:
                    grouped[qid] = {
                        "question": log.question,
                        "topic": log.topic,
                        "attempts": [],
                    }

                grouped[qid]["attempts"].append({
                    "mode": "test" if log.test_id else "practice",
                    "serial": log.serial,
                    "user_answered": log.user_answered or "—",
                    "attempt_result": log.attempt_result or "—",
                    "attempt_type": log.attempt_type or "—",
                    "timestamp": log.timestamp,
                    "time_taken_seconds": log.time_taken_seconds,
                })

            rows = [
                {
                    "sno": idx,
                    "question": data["question"],
                    "topic": data["topic"],
                    "attempts": data["attempts"],
                }
                for idx, data in enumerate(grouped.values(), start=1)
            ]

    context = {
        "users": users,
        "topics": topics,
        "sections": sections,
        "selected_user": selected_user,
        "selected_topic": selected_topic,
        "mode": mode,
        "rows": rows,
        "submitted": submitted,
    }

    return render(request, "result/question_log_history.html", context)



@staff_member_required
def daily_engagement_report(request):
    """
    ADMIN DAILY ENGAGEMENT (Completed-first)

    Metrics:
    - New Users (date_joined)
    - DAU (users completing practice/test)
    - Returning Users (D-7)
    - Avg Questions / Active User
    - Practice vs Test %
    - Completion Rate (same-day)
    - Practice Sessions Completed (by end_time)
    - Practice Questions Completed (by end_time)
    - Tests Completed (by end_time)
    - Test Questions Completed (by end_time)
    - Carryover Practice Sessions
    - Carryover Test Sessions
    """

    FILTER_START = date(2025, 12, 1)
    FILTER_START_DT = timezone.make_aware(
        timezone.datetime.combine(FILTER_START, timezone.datetime.min.time())
    )

    # ───────────────────────────────────────────────
    # 1) New Users
    # ───────────────────────────────────────────────
    user_joins_qs = (
        Profile.objects
        .filter(date_joined__gte=FILTER_START)
        .values("date_joined")
        .annotate(new_users=Count("id"))
    )

    # ───────────────────────────────────────────────
    # 2) Completed Practice (sessions + questions + users)
    # ───────────────────────────────────────────────
    practice_completed_qs = (
        PracticeSession.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            end_time__gte=FILTER_START_DT,
        )
        .annotate(date=TruncDate("end_time"))
        .values("date")
        .annotate(
            practice_sessions_completed=Count("id"),
            practice_questions_completed=Sum("total_questions"),
        )
    )

    practice_completed_users_qs = (
        PracticeSession.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            end_time__gte=FILTER_START_DT,
        )
        .annotate(date=TruncDate("end_time"))
        .values("date", "user_id")
        .distinct()
    )

    # ───────────────────────────────────────────────
    # 3) Completed Tests (sessions + questions + users)
    # ───────────────────────────────────────────────
    test_completed_qs = (
        Test.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            end_time__gte=FILTER_START_DT,
        )
        .annotate(date=TruncDate("end_time"))
        .values("date")
        .annotate(
            tests_completed=Count("id"),
            test_questions_completed=Sum("total_questions"),
        )
    )

    test_completed_users_qs = (
        Test.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            end_time__gte=FILTER_START_DT,
        )
        .annotate(date=TruncDate("end_time"))
        .values("date", "user_id")
        .distinct()
    )

    # ───────────────────────────────────────────────
    # 4) Started vs Completed SAME DAY (for carryover + completion)
    # ───────────────────────────────────────────────
    practice_started_qs = (
        PracticeSession.objects
        .filter(start_time__gte=FILTER_START_DT)
        .annotate(date=TruncDate("start_time"))
        .values("date")
        .annotate(practice_started=Count("id"))
    )

    practice_completed_same_day_qs = (
        PracticeSession.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            start_time__gte=FILTER_START_DT,
        )
        .annotate(start_date=TruncDate("start_time"))
        .annotate(end_date=TruncDate("end_time"))
        .filter(end_date=F("start_date"))
        .values("start_date")
        .annotate(practice_completed_same_day=Count("id"))
    )

    tests_started_qs = (
        Test.objects
        .filter(start_time__gte=FILTER_START_DT)
        .annotate(date=TruncDate("start_time"))
        .values("date")
        .annotate(tests_started=Count("id"))
    )

    tests_completed_same_day_qs = (
        Test.objects
        .filter(
            status="completed",
            end_time__isnull=False,
            start_time__gte=FILTER_START_DT,
        )
        .annotate(start_date=TruncDate("start_time"))
        .annotate(end_date=TruncDate("end_time"))
        .filter(end_date=F("start_date"))
        .values("start_date")
        .annotate(tests_completed_same_day=Count("id"))
    )

    # ───────────────────────────────────────────────
    # 5) Merge buckets
    # ───────────────────────────────────────────────
    data = defaultdict(lambda: {
        "date": None,
        "new_users": 0,

        "dau": 0,
        "returning_d7": 0,
        "avg_q_per_user": 0.0,

        "practice_pct": 0.0,
        "test_pct": 0.0,

        "completion_rate": 0.0,

        "practice_sessions_completed": 0,
        "practice_questions_completed": 0,
        "tests_completed": 0,
        "test_questions_completed": 0,

        "carryover_practice": 0,
        "carryover_tests": 0,

        # internal
        "_practice_started": 0,
        "_tests_started": 0,
        "_practice_completed_same_day": 0,
        "_tests_completed_same_day": 0,
    })

    def touch(d):
        b = data[d]
        if b["date"] is None:
            b["date"] = d
        return b

    # New users
    for r in user_joins_qs:
        touch(r["date_joined"])["new_users"] = r["new_users"]

    # Practice completed
    for r in practice_completed_qs:
        b = touch(r["date"])
        b["practice_sessions_completed"] = r["practice_sessions_completed"] or 0
        b["practice_questions_completed"] = r["practice_questions_completed"] or 0

    # Tests completed
    for r in test_completed_qs:
        b = touch(r["date"])
        b["tests_completed"] = r["tests_completed"] or 0
        b["test_questions_completed"] = r["test_questions_completed"] or 0

    # Started / same-day completed
    for r in practice_started_qs:
        touch(r["date"])["_practice_started"] = r["practice_started"]

    for r in practice_completed_same_day_qs:
        touch(r["start_date"])["_practice_completed_same_day"] = r["practice_completed_same_day"]

    for r in tests_started_qs:
        touch(r["date"])["_tests_started"] = r["tests_started"]

    for r in tests_completed_same_day_qs:
        touch(r["start_date"])["_tests_completed_same_day"] = r["tests_completed_same_day"]

    # ───────────────────────────────────────────────
    # 6) DAU & Returning (D-7)
    # ───────────────────────────────────────────────
    active_users_by_date = defaultdict(set)

    for r in practice_completed_users_qs:
        active_users_by_date[r["date"]].add(r["user_id"])

    for r in test_completed_users_qs:
        active_users_by_date[r["date"]].add(r["user_id"])

    for d, users in active_users_by_date.items():
        touch(d)["dau"] = len(users)

    for d in sorted(active_users_by_date.keys()):
        today_users = active_users_by_date[d]
        prev_users = set()
        for i in range(1, 8):
            prev_users |= active_users_by_date.get(d - timedelta(days=i), set())
        touch(d)["returning_d7"] = len(today_users & prev_users)

    # ───────────────────────────────────────────────
    # 7) Derived metrics
    # ───────────────────────────────────────────────
    for b in data.values():
        total_q = b["practice_questions_completed"] + b["test_questions_completed"]

        if b["dau"] > 0:
            b["avg_q_per_user"] = round(total_q / b["dau"], 2)

        if total_q > 0:
            b["practice_pct"] = round(100 * b["practice_questions_completed"] / total_q, 1)
            b["test_pct"] = round(100 - b["practice_pct"], 1)

        b["carryover_practice"] = max(
            0, b["_practice_started"] - b["_practice_completed_same_day"]
        )
        b["carryover_tests"] = max(
            0, b["_tests_started"] - b["_tests_completed_same_day"]
        )

        started_total = b["_practice_started"] + b["_tests_started"]
        completed_same_day_total = (
            b["_practice_completed_same_day"] + b["_tests_completed_same_day"]
        )

        if started_total > 0:
            b["completion_rate"] = round(
                100 * completed_same_day_total / started_total, 1
            )

    rows = list(data.values())

    rows.sort(key=lambda x: x["date"], reverse=True)

    return render(request, "result/daily_engagement_report.html", {
        "rows": rows,
    })




# FILTER_START = date(2025, 12, 1)
# FILTER_START_DT = datetime.combine(FILTER_START, time.min)  # 2025-12-01 00:00:00


# @staff_member_required
# def daily_engagement_report(request):
#     """
#     Daily summary:
#     - New users joined per date (Profile.date_joined)
#     - Practice sessions per date (ALL sessions: pending + completed) by start_time
#     - Practice questions per date (ONLY completed sessions) by end_time
#     - Tests per date (ALL tests) by start_time
#     - Test questions per date (ONLY completed tests) by end_time
#     """

#     # 1) Users joined since FILTER_START (DateField – fine to use __gte)
#     user_joins_qs = (
#         Profile.objects
#         .filter(date_joined__gte=FILTER_START)
#         .values('date_joined')
#         .annotate(new_users=Count('id'))
#     )

#     # 2a) Practice sessions (ALL) by start_time (index-friendly filter)
#     practice_sessions_qs = (
#         PracticeSession.objects
#         .filter(start_time__gte=FILTER_START_DT)
#         .annotate(date=TruncDate('start_time'))
#         .values('date')
#         .annotate(practice_sessions=Count('id'))
#     )

#     # 2b) Practice questions (ONLY completed) by end_time
#     practice_questions_qs = (
#         PracticeSession.objects
#         .filter(
#             status='completed',
#             end_time__isnull=False,
#             end_time__gte=FILTER_START_DT,
#         )
#         .annotate(date=TruncDate('end_time'))
#         .values('date')
#         .annotate(practice_questions=Sum('total_questions'))
#     )

#     # 3a) Tests (ALL) by start_time
#     tests_qs = (
#         Test.objects
#         .filter(start_time__gte=FILTER_START_DT)
#         .annotate(date=TruncDate('start_time'))
#         .values('date')
#         .annotate(tests=Count('id'))
#     )

#     # 3b) Test questions (ONLY completed) by end_time
#     test_questions_qs = (
#         Test.objects
#         .filter(
#             status='completed',
#             end_time__isnull=False,
#             end_time__gte=FILTER_START_DT,
#         )
#         .annotate(date=TruncDate('end_time'))
#         .values('date')
#         .annotate(test_questions=Sum('total_questions'))
#     )

#     # --- Merge all into one dict keyed by date ---
#     data = defaultdict(lambda: {
#         'date': None,
#         'new_users': 0,
#         'practice_sessions': 0,     # ALL sessions
#         'practice_questions': 0,    # only completed
#         'tests': 0,                 # ALL tests
#         'test_questions': 0,        # only completed
#     })

#     def touch_bucket(d):
#         """Ensure bucket exists and has date set once."""
#         bucket = data[d]
#         if bucket['date'] is None:
#             bucket['date'] = d
#         return bucket

#     # Users
#     for row in user_joins_qs:
#         d = row['date_joined']
#         bucket = touch_bucket(d)
#         bucket['new_users'] = row['new_users']

#     # Practice sessions (all)
#     for row in practice_sessions_qs:
#         d = row['date']
#         bucket = touch_bucket(d)
#         bucket['practice_sessions'] = row['practice_sessions'] or 0

#     # Practice questions (completed)
#     for row in practice_questions_qs:
#         d = row['date']
#         bucket = touch_bucket(d)
#         bucket['practice_questions'] = row['practice_questions'] or 0

#     # Tests (all)
#     for row in tests_qs:
#         d = row['date']
#         bucket = touch_bucket(d)
#         bucket['tests'] = row['tests'] or 0

#     # Test questions (completed)
#     for row in test_questions_qs:
#         d = row['date']
#         bucket = touch_bucket(d)
#         bucket['test_questions'] = row['test_questions'] or 0

#     rows = list(data.values())

#     # --- Sorting ---
#     sort = request.GET.get("sort", "date")
#     direction = request.GET.get("dir", "desc")

#     allowed_sorts = {
#         "date": "date",
#         "new_users": "new_users",
#         "practice_sessions": "practice_sessions",
#         "practice_questions": "practice_questions",
#         "tests": "tests",
#         "test_questions": "test_questions",
#     }

#     sort_key = allowed_sorts.get(sort, "date")
#     reverse = (direction != "asc")  # default desc

#     rows.sort(key=lambda x: x[sort_key] or 0, reverse=reverse)

#     return render(request, 'result/daily_engagement_report.html', {
#         'rows': rows,
#         'sort': sort,
#         'direction': direction,
#     })



@login_required
def topic_summary(request):
    target_user = request.user
    user_qs_param = request.GET.get("user")
    if user_qs_param and request.user.is_staff:
        target_user = get_object_or_404(User, pk=user_qs_param)

    # Base queryset
    summaries = (
        TopicAttemptSummary.objects
        .filter(user=target_user)
        .select_related("topic__section__subject", "topic__section")
    )

    # ---- Filters ----
    valid_modes = {value for value, _ in TopicAttemptSummary.MODE_CHOICES}
    mode = (request.GET.get("mode") or "").strip()
    if mode and mode in valid_modes:
        summaries = summaries.filter(mode=mode)
    else:
        mode = ""  # normalize

    q = (request.GET.get("q") or "").strip()
    if q:
        summaries = summaries.filter(topic__name__icontains=q)

    # Subject filter (dropdown)
    subject_id = (request.GET.get("subject") or "").strip()
    if subject_id.isdigit():
        summaries = summaries.filter(topic__section__subject_id=int(subject_id))

    # ---- Metrics annotations (all as percentages except practice_rounds) ----
    # Safe denominators
    denom_total = Case(
        When(total_attempts=0, then=Value(1)),  # avoid div-by-zero; values below guard display
        default=F("total_attempts"),
        output_field=IntegerField(),
    )
    denom_ss = Case(
        When(sureshot_attempts=0, then=Value(1)),
        default=F("sureshot_attempts"),
        output_field=IntegerField(),
    )
    denom_ap = Case(
        When(applied_attempts=0, then=Value(1)),
        default=F("applied_attempts"),
        output_field=IntegerField(),
    )
    denom_gw = Case(
        When(guesswork_attempts=0, then=Value(1)),
        default=F("guesswork_attempts"),
        output_field=IntegerField(),
    )

    # Rights by type (guard negatives)
    ss_right = Greatest(F("sureshot_attempts") - F("sureshot_wrong"), Value(0))
    ap_right = Greatest(F("applied_attempts") - F("applied_wrong"), Value(0))
    gw_right = Greatest(F("guesswork_attempts") - F("guesswork_wrong"), Value(0))

    # Wrong rate (already existed)
    wrong_rate_expr = Case(
        When(total_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * F("wrong_attempts") / F("total_attempts"),
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )

    # 6 Metrics
    cki_expr = Case(
        When(total_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * (F("sureshot_attempts") + F("applied_attempts")) / denom_total,
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )
    pki_expr = Case(
        When(total_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * (ss_right + ap_right) / denom_total,
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )
    cg_expr = ExpressionWrapper(cki_expr - pki_expr, output_field=FloatField())

    fcr_expr = Case(
        When(sureshot_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * F("sureshot_wrong") / denom_ss,
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )
    af_expr = Case(
        When(applied_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * F("applied_wrong") / denom_ap,
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )
    gw_wrong_pct_expr = Case(
        When(guesswork_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * F("guesswork_wrong") / denom_gw,
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )

    # ---- PMI + practice_rounds from TopicStatus via Subquery ----
    ts_pmi_sq = Subquery(
        TopicStatus.objects
        .filter(user=target_user, topic=OuterRef("topic"))
        .values("pmi")[:1]
    )
    ts_practice_rounds_sq = Subquery(
        TopicStatus.objects
        .filter(user=target_user, topic=OuterRef("topic"))
        .values("practice_rounds")[:1]
    )

    summaries = summaries.annotate(
        wrong_rate_value=wrong_rate_expr,
        cki_value=cki_expr,
        pki_value=pki_expr,
        cg_value=cg_expr,
        fcr_value=fcr_expr,
        af_value=af_expr,
        gw_wrong_pct_value=gw_wrong_pct_expr,
        pmi_value=ts_pmi_sq,
        practice_rounds_value=ts_practice_rounds_sq,
        subject_name=F("topic__section__subject__name"),
        section_name=F("topic__section__name"),
    )

    # ---- Sorting ----
    sort_map = {
        "subject": "subject_name",
        "section": "section_name",
        "topic": "topic__name",
        "mode": "mode",
        "total": "total_attempts",
        "correct": "correct_attempts",
        "wrong": "wrong_attempts",
        "wrong_rate": "wrong_rate_value",
        "net": "net_marks",
        "ss": "sureshot_attempts",
        "ap": "applied_attempts",
        "gw": "guesswork_attempts",
        "ssw": "sureshot_wrong",
        "apw": "applied_wrong",
        "gww": "guesswork_wrong",
        # NEW metrics:
        "cki": "cki_value",
        "pki": "pki_value",
        "cg": "cg_value",
        "fcr": "fcr_value",
        "af": "af_value",
        "gw_wrong_pct": "gw_wrong_pct_value",
        # PMI + practice_rounds
        "pmi": "pmi_value",
        "practice_rounds": "practice_rounds_value",
    }

    sort_key = (request.GET.get("sort") or "topic").strip()
    sort_dir = (request.GET.get("dir") or "asc").strip().lower()
    orm_field = sort_map.get(sort_key, "topic__name")

    if sort_dir == "desc":
        summaries = summaries.order_by(f"-{orm_field}", "topic__name", "mode")
    else:
        summaries = summaries.order_by(orm_field, "topic__name", "mode")

    # Keep other params when toggling sort
    base_params = request.GET.copy()
    base_params.pop("sort", None)
    base_params.pop("dir", None)
    base_qs = urlencode(base_params, doseq=True)

    # Subject choices for dropdown (subjects that this user has summaries for)
    subject_choices = (
        Subject.objects
        .filter(sections__topics__topicattemptsummary__user=target_user)
        .distinct()
        .order_by("name")
    )

    all_users = User.objects.only("id", "username").order_by("username")

    context = {
        "target_user": target_user,
        "summaries": summaries,
        "all_users": all_users,
        "mode_choices": TopicAttemptSummary.MODE_CHOICES,
        "current_mode": mode,
        "q": q,
        "active_sort": sort_key,
        "active_dir": sort_dir,
        "base_qs": base_qs,
        "subject_choices": subject_choices,
        "current_subject_id": subject_id,
    }
    return render(request, "result/topic_summary.html", context)


def test_result(request, test_id):

    test = get_object_or_404(Test, id=test_id, user=request.user)

    if test.status != 'completed':
        return redirect('dashboard')
    total = test.total_questions
    correct = test.correct_answers
    unattempted = test.unattempted
    blind_attempts = test.blind_attempts
    wrong = test.wrong_answers()
    attempted = total - unattempted
    score = test.total_score

     # Get all test IDs for the user, ordered by ID
    test_ids = list(
        Test.objects.filter(user=request.user, status='completed')
        .order_by('id')
        .values_list('id', flat=True)
    )

    # Find the index of the current test
    try:
        current_index = test_ids.index(test.id)
    except ValueError:
        current_index = -1

    previous_test_id = test_ids[current_index - 1] if current_index > 0 else None
    next_test_id = test_ids[current_index + 1] if current_index < len(test_ids) - 1 else None

    # Your core metric
    percent_wrong = round((wrong / attempted) * 100, 2) if attempted > 0 else 0

    # Scoring system
    MARKS_CORRECT = 2
    MARKS_WRONG = -2 / 3

    def compute_score(correct_count, wrong_count):
        return round((correct_count * MARKS_CORRECT) + (wrong_count * MARKS_WRONG), 2)

    attempt_types = []

    # Main 3 attempt types
    for label, key, total_attempts, wrong_attempts in [
        ('Sureshot', 'sureshot', test.sureshot_attempts, test.sureshot_wrong),
        ('Applied', 'applied', test.applied_attempts, test.applied_wrong),
        ('Guesswork', 'guesswork', test.guesswork_attempts, test.guesswork_wrong),
    ]:
        correct_attempts = total_attempts - wrong_attempts
        percent_type_wrong = round((wrong_attempts / total_attempts) * 100, 2) if total_attempts > 0 else 0
        marks = compute_score(correct_attempts, wrong_attempts)

        attempt_types.append({
            'label': label,
            'key': key,
            'total': total_attempts,
            'wrong': wrong_attempts,
            'correct': correct_attempts,
            'percent_wrong': percent_type_wrong,
            'marks': marks,
            'url': f'/result/{test.id}/{key}/',
        })

    # Optional: Blind Attempt (only shown if used)
    if test.blind_wrong > 0:
        blind_correct = blind_attempts - test.blind_wrong
        blind_marks = compute_score(blind_correct, test.blind_wrong)

        attempt_types.append({
            'label': 'Blind Attempt',
            'key': 'blind',
            'total': blind_attempts,
            'wrong': test.blind_wrong,
            'correct': blind_correct,
            'percent_wrong': round((test.blind_wrong / blind_attempts) * 100, 2) if blind_attempts > 0 else 0,
            'marks': blind_marks,
            'url': f'/result/{test.id}/blind/',
        })

    context = {
        'test': test,
        'total': total,
        'correct': correct,
        'wrong': wrong,
        'attempted': attempted,
        'unattempted': unattempted,
        'score': score,
        'percent_wrong': percent_wrong,
        'attempt_types': attempt_types,
        'previous_test_id': previous_test_id,
        'next_test_id': next_test_id,
    }

    return render(request, 'result/test_result.html', context)



def attempt_type_detail(request, test_id, attempt_type):
    test = get_object_or_404(Test, id=test_id, user=request.user)  # 1 DB hit

    # Pull all logs and their linked question & subject in one query
    base_logs = QuestionLog.objects.filter(test=test).select_related('question__subject')  # 1 DB hit
    logs = base_logs

    # Apply attempt_type filter
    if attempt_type in ['sureshot', 'applied', 'guesswork', 'blind']:
        logs = logs.filter(attempt_type=attempt_type)

        result_type = request.GET.get('result')
        if result_type in ['right', 'wrong']:
            logs = logs.filter(attempt_result=result_type).exclude(attempt_type__in=['unattempted', 'blind'])
        else:
            result_type = ''
    elif attempt_type == 'right':
        logs = logs.filter(attempt_result='right').exclude(attempt_type__in=['unattempted', 'blind'])
        result_type = 'right'
    elif attempt_type == 'wrong':
        logs = logs.filter(attempt_result='wrong').exclude(attempt_type__in=['unattempted', 'blind'])
        result_type = 'wrong'
    elif attempt_type == 'unattempted':
        logs = logs.filter(attempt_type__in=['unattempted', 'blind'])
        result_type = 'unattempted'
    else:
        logs = QuestionLog.objects.none()
        result_type = ''

    # Evaluate logs only ONCE
    logs = list(logs.order_by('serial'))  # 1 DB hit (all filtering + sorting)

    # Subject count using already-fetched objects (no DB hit)
    subject_counter = Counter([log.question.subject.name for log in logs if log.question.subject])
    subjects = [{'name': name, 'count': count} for name, count in sorted(subject_counter.items())]

    subject_filter = request.GET.get('subject')
    if not subject_filter and len(subjects) == 1:
        subject_filter = subjects[0]['name']

    if subject_filter:
        logs = [log for log in logs if log.question.subject and log.question.subject.name == subject_filter]

    context = {
        'test': test,
        'logs': logs,
        'log_count': len(logs),
        'attempt_type': attempt_type.capitalize(),
        'subjects': subjects,
        'selected_subject': subject_filter,
        'selected_result': result_type,
    }

    return render(request, 'result/attempt_type_detail.html', context)




