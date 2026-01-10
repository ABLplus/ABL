# finalize.py
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from tests.models import (
    QuestionLog,
    QuestionAttemptSummary,
    TopicAttemptSummary,
    TopicOLTSummary,
    Test,
)
from practice.models import PracticeSession
from analysis.models import TopicStatus
from user.models import UserDailyStats
from syllabus.models import Topic
from practice.views import _compute_and_update_topic_pmi


# ─────────────────────────────────────────────────────────────
# Marks (UPSC Prelims style)
# ─────────────────────────────────────────────────────────────
MARKS_RIGHT = Decimal("2.0")
MARKS_WRONG = Decimal("2.0") / Decimal("3.0")


# ─────────────────────────────────────────────────────────────
# TMI config (v1)
# ─────────────────────────────────────────────────────────────
TMI_WINDOW_N = 30
TMI_MIN_ATTEMPTED = 10

ATTEMPTED_TOKENS = {"sr", "sw", "ar", "aw", "gr", "gw"}

TMI_WEIGHTS = {
    "sr": Decimal("1.00"),
    "ar": Decimal("0.90"),
    "gr": Decimal("0.60"),
    "sw": Decimal("-0.45"),
    "aw": Decimal("-0.35"),
    "gw": Decimal("-0.25"),
    "na": Decimal("0.00"),
}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _token_from_log(log: QuestionLog) -> str:
    """
    Map QuestionLog -> token in {sr, sw, ar, aw, gr, gw, na}

    Rules:
      - blind is treated as unattempted => na (for mastery window)
      - unattempted/None => na
    """
    atype = (log.attempt_type or "unattempted").lower()
    result = (log.attempt_result or "").lower()

    if atype in ("unattempted", "blind", "", None):
        return "na"

    if atype == "sureshot":
        return "sr" if result == "right" else "sw"
    if atype == "applied":
        return "ar" if result == "right" else "aw"
    if atype == "guesswork":
        return "gr" if result == "right" else "gw"

    # Unknown attempt type -> safe default
    return "na"


def _compute_tmi_from_window(tokens: list[str]) -> tuple[Decimal | None, int]:
    """
    Compute TMI from a rolling window list of tokens.

    Rule:
      - Only attempted tokens are counted for the average (sr/sw/ar/aw/gr/gw)
      - If attempted_count < TMI_MIN_ATTEMPTED => TMI is None
      - Else TMI = average(weight(token)) over attempted tokens

    Returns:
      (tmi_decimal_or_none, attempted_count_in_window)
    """
    if not tokens:
        return None, 0

    attempted = [t for t in tokens if t in ATTEMPTED_TOKENS]
    n = len(attempted)

    if n < TMI_MIN_ATTEMPTED:
        return None, n

    score_sum = sum((TMI_WEIGHTS[t] for t in attempted), Decimal("0.00"))
    tmi = score_sum / Decimal(n)
    return tmi, n


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

    # Optional strict type guard (keeps bugs loud)
    if mode == "test" and not isinstance(session, Test):
        raise TypeError("mode='test' but session is not a Test instance")
    if mode == "practice" and not isinstance(session, PracticeSession):
        raise TypeError("mode='practice' but session is not a PracticeSession instance")

    # Guard: already completed
    if session.status == "completed":
        return

    # ✅ Load logs from QuestionLog model (NOT session.questionlog_set)
    logs_qs = (
        QuestionLog.objects.select_related(
            "question__topic",
            "question__subject",
            "question__olt",
            "topic",  # snapshot topic on log
        )
        .order_by("timestamp")
    )

    if mode == "test":
        logs_qs = logs_qs.filter(test=session)
    else:
        logs_qs = logs_qs.filter(practiceSession=session)

    logs = list(logs_qs)

    if not logs:
        print("No QuestionLog entries found for session:", session.id)
        return

    aggregates = build_aggregates(logs, session, mode=mode)

    with transaction.atomic():
        update_session_row(session, aggregates)

        if mode == "test":
            update_qas(aggregates)

        update_tas(aggregates)
        # update_topic_olt_summary(aggregates)
        update_topic_status_from_session(aggregates)
        update_user_daily_stats(aggregates)
        register_profile_attempts(aggregates)
        # register_subscription_attempts(aggregates)


def build_aggregates(logs, session, *, mode: str) -> dict:
    """
    Single-pass aggregation over QuestionLog rows.

    Returns a dict used by all writers:

    {
        "mode": "practice" | "test",
        "now": datetime,
        "user": User,
        "session": session,
        "date": date,
        "duration_hours": float,
        "total": { ... },              # session-level counts (incl blind_* for Test)
        "per_question": {...},         # question_id -> stats   (for QAS)
        "per_topic": {...},            # topic_id -> stats      (for TAS, TopicStatus)
        "per_topic_olt": {...},        # (topic_id, olt_id) -> stats (for TopicOLTSummary)
        "per_topic_tokens": {...},     # topic_id -> [tokens]   (TEST only)
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

    # Keep blind separate for Test model reporting
    blind_q = 0
    blind_wrong = 0  # typically 0; kept for schema compatibility

    sureshot_q = applied_q = guesswork_q = 0
    sureshot_wrong = applied_wrong = guesswork_wrong = 0

    # Per-question (for QAS)
    per_question = defaultdict(
        lambda: {
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
        }
    )

    # Per-topic (for TAS & TopicStatus)
    per_topic = defaultdict(
        lambda: {
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
        }
    )

    # Per topic × OLT (for TopicOLTSummary)
    per_topic_olt = defaultdict(
        lambda: {
            "answered_q": 0,
            "correct_q": 0,
            "wrong_q": 0,
            "sureshot_q": 0,
            "applied_q": 0,
            "guesswork_q": 0,
            "sureshot_wrong": 0,
            "applied_wrong": 0,
            "guesswork_wrong": 0,
        }
    )

    # TEST-only: token payload to merge into TAS rolling window later
    per_topic_tokens = defaultdict(list)

    for log in logs:
        total_q += 1

        atype_raw = (log.attempt_type or "unattempted").lower()
        token = _token_from_log(log)  # blind/unattempted -> "na"

        # topic and olt ids
        topic_id = log.topic_id or (log.question.topic_id if log.question else None)
        olt_id = getattr(log.question, "olt_id", None)

        # collect tokens for TEST window (even "na" matters)
        if mode == "test" and topic_id:
            per_topic_tokens[topic_id].append(token)

        # Blind: count separately, but treat as unattempted for score/mastery
        if atype_raw == "blind":
            blind_q += 1
            if topic_id:
                per_topic[topic_id]["blind_q"] += 1
            unattempted_q += 1
            continue

        # Unattempted (non-blind)
        if token == "na":
            unattempted_q += 1
            continue

        # Attempted
        answered_q += 1
        is_correct = token in ("sr", "ar", "gr")
        if is_correct:
            correct_q += 1
        else:
            wrong_q += 1

        # Session-level attempt type
        if token in ("sr", "sw"):
            sureshot_q += 1
            if token == "sw":
                sureshot_wrong += 1
        elif token in ("ar", "aw"):
            applied_q += 1
            if token == "aw":
                applied_wrong += 1
        elif token in ("gr", "gw"):
            guesswork_q += 1
            if token == "gw":
                guesswork_wrong += 1

        # Per-question
        q_stats = per_question[log.question_id]
        q_stats["answered_q"] += 1
        if is_correct:
            q_stats["correct_q"] += 1
        else:
            q_stats["wrong_q"] += 1

        if token in ("sr", "sw"):
            q_stats["sureshot_q"] += 1
            if token == "sw":
                q_stats["sureshot_wrong"] += 1
        elif token in ("ar", "aw"):
            q_stats["applied_q"] += 1
            if token == "aw":
                q_stats["applied_wrong"] += 1
        elif token in ("gr", "gw"):
            q_stats["guesswork_q"] += 1
            if token == "gw":
                q_stats["guesswork_wrong"] += 1

        if topic_id and q_stats["topic_id"] is None:
            q_stats["topic_id"] = topic_id

        # Per-topic
        if topic_id:
            t_stats = per_topic[topic_id]
            t_stats["answered_q"] += 1
            if is_correct:
                t_stats["correct_q"] += 1
            else:
                t_stats["wrong_q"] += 1

            if token in ("sr", "sw"):
                t_stats["sureshot_q"] += 1
                if token == "sw":
                    t_stats["sureshot_wrong"] += 1
            elif token in ("ar", "aw"):
                t_stats["applied_q"] += 1
                if token == "aw":
                    t_stats["applied_wrong"] += 1
            elif token in ("gr", "gw"):
                t_stats["guesswork_q"] += 1
                if token == "gw":
                    t_stats["guesswork_wrong"] += 1

        # Per-topic × OLT
        if topic_id and olt_id:
            key = (topic_id, olt_id)
            to_stats = per_topic_olt[key]
            to_stats["answered_q"] += 1
            if is_correct:
                to_stats["correct_q"] += 1
            else:
                to_stats["wrong_q"] += 1

            if token in ("sr", "sw"):
                to_stats["sureshot_q"] += 1
                if token == "sw":
                    to_stats["sureshot_wrong"] += 1
            elif token in ("ar", "aw"):
                to_stats["applied_q"] += 1
                if token == "aw":
                    to_stats["applied_wrong"] += 1
            elif token in ("gr", "gw"):
                to_stats["guesswork_q"] += 1
                if token == "gw":
                    to_stats["guesswork_wrong"] += 1

    net_marks = (Decimal(correct_q) * MARKS_RIGHT) - (Decimal(wrong_q) * MARKS_WRONG)

    total = {
        "total_q": total_q,
        "answered_q": answered_q,
        "correct_q": correct_q,
        "wrong_q": wrong_q,
        "unattempted_q": unattempted_q,
        "blind_q": blind_q,
        "blind_wrong": blind_wrong,
        "sureshot_q": sureshot_q,
        "applied_q": applied_q,
        "guesswork_q": guesswork_q,
        "sureshot_wrong": sureshot_wrong,
        "applied_wrong": applied_wrong,
        "guesswork_wrong": guesswork_wrong,
        "net_marks": net_marks,
    }

    return {
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
        "per_topic_tokens": per_topic_tokens,
    }


def update_session_row(session, agg: dict) -> None:
    """
    Update Test or PracticeSession row from aggregates.

    Blind is treated as 'na' for the TMI rolling window,
    but still reported on Test model as blind_attempts.
    """
    total = agg["total"]
    now = agg["now"]
    mode = agg["mode"]

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

    if isinstance(session, Test) or mode == "test":
        session.blind_attempts = total.get("blind_q", 0)
        session.blind_wrong = total.get("blind_wrong", 0)

    session.status = "completed"
    session.end_time = now
    session.save()


def update_qas(agg: dict) -> None:
    """
    Update QuestionAttemptSummary for TEST mode only.
    """
    if agg["mode"] != "test":
        return

    user = agg["user"]
    now = agg["now"]
    per_q = agg["per_question"]
    if not per_q:
        return

    question_ids = list(per_q.keys())

    existing = QuestionAttemptSummary.objects.filter(user=user, question_id__in=question_ids)
    q_map = {obj.question_id: obj for obj in existing}

    to_create = []
    to_update = []

    for qid, s in per_q.items():
        obj = q_map.get(qid)
        if not obj:
            obj = QuestionAttemptSummary(user=user, question_id=qid, topic_id=s.get("topic_id"))
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

        obj.net_marks = (
            Decimal(obj.correct_attempts) * MARKS_RIGHT
            - Decimal(obj.wrong_attempts) * MARKS_WRONG
        )

        if hasattr(obj, "last_attempted"):
            obj.last_attempted = now

        if obj not in to_create:
            to_update.append(obj)

    if to_create:
        QuestionAttemptSummary.objects.bulk_create(to_create)

    if to_update:
        fields = [
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
        ]
        if hasattr(QuestionAttemptSummary, "last_attempted"):
            fields.append("last_attempted")

        QuestionAttemptSummary.objects.bulk_update(to_update, fields)


def update_tas(agg: dict) -> None:
    """
    Update TopicAttemptSummary (per topic + mode).

    FIX:
    - In test mode, topics may have ONLY "na" tokens (all unattempted).
      Those topics must still get a TAS row so the rolling window is complete.
    """
    user = agg["user"]
    mode = agg["mode"]
    now = agg["now"]

    per_topic = agg.get("per_topic", {})                  # attempted aggregates
    per_topic_tokens = agg.get("per_topic_tokens", {})    # includes na tokens (test)

    if mode == "test":
        topic_ids = list(set(per_topic.keys()) | set(per_topic_tokens.keys()))
    else:
        topic_ids = list(per_topic.keys())

    if not topic_ids:
        return

    existing = TopicAttemptSummary.objects.filter(
        user=user,
        topic_id__in=topic_ids,
        mode=mode,
    )
    t_map = {obj.topic_id: obj for obj in existing}

    to_create = []
    to_update = []

    for topic_id in topic_ids:
        obj = t_map.get(topic_id)
        if not obj:
            obj = TopicAttemptSummary(user=user, topic_id=topic_id, mode=mode)
            t_map[topic_id] = obj
            to_create.append(obj)

        # ─────────────────────────────────────────────
        # 1) Attempted aggregates (only if present)
        # ─────────────────────────────────────────────
        s = per_topic.get(topic_id)
        if s:
            obj.total_attempts += s["answered_q"]
            obj.correct_attempts += s["correct_q"]
            obj.wrong_attempts += s["wrong_q"]

            obj.sureshot_attempts += s["sureshot_q"]
            obj.applied_attempts += s["applied_q"]
            obj.guesswork_attempts += s["guesswork_q"]

            obj.sureshot_wrong += s["sureshot_wrong"]
            obj.applied_wrong += s["applied_wrong"]
            obj.guesswork_wrong += s["guesswork_wrong"]

            if mode == "test":
                obj.blind_attempts += s.get("blind_q", 0)
                obj.blind_wrong += s.get("blind_wrong", 0)

        # ─────────────────────────────────────────────
        # 2) Test-only: seen counters + rolling window
        # ─────────────────────────────────────────────
        if mode == "test":
            new_tokens = per_topic_tokens.get(topic_id, [])
            if new_tokens:
                seen_inc = len(new_tokens)

                # seen = total questions from this topic that appeared in tests
                
                obj.total_test_questions += seen_inc

                existing_window = list(obj.last_n_questions_test or [])
                obj.last_n_questions_test = (existing_window + new_tokens)[-TMI_WINDOW_N:]

        # ─────────────────────────────────────────────
        # 3) Net marks (from cumulative totals)
        # ─────────────────────────────────────────────
        obj.net_marks = (
            Decimal(obj.correct_attempts) * MARKS_RIGHT
            - Decimal(obj.wrong_attempts) * MARKS_WRONG
        )

        # bulk_update won’t trigger auto_now
        obj.last_updated = now

        if obj not in to_create:
            to_update.append(obj)

    if to_create:
        TopicAttemptSummary.objects.bulk_create(to_create)

    if to_update:
        TopicAttemptSummary.objects.bulk_update(
            to_update,
            [
                "total_test_questions",
                
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
                "last_n_questions_test",
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
        user=user, topic_id__in=topic_ids, olt_id__in=olt_ids, mode=mode
    )
    m = {(obj.topic_id, obj.olt_id): obj for obj in existing}

    to_create = []
    to_update = []

    # Need Topic for deriving subject (if your TopicOLTSummary requires it)
    topics = {t.id: t for t in Topic.objects.select_related("section__subject").filter(id__in=topic_ids)}

    for (topic_id, olt_id), s in per_to.items():
        obj = m.get((topic_id, olt_id))
        if not obj:
            topic = topics.get(topic_id)
            obj = TopicOLTSummary(
                user=user,
                subject=(topic.section.subject if topic and topic.section else None),
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
                "last_updated",  # if you have auto_now here, bulk_update needs manual set (you can set it like TAS)
            ],
        )


def update_topic_status_from_session(agg: dict) -> None:
    """
    Update TopicStatus after a session submit.

    v1:
      - practice: compute/update PMI via _compute_and_update_topic_pmi(user, topic)
      - test: update seen/attempted counters, compute TCI, compute TMI from TAS rolling window

    Notes:
      - Uses bulk_create/bulk_update to avoid 100 individual ts.save() calls.
      - Because bulk_* does NOT trigger auto_now/auto_now_add, we set created_at/updated_at manually.
    """
    user = agg["user"]
    mode = agg["mode"]
    now = agg["now"]
    per_topic = agg["per_topic"]
    if not per_topic:
        return

    topic_ids = list(per_topic.keys())

    # Existing TopicStatus rows for these topics
    statuses = {
        ts.topic_id: ts
        for ts in TopicStatus.objects.filter(user=user, topic_id__in=topic_ids)
    }

    # PRACTICE MODE: keep your existing PMI path (this function likely writes TopicStatus itself)
    if mode == "practice":
        topics = Topic.objects.filter(id__in=topic_ids)
        for topic in topics:
            _compute_and_update_topic_pmi(user, topic)
        return

    # ─────────────────────────────────────────────
    # TEST MODE
    # ─────────────────────────────────────────────

    # Seen/attempted increments in *this* session
    per_topic_tokens = agg.get("per_topic_tokens", {})
    seen_by_topic = {tid: len(per_topic_tokens.get(tid, [])) for tid in topic_ids}
    attempted_by_topic = {tid: per_topic[tid]["answered_q"] for tid in topic_ids}

    # TAS rolling windows (already updated by update_tas() earlier in the same transaction)
    tas_rows = TopicAttemptSummary.objects.filter(
        user=user,
        topic_id__in=topic_ids,
        mode="test",
    ).only("topic_id", "last_n_questions_test")
    window_by_topic = {t.topic_id: (t.last_n_questions_test or []) for t in tas_rows}

    # Topic objects for new TopicStatus rows
    topics = {
        t.id: t
        for t in Topic.objects.select_related("section__subject__exam").filter(id__in=topic_ids)
    }

    to_create = []
    to_update = []

    for topic_id in topic_ids:
        topic = topics.get(topic_id)
        if not topic:
            continue

        ts = statuses.get(topic_id)
        is_new = False

        if not ts:
            ts = TopicStatus(
                user=user,
                topic=topic,
                section=topic.section,
                subject=topic.section.subject,
                exam=topic.section.subject.exam,
            )
            statuses[topic_id] = ts
            is_new = True

        # increments
        seen_inc = int(seen_by_topic.get(topic_id, 0))
        attempted_inc = int(attempted_by_topic.get(topic_id, 0))

        ts.test_questions_seen = int(ts.test_questions_seen or 0) + seen_inc
        ts.test_questions_attempted = int(ts.test_questions_attempted or 0) + attempted_inc

        # TCI = attempted/seen
        if ts.test_questions_seen > 0:
            tci = float(ts.test_questions_attempted / ts.test_questions_seen) * 100.0
            ts.tci = round(tci, 2)
        else:
            ts.tci = None

        # TMI from rolling window tokens
        window = window_by_topic.get(topic_id, [])
        tmi_value, _attempted_in_window = _compute_tmi_from_window(window)
        ts.tmi = float(tmi_value) if tmi_value is not None else None

        # bulk_* won't run auto_now / auto_now_add, so set manually
        ts.updated_at = now
        if is_new:
            ts.created_at = now
            to_create.append(ts)
        else:
            to_update.append(ts)

    if to_create:
        TopicStatus.objects.bulk_create(to_create)

    if to_update:
        TopicStatus.objects.bulk_update(
            to_update,
            [
                "test_questions_seen",
                "test_questions_attempted",
                "tci",
                "tmi",
                "updated_at",
            ],
        )



def update_user_daily_stats(agg: dict) -> None:
    """
    Update UserDailyStats for this user & date.

    Time normalization:
      - expected_time = total_q * 2 minutes
      - if actual_time > expected_time * 1.25:
            use expected_time (convert to hours)
        else:
            use actual_time (hours)
    """
    user = agg["user"]
    date = agg["date"]
    mode = agg["mode"]
    total = agg["total"]

    uds, _ = UserDailyStats.objects.get_or_create(user=user, date=date)

    uds.total_attempts += total["answered_q"]
    uds.total_correct += total["correct_q"]
    uds.total_wrong += total["wrong_q"]

    uds.sureshot_attempts += total["sureshot_q"]
    uds.applied_attempts += total["applied_q"]
    uds.guesswork_attempts += total["guesswork_q"]

    uds.sureshot_wrong += total["sureshot_wrong"]
    uds.applied_wrong += total["applied_wrong"]
    uds.guesswork_wrong += total["guesswork_wrong"]

    actual_hours = float(agg["duration_hours"])

    total_q = int(total.get("total_q", 0))
    expected_minutes = total_q * 2.0
    expected_hours = expected_minutes / 60.0

    max_allowed_hours = expected_hours * 1.25

    if expected_hours > 0 and actual_hours > max_allowed_hours:
        hours_to_add = expected_hours
    else:
        hours_to_add = actual_hours

    if mode == "practice":
        uds.practice_time += hours_to_add
    else:
        uds.test_time += hours_to_add

    uds.save()


def register_profile_attempts(agg: dict) -> None:
    """
    Bump profile streak counters using register_attempt.
    """
    user = agg["user"]
    attempt_count = agg["total"]["answered_q"]
    if attempt_count and hasattr(user, "profile"):
        user.profile.register_attempt(increment=attempt_count)


