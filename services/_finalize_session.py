# services/finalise_session.py
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.db.models import F
from django.db.models import Sum

from tests.models import (
    QuestionLog,
    QuestionAttemptSummary,
    TopicAttemptSummary,
    TopicOLTSummary,
    Test,
)
from practice.models import PracticeSession
from analysis.models import TopicStatus
from user.models import UserDailyStats   # adjust app label if different
from syllabus.models import Topic, Subject
from question.models import OLT




MARKS_RIGHT = Decimal("2.0")
MARKS_WRONG = Decimal("2.0") / Decimal("3.0")


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def finalise_session(session, mode: str) -> None:
    """
    Unified finaliser for both PracticeSession and Test.

    mode: "practice" or "test"
    """
    if mode not in ("practice", "test"):
        raise ValueError(f"Unsupported mode: {mode}")

    # 1. Guard: already completed
    if session.status == "completed":
        return

    # 2. Load logs (single query, with useful joins)
    logs = (
        session.questionlog_set
        .select_related(
            "question__topic",
            "question__subject",
            "question__olt",
            "topic",           # snapshot topic on log
        )
        .all()
    )

    if not logs:
        # Nothing to do; just mark completed and bail.
        session.status = "completed"
        session.end_time = timezone.now()
        session.save(update_fields=["status", "end_time"])
        return

    # 3. Build all aggregates once in memory
    aggregates = build_aggregates(logs, session, mode=mode)

    # 4. One transaction for all writes
    with transaction.atomic():
        update_session_row(session, aggregates)               # Test / PracticeSession
        if mode == "test":
            update_qas(aggregates)                            # QuestionAttemptSummary (test only)

        update_tas(aggregates)                                # TopicAttemptSummary
        update_topic_olt_summary(aggregates)                  # TopicOLTSummary
        update_topic_status_from_session(aggregates)          # TopicStatus / PMI
        update_user_daily_stats(aggregates)                   # UserDailyStats
        register_profile_attempts(aggregates)                 # Profile.register_attempt
        register_subscription_attempts(aggregates)            # optional, safe no-op if none


# ─────────────────────────────────────────────────────────────
# 1. Aggregation
# ─────────────────────────────────────────────────────────────

def build_aggregates(logs, session, *, mode: str) -> dict:
    """
    Single-pass aggregation over QuestionLog rows.

    Returns a dict used by all writers, shape:

    {
        "mode": "practice" | "test",
        "now": datetime,
        "user": User,
        "session": session,
        "date": date,
        "duration_hours": float,
        "total": { ... },          # session-level counts
        "per_question": {...},     # question_id -> stats   (for QAS)
        "per_topic": {...},        # topic_id -> stats      (for TAS, TopicStatus)
        "per_topic_olt": {...},    # (topic_id, olt_id) -> stats (for TopicOLTSummary)
    }
    """
    user = session.user
    now = timezone.now()
    start = session.start_time or now
    duration_seconds = max((now - start).total_seconds(), 0)
    duration_hours = duration_seconds / 3600.0

    # Session-level counters
    total_q = 0
    answered_q = 0
    correct_q = 0
    wrong_q = 0
    unattempted_q = 0

    sureshot_q = applied_q = guesswork_q = blind_q = 0
    sureshot_wrong = applied_wrong = guesswork_wrong = blind_wrong = 0

    # Per-question (for QAS, test mode only)
    per_question = defaultdict(lambda: {
        "answered_q": 0,
        "correct_q": 0,
        "wrong_q": 0,
        "sureshot_q": 0,
        "applied_q": 0,
        "guesswork_q": 0,
        "sureshot_wrong": 0,
        "applied_wrong": 0,
        "guesswork_wrong": 0,
        "topic_id": None,
    })

    # Per-topic (for TAS & TopicStatus)
    per_topic = defaultdict(lambda: {
        "answered_q": 0,
        "correct_q": 0,
        "wrong_q": 0,
        "sureshot_q": 0,
        "applied_q": 0,
        "guesswork_q": 0,
        "blind_q": 0,
        "sureshot_wrong": 0,
        "applied_wrong": 0,
        "guesswork_wrong": 0,
        "blind_wrong": 0,
    })

    # Per topic × OLT (for TopicOLTSummary)
    per_topic_olt = defaultdict(lambda: {
        "answered_q": 0,
        "correct_q": 0,
        "wrong_q": 0,
        "sureshot_q": 0,
        "applied_q": 0,
        "guesswork_q": 0,
        "sureshot_wrong": 0,
        "applied_wrong": 0,
        "guesswork_wrong": 0,
    })

    for log in logs:
        total_q += 1

        atype = (log.attempt_type or "unattempted").lower()
        result = (log.attempt_result or "").lower()

        is_attempted = atype in ("sureshot", "applied", "guesswork", "blind")
        is_correct = (result == "right") if is_attempted else False

        topic_id = log.topic_id or (log.question.topic_id if log.question else None)
        olt_id = log.question.olt_id if getattr(log.question, "olt_id", None) else None

        if not is_attempted:
            unattempted_q += 1
            continue

        # session-level
        answered_q += 1
        if is_correct:
            correct_q += 1
        else:
            wrong_q += 1

        if atype == "sureshot":
            sureshot_q += 1
            if not is_correct:
                sureshot_wrong += 1
        elif atype == "applied":
            applied_q += 1
            if not is_correct:
                applied_wrong += 1
        elif atype == "guesswork":
            guesswork_q += 1
            if not is_correct:
                guesswork_wrong += 1
        elif atype == "blind":
            blind_q += 1
            if not is_correct:
                blind_wrong += 1

        # per-question (only meaningful for test mode – but we compute anyway; writer can decide)
        q_stats = per_question[log.question_id]
        q_stats["answered_q"] += 1
        if is_correct:
            q_stats["correct_q"] += 1
        else:
            q_stats["wrong_q"] += 1

        if atype == "sureshot":
            q_stats["sureshot_q"] += 1
            if not is_correct:
                q_stats["sureshot_wrong"] += 1
        elif atype == "applied":
            q_stats["applied_q"] += 1
            if not is_correct:
                q_stats["applied_wrong"] += 1
        elif atype == "guesswork":
            q_stats["guesswork_q"] += 1
            if not is_correct:
                q_stats["guesswork_wrong"] += 1

        if topic_id and q_stats["topic_id"] is None:
            q_stats["topic_id"] = topic_id

        # per-topic
        if topic_id:
            t_stats = per_topic[topic_id]
            t_stats["answered_q"] += 1
            if is_correct:
                t_stats["correct_q"] += 1
            else:
                t_stats["wrong_q"] += 1

            if atype == "sureshot":
                t_stats["sureshot_q"] += 1
                if not is_correct:
                    t_stats["sureshot_wrong"] += 1
            elif atype == "applied":
                t_stats["applied_q"] += 1
                if not is_correct:
                    t_stats["applied_wrong"] += 1
            elif atype == "guesswork":
                t_stats["guesswork_q"] += 1
                if not is_correct:
                    t_stats["guesswork_wrong"] += 1
            elif atype == "blind":
                t_stats["blind_q"] += 1
                if not is_correct:
                    t_stats["blind_wrong"] += 1

        # per-topic × OLT
        if topic_id and olt_id:
            key = (topic_id, olt_id)
            to_stats = per_topic_olt[key]
            to_stats["answered_q"] += 1
            if is_correct:
                to_stats["correct_q"] += 1
            else:
                to_stats["wrong_q"] += 1

            if atype == "sureshot":
                to_stats["sureshot_q"] += 1
                if not is_correct:
                    to_stats["sureshot_wrong"] += 1
            elif atype == "applied":
                to_stats["applied_q"] += 1
                if not is_correct:
                    to_stats["applied_wrong"] += 1
            elif atype == "guesswork":
                to_stats["guesswork_q"] += 1
                if not is_correct:
                    to_stats["guesswork_wrong"] += 1

    # compute marks
    net_marks = (Decimal(correct_q) * MARKS_RIGHT) - (Decimal(wrong_q) * MARKS_WRONG)

    total = {
        "total_q": total_q,
        "answered_q": answered_q,
        "correct_q": correct_q,
        "wrong_q": wrong_q,
        "unattempted_q": unattempted_q,
        "sureshot_q": sureshot_q,
        "applied_q": applied_q,
        "guesswork_q": guesswork_q,
        "blind_q": blind_q,
        "sureshot_wrong": sureshot_wrong,
        "applied_wrong": applied_wrong,
        "guesswork_wrong": guesswork_wrong,
        "blind_wrong": blind_wrong,
        "net_marks": net_marks,
    }

    aggregates = {
        "mode": mode,
        "now": now,
        "user": user,
        "session": session,
        "date": timezone.localdate(now),
        "duration_hours": float(duration_hours),
        "total": total,
        "per_question": per_question,
        "per_topic": per_topic,
        "per_topic_olt": per_topic_olt,
    }
    return aggregates


# ─────────────────────────────────────────────────────────────
# 2. Writers
# ─────────────────────────────────────────────────────────────

def update_session_row(session, agg: dict) -> None:
    """Update Test or PracticeSession row from aggregates."""
    total = agg["total"]
    now = agg["now"]
    mode = agg["mode"]

    if isinstance(session, Test) or mode == "test":
        session.total_questions = total["total_q"]
        session.correct_answers = total["correct_q"]
        session.unattempted = total["unattempted_q"]
        session.total_score = total["net_marks"]

        session.sureshot_attempts = total["sureshot_q"]
        session.applied_attempts = total["applied_q"]
        session.guesswork_attempts = total["guesswork_q"]
        session.blind_attempts = total["blind_q"]

        session.sureshot_wrong = total["sureshot_wrong"]
        session.applied_wrong = total["applied_wrong"]
        session.guesswork_wrong = total["guesswork_wrong"]
        session.blind_wrong = total["blind_wrong"]

    else:  # PracticeSession
        session.total_questions = total["total_q"]
        session.correct_answers = total["correct_q"]
        session.unattempted = total["unattempted_q"]
        session.total_score = total["net_marks"]

        session.sureshot_attempts = total["sureshot_q"]
        session.applied_attempts = total["applied_q"]
        session.guesswork_attempts = total["guesswork_q"]

        session.sureshot_wrong = total["sureshot_wrong"]
        session.applied_wrong = total["applied_wrong"]
        session.guesswork_wrong = total["guesswork_wrong"]

    session.status = "completed"
    session.end_time = now
    session.save()

def update_qas(agg: dict) -> None:
    """
    Update QuestionAttemptSummary for test mode.

    per_question[qid] = {
        answered_q, correct_q, wrong_q, ..., topic_id
    }
    """
    if agg["mode"] != "test":
        return

    user = agg["user"]
    per_q = agg["per_question"]
    if not per_q:
        return

    question_ids = list(per_q.keys())
    existing = QuestionAttemptSummary.objects.filter(
        user=user,
        question_id__in=question_ids
    )
    q_map = {obj.question_id: obj for obj in existing}

    to_create = []
    to_update = []

    for qid, s in per_q.items():
        obj = q_map.get(qid)
        if not obj:
            obj = QuestionAttemptSummary(
                user=user,
                question_id=qid,
                topic_id=s["topic_id"],
            )
            q_map[qid] = obj
            to_create.append(obj)

        obj.total_attempts += s["answered_q"]
        obj.correct_attempts += s["correct_q"]
        obj.wrong_attempts += s["wrong_q"]

        obj.sureshot_attempts += s["sureshot_q"]
        obj.applied_attempts += s["applied_q"]
        obj.guesswork_attempts += s["guesswork_q"]

        obj.sureshot_wrong += s["sureshot_wrong"]
        obj.applied_wrong += s["applied_wrong"]
        obj.guesswork_wrong += s["guesswork_wrong"]

        # recompute net_marks from totals
        obj.net_marks = (
            Decimal(obj.correct_attempts) * MARKS_RIGHT
            - Decimal(obj.wrong_attempts) * MARKS_WRONG
        )
        if obj not in to_create:
            to_update.append(obj)

    if to_create:
        QuestionAttemptSummary.objects.bulk_create(to_create)

    if to_update:
        QuestionAttemptSummary.objects.bulk_update(
            to_update,
            [
                "total_attempts",
                "correct_attempts",
                "wrong_attempts",
                "sureshot_attempts",
                "applied_attempts",
                "guesswork_attempts",
                "sureshot_wrong",
                "applied_wrong",
                "guesswork_wrong",
                "net_marks",
                "last_attempted",
            ],
        )

def update_tas(agg: dict) -> None:
    """
    Update TopicAttemptSummary (per topic + mode).
    """
    user = agg["user"]
    mode = agg["mode"]
    per_topic = agg["per_topic"]
    if not per_topic:
        return

    topic_ids = list(per_topic.keys())
    existing = TopicAttemptSummary.objects.filter(
        user=user,
        topic_id__in=topic_ids,
        mode=mode,
    )
    t_map = {obj.topic_id: obj for obj in existing}

    to_create = []
    to_update = []

    for topic_id, s in per_topic.items():
        obj = t_map.get(topic_id)
        if not obj:
            obj = TopicAttemptSummary(
                user=user,
                topic_id=topic_id,
                mode=mode,
            )
            t_map[topic_id] = obj
            to_create.append(obj)

        obj.total_attempts += s["answered_q"]
        obj.correct_attempts += s["correct_q"]
        obj.wrong_attempts += s["wrong_q"]

        obj.sureshot_attempts += s["sureshot_q"]
        obj.applied_attempts += s["applied_q"]
        obj.guesswork_attempts += s["guesswork_q"]
        obj.blind_attempts += s["blind_q"]

        obj.sureshot_wrong += s["sureshot_wrong"]
        obj.applied_wrong += s["applied_wrong"]
        obj.guesswork_wrong += s["guesswork_wrong"]
        obj.blind_wrong += s["blind_wrong"]

        obj.net_marks = (
            Decimal(obj.correct_attempts) * MARKS_RIGHT
            - Decimal(obj.wrong_attempts) * MARKS_WRONG
        )
        if obj not in to_create:
            to_update.append(obj)

    if to_create:
        TopicAttemptSummary.objects.bulk_create(to_create)

    if to_update:
        TopicAttemptSummary.objects.bulk_update(
            to_update,
            [
                "total_attempts",
                "correct_attempts",
                "wrong_attempts",
                "sureshot_attempts",
                "applied_attempts",
                "guesswork_attempts",
                "blind_attempts",
                "sureshot_wrong",
                "applied_wrong",
                "guesswork_wrong",
                "blind_wrong",
                "net_marks",
                "last_updated",
            ],
        )

def update_topic_olt_summary(agg: dict) -> None:
    """
    Update TopicOLTSummary from per_topic_olt aggregates.
    """
    user = agg["user"]
    mode = agg["mode"]
    per_to = agg["per_topic_olt"]
    if not per_to:
        return

    keys = list(per_to.keys())  # (topic_id, olt_id)
    topic_ids = [k[0] for k in keys]
    olt_ids = [k[1] for k in keys]

    existing = TopicOLTSummary.objects.filter(
        user=user,
        topic_id__in=topic_ids,
        olt_id__in=olt_ids,
        mode=mode,
    )
    m = {(obj.topic_id, obj.olt_id): obj for obj in existing}

    to_create = []
    to_update = []

    # Need subject for new rows – we can derive via Topic
    topics = {t.id: t for t in Topic.objects.filter(id__in=topic_ids)}

    for (topic_id, olt_id), s in per_to.items():
        obj = m.get((topic_id, olt_id))
        if not obj:
            topic = topics.get(topic_id)
            obj = TopicOLTSummary(
                user=user,
                subject=topic.section.subject if topic and topic.section else None,
                topic_id=topic_id,
                olt_id=olt_id,
                mode=mode,
            )
            m[(topic_id, olt_id)] = obj
            to_create.append(obj)

        obj.total_attempts += s["answered_q"]
        obj.correct_attempts += s["correct_q"]
        obj.wrong_attempts += s["wrong_q"]

        obj.sureshot_attempts += s["sureshot_q"]
        obj.applied_attempts += s["applied_q"]
        obj.guesswork_attempts += s["guesswork_q"]

        obj.sureshot_wrong += s["sureshot_wrong"]
        obj.applied_wrong += s["applied_wrong"]
        obj.guesswork_wrong += s["guesswork_wrong"]

        obj.net_marks = (
            Decimal(obj.correct_attempts) * MARKS_RIGHT
            - Decimal(obj.wrong_attempts) * MARKS_WRONG
        )
        if obj not in to_create:
            to_update.append(obj)

    if to_create:
        TopicOLTSummary.objects.bulk_create(to_create)

    if to_update:
        TopicOLTSummary.objects.bulk_update(
            to_update,
            [
                "total_attempts",
                "correct_attempts",
                "wrong_attempts",
                "sureshot_attempts",
                "applied_attempts",
                "guesswork_attempts",
                "sureshot_wrong",
                "applied_wrong",
                "guesswork_wrong",
                "net_marks",
                "last_updated",
            ],
        )

def update_topic_status_from_session(agg: dict) -> None:
    """
    Hook into TopicStatus.

    For now:
    - In practice mode: call your PMI helper for each topic.
    - In test mode: increment TopicStatus.test_questions_attempted.
    """
    user = agg["user"]
    mode = agg["mode"]
    per_topic = agg["per_topic"]
    if not per_topic:
        return

    topic_ids = list(per_topic.keys())
    statuses = {
        ts.topic_id: ts
        for ts in TopicStatus.objects.filter(user=user, topic_id__in=topic_ids)
    }

    if mode == "practice":
        # Compute PMI for each topic using existing helper
        for topic_id in topic_ids:
            topic = Topic.objects.get(pk=topic_id)
            _compute_and_update_topic_pmi(user, topic)
    else:  # test mode
        for topic_id, s in per_topic.items():
            ts = statuses.get(topic_id)
            if not ts:
                topic = Topic.objects.get(pk=topic_id)
                ts = TopicStatus.objects.create(
                    user=user,
                    topic=topic,
                    exam=topic.section.subject.exam,
                    subject=topic.section.subject,
                    section=topic.section,
                    practice_rounds=0,
                    test_questions_attempted=0,
                )
                statuses[topic_id] = ts
            ts.test_questions_attempted = F("test_questions_attempted") + s["answered_q"]
            ts.save(update_fields=["test_questions_attempted"])

def update_user_daily_stats(agg: dict) -> None:
    """
    Update UserDailyStats for this user and date.
    """
    user = agg["user"]
    date = agg["date"]
    mode = agg["mode"]
    total = agg["total"]
    hours = agg["duration_hours"]

    uds, _ = UserDailyStats.objects.get_or_create(
        user=user,
        date=date,
        defaults={},
    )

    uds.total_attempts += total["answered_q"]
    uds.total_correct += total["correct_q"]
    uds.total_wrong += total["wrong_q"]

    uds.sureshot_attempts += total["sureshot_q"]
    uds.applied_attempts += total["applied_q"]
    uds.guess_attempts += total["guesswork_q"]

    uds.sureshot_wrong += total["sureshot_wrong"]
    uds.applied_wrong += total["applied_wrong"]
    uds.guess_wrong += total["guesswork_wrong"]

    if mode == "practice":
        uds.practice_time += hours
    else:
        uds.test_time += hours

    uds.save()

def register_profile_attempts(agg: dict) -> None:
    """
    Bump profile streak counters using register_attempt.
    """
    user = agg["user"]
    attempt_count = agg["total"]["answered_q"]
    if attempt_count and hasattr(user, "profile"):
        user.profile.register_attempt(increment=attempt_count)

def register_subscription_attempts(agg: dict) -> None:
    """
    Optional: count usage against Subscription plan.
    Safe no-op if user has no subscription.
    """
    user = agg["user"]
    attempt_count = agg["total"]["answered_q"]
    sub = getattr(user, "subscription", None)
    if attempt_count and sub:
        # strict=False so it never raises here; you can enforce limits earlier.
        sub.count_attempts(increment=attempt_count, strict=False)

def _compute_and_update_topic_pmi(user, topic) -> None:
    """
    Compute PMI over the last N completed practice sessions for (user, topic)
    using aggregated fields stored on PracticeSession.

    Rules:
      - Only last N sessions (default N=3 via ABL_PMI_WINDOW) are considered
        for the PMI window.
      - PMI can be negative (penalties > rewards).
      - PMI is capped at 100 on the upper side (no lower clamp).
      - If only 1 session in window, cap positive PMI at 55% (negatives allowed).
      - practice_rounds = total completed practice sessions for that topic.
      - Also store TopicStatus.subject, section, exam from Topic.
    """
    N =  3

    # All completed sessions for this user+topic, latest first.
    # Because this is called AFTER update_session_row() inside the same
    # transaction.atomic(), this queryset *will* see the just-updated session.
    base_qs = (
        PracticeSession.objects
        .filter(user=user, topic=topic, status="completed")
        .order_by("-end_time")
    )

    total_session_count = base_qs.count()
    if total_session_count == 0:
        return

    # PMI window = last N sessions
    recent_ids = list(base_qs.values_list("id", flat=True)[:N])
    window_session_count = len(recent_ids)

    window_qs = PracticeSession.objects.filter(id__in=recent_ids)

    agg = window_qs.aggregate(
        S_a=Sum("sureshot_attempts"),
        A_a=Sum("applied_attempts"),
        G_a=Sum("guesswork_attempts"),

        S_w=Sum("sureshot_wrong"),
        A_w=Sum("applied_wrong"),
        G_w=Sum("guesswork_wrong"),
    )

    # Coalesce None → 0
    S_a = agg["S_a"] or 0
    A_a = agg["A_a"] or 0
    G_a = agg["G_a"] or 0

    S_w = agg["S_w"] or 0
    A_w = agg["A_w"] or 0
    G_w = agg["G_w"] or 0

    # Rights (guard against negatives per type)
    S_r = max(S_a - S_w, 0)
    A_r = max(A_a - A_w, 0)
    G_r = max(G_a - G_w, 0)

    denom = S_a + A_a + G_a

    if denom <= 0:
        pmi_pct = 0.0
    else:
        # Your PMI formula:
        # reward = Sr*2 + Ar*1.5 + Gr*0.75
        # penalty = Sw*0.75 + Aw*0.5
        # pmi_raw = (reward - penalty) / (denom * 2.0)
        reward = S_r * 2.0 + A_r * 1.5 + G_r * 0.75
        penalty = S_w * 0.75 + A_w * 0.5

        pmi_raw = (reward - penalty) / (denom * 2.0)
        pmi_pct = pmi_raw * 100.0

        # Upper cap
        if pmi_pct > 100.0:
            pmi_pct = 100.0

        # First-session-in-window positive cap at 55%
        if window_session_count == 1 and pmi_pct > 55.0:
            pmi_pct = 55.0

    # Pull subject/section/exam from topic
    section = topic.section
    subject = section.subject
    exam = subject.exam

    # Upsert TopicStatus for this user+topic
    topic_status, _ = TopicStatus.objects.get_or_create(
        user=user,
        topic=topic,
        defaults={
            "pmi": pmi_pct,
            "practice_rounds": total_session_count,
            "section": section,
            "subject": subject,
            "exam": exam,
        },
    )

    # Update fields in one shot
    topic_status.pmi = pmi_pct
    topic_status.practice_rounds = total_session_count
    topic_status.section = section
    topic_status.subject = subject
    topic_status.exam = exam

    # If you have updated_at and it's not auto_now
    if hasattr(topic_status, "updated_at"):
        topic_status.updated_at = timezone.now()

    topic_status.save()

    print(
        f"PMI for {user.username} / {topic.name} updated to "
        f"{pmi_pct:.2f} over last {window_session_count} sessions "
        f"(total={total_session_count})"
    )