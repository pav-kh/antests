import asyncio
import logging
import math
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Question, TestSession
from app.generation.open_seed import SEED_OPEN_QUESTIONS
from app.generation.planner import LEVEL_MULTI_TARGET

logger = logging.getLogger(__name__)

# Topics that naturally carry an embedded artifact (code/SQL/JSON/XML/diagram).
# Used to steer the artifact quota toward questions where an artifact is
# pedagogically appropriate instead of bolted on.
ARTIFACT_TOPICS = {
    "data", "integration", "modeling", "architecture", "fundamentals", "security",
}

# Per-level override of artifact-friendly topics. ba only gets diagrams on
# modeling/process_analysis; base/specialist get NO artifacts (empty set) — code
# and data artifacts lost their pedagogical value there. Levels absent here use
# ARTIFACT_TOPICS.
LEVEL_ARTIFACT_TOPICS = {
    "ba": {"modeling", "process_analysis"},
    "base": set(),
    "specialist": set(),
}
# Levels whose artifacts must be Mermaid diagrams only (no sql/json/xml/code).
LEVEL_ARTIFACT_MERMAID_ONLY = {"ba"}

# How many LLM candidates the pool-based open generation produces (ba only).
LLM_OPEN_CANDIDATES = 3
# Open questions per session, per level. base/specialist=3, ba=2, default 2.
LEVEL_OPEN_COUNT = {"base": 3, "specialist": 3, "ba": 2}
DEFAULT_OPEN_COUNT = 2

# Hard multi-quota: after closed generation, if the share of multi-answer
# questions is below LEVEL_MULTI_TARGET, regenerate excess single questions as
# multi — up to this many passes, then accept whatever we reached.
MULTI_TOPUP_ROUNDS = 3
# Themed open questions for base/specialist: (topic_title, hint). Each is one
# LLM-generated open question via generate_open_on_topic.
OPEN_TOPICS_BASE_SPEC = [
    ("Описание интеграции",
     "Опиши, как ты подойдёшь к описанию интеграции между системами: какие "
     "требования к интеграции собрать, какие уточняющие вопросы задать (формат, "
     "протокол, объёмы, SLA, ошибки), какие критерии приёмки зафиксировать и "
     "какие риски/ошибки учесть (сбои, задержки, недоступность внешней системы, "
     "идемпотентность, ретраи)."),
    ("Системное мышление",
     "Кейс на системное мышление: декомпозиция задачи, выявление связей и "
     "зависимостей между компонентами, границы системы, причинно-следственные "
     "связи, целостный взгляд на проблему вместо локального."),
]
# Levels that use the fixed themed-open composition (1 random seed + the themed
# questions above). Levels absent here use the seed+LLM pool (e.g. ba).
LEVEL_OPEN_THEMED = {"base": OPEN_TOPICS_BASE_SPEC, "specialist": OPEN_TOPICS_BASE_SPEC}


def _sample_open_pool(pool, k, rng):
    """Pick k distinct items from pool using rng. Returns <=k items (all of pool
    if it has fewer than k). Seeded rng → deterministic, reproducible choice."""
    if len(pool) <= k:
        return list(pool)
    return rng.sample(pool, k)


class Generator:
    def __init__(self, session: AsyncSession, client, batch_size=10,
                 max_slot_retries=2, max_batch_retries=3):
        self.db = session
        self.client = client
        self.batch_size = batch_size
        self.max_slot_retries = max_slot_retries
        self.max_batch_retries = max_batch_retries

    async def run(self, session_id, plan):
        session = await self.db.get(TestSession, session_id)
        if session is None:
            return
        try:
            seq = session.generated_count
            # Artifact quota: aim for ~15% (target) but never exceed 20% (cap).
            # The target drives whether we ASK the model for an artifact; the cap
            # is a hard ceiling enforced when STORING — any extra artifact the
            # model adds on its own past the cap is stripped to text-only.
            total_questions = sum(c for _, c in plan)
            artifact_target = max(1, math.ceil(0.15 * total_questions))
            artifact_cap = math.floor(0.20 * total_questions)
            artifact_count = 0
            # Spread artifacts across DISTINCT topics instead of dumping the
            # whole quota on the first artifact-friendly topic(s). We request an
            # artifact at most once per topic; combined with the post-generation
            # shuffle below, artifacts end up interspersed rather than clustered
            # at the start of the test.
            artifact_topics_used = set()
            multi_ratio = LEVEL_MULTI_TARGET.get(session.level)
            artifact_topics = LEVEL_ARTIFACT_TOPICS.get(session.level, ARTIFACT_TOPICS)
            mermaid_only = session.level in LEVEL_ARTIFACT_MERMAID_ONLY
            # SESSION-WIDE dedup: a stem seen in ANY topic blocks an identical one
            # later, and we feed recently-generated stems back to the model so it
            # diversifies. Per-topic-only dedup let near-duplicates slip across
            # topics in a long (120-question) Specialist test.
            seen_stems: set[str] = set()
            recent_stems: list[str] = []
            # Process one topic at a time. Routing questions by the model's
            # returned topic_id is unreliable — the model echoes the topic TITLE
            # (or a paraphrase), not the canonical key — so we generate per topic
            # and stamp the known key ourselves. This prevents an infinite loop
            # where every question is discarded for a "mismatched" topic_id.
            for topic_id, count in plan:
                needed = count
                attempts = 0
                max_attempts = (count + 1) * (self.max_slot_retries + 1)
                while needed > 0 and attempts < max_attempts:
                    attempts += 1
                    take = min(needed, self.batch_size)
                    # Only request artifacts on artifact-friendly topics, and
                    # only while we still owe the session its quota.
                    want_artifact = (
                        topic_id in artifact_topics
                        and artifact_count < artifact_target
                        and topic_id not in artifact_topics_used
                    )
                    batch = await self._generate_with_retry(
                        session.level, session.mode, [(topic_id, take)],
                        avoid_stems=recent_stems, want_artifact=want_artifact,
                        multi_ratio=multi_ratio, mermaid_only=mermaid_only,
                    )
                    for q in batch.questions:
                        if needed <= 0:
                            break
                        verdict = await self.client.validate_question(q)
                        if not verdict.valid:
                            continue
                        norm = q.stem.strip().lower()
                        if norm in seen_stems:
                            continue
                        seen_stems.add(norm)
                        seq += 1
                        # Enforce artifact policy. The model may volunteer an
                        # artifact even when we didn't request one, so strip it
                        # when (a) the level disallows artifacts entirely (empty
                        # artifact_topics, e.g. base/specialist), or (b) we're
                        # already at the 20% ceiling. Otherwise store as-is.
                        kind = q.artifact_kind
                        content = q.artifact_content
                        if kind != "none" and (
                            not artifact_topics or artifact_count >= artifact_cap
                        ):
                            kind, content = "none", None
                        self.db.add(Question(
                            session_id=session.id, seq=seq, topic_id=topic_id,
                            type=q.type, stem=q.stem, artifact_kind=kind,
                            artifact_content=content,
                            options=[o.model_dump() for o in q.options],
                            correct_keys=q.correct_keys, explanation=q.explanation,
                            validation_status="passed",
                        ))
                        needed -= 1
                        # Keep the most recent stems as the model's avoid-list
                        # (cap to the last 40 so the prompt stays bounded).
                        recent_stems.append(q.stem)
                        if len(recent_stems) > 40:
                            recent_stems = recent_stems[-40:]
                        if kind != "none":
                            artifact_count += 1
                            artifact_topics_used.add(topic_id)
                        session.generated_count = seq
                        # Commit after EACH validated question so generated_count
                        # rises live — the frontend sees smooth progress and can
                        # start answering ready questions instead of a frozen
                        # counter.
                        await self.db.commit()
                if needed > 0:
                    # Could not fill this topic within the attempt budget.
                    session.status = "failed"
                    await self.db.commit()
                    return

            # Hard multi-quota: the soft prompt instruction underdelivers, so
            # after generating the closed pool, regenerate excess single
            # questions as multi until we reach the target share (or run out of
            # rounds — then accept what we have; never block readiness).
            if multi_ratio:
                await self._enforce_multi_quota(
                    session, multi_ratio, seen_stems, recent_stems)

            # Shuffle the question order so artifacts and topics are interspersed
            # rather than clustered at the start (they're generated topic-by-topic,
            # and the artifact quota lands on the earliest artifact-friendly
            # topics). Deterministic shuffle seeded by the session id, so the order
            # is reproducible and testable (no Math.random/Date).
            all_qs = (await self.db.execute(
                select(Question).where(Question.session_id == session.id)
                .order_by(Question.seq)
            )).scalars().all()
            rng = random.Random(str(session.id))
            order = list(range(1, len(all_qs) + 1))
            rng.shuffle(order)
            for q, new_seq in zip(all_qs, order):
                q.seq = new_seq
            await self.db.commit()

            # Append open (free-text) questions after the closed pool. base/
            # specialist get a fixed mix (1 session-seeded seed case + 1 themed «интеграция» +
            # 1 themed «системное мышление»); ba keeps the seed+LLM pool. A
            # failure in any single open question degrades softly (skip it) — open
            # questions are a bonus section and must not block readiness.
            try:
                rng = random.Random(str(session.id))
                themed = LEVEL_OPEN_THEMED.get(session.level)
                if themed is not None:
                    chosen = [rng.choice(SEED_OPEN_QUESTIONS)]
                    for topic_title, hint in themed:
                        try:
                            chosen.append(
                                await self.client.generate_open_on_topic(topic_title, hint))
                        except Exception:
                            logger.exception(
                                "Themed open question '%s' failed for session %s",
                                topic_title, session_id)
                else:
                    open_count = LEVEL_OPEN_COUNT.get(session.level, DEFAULT_OPEN_COUNT)
                    pool = list(SEED_OPEN_QUESTIONS)
                    try:
                        pool += await self.client.generate_open_questions(
                            session.level, count=LLM_OPEN_CANDIDATES)
                    except Exception:
                        logger.exception(
                            "LLM open-question generation failed for session %s "
                            "(falling back to seed pool)", session_id)
                    chosen = _sample_open_pool(pool, open_count, rng)
                for oq in chosen:
                    seq += 1
                    self.db.add(Question(
                        session_id=session.id, seq=seq, topic_id="open",
                        type="open", stem=oq.stem, artifact_kind="none",
                        artifact_content=None, options=[], correct_keys=[],
                        explanation=oq.explanation, rubric=oq.rubric,
                        validation_status="passed",
                    ))
                # Bump generated_count to include the open questions so the exam
                # UI's readiness check (seq <= generated_count) unlocks them.
                session.generated_count = seq
                await self.db.commit()
            except Exception:
                logger.exception("Open-question step failed for session %s", session_id)

            session.status = "ready"
            # NB: the generator no longer starts the timer. The timer starts
            # when the user first opens the exam screen (POST /sessions/{id}/start),
            # so the prep time spent waiting for the pool isn't billed against them.
            await self.db.commit()
        except Exception:
            logger.exception("Generation failed for session %s", session_id)
            session.status = "failed"
            await self.db.commit()

    async def _enforce_multi_quota(self, session, multi_ratio, seen_stems, recent_stems):
        """Regenerate excess single closed questions as multi until the multi
        share reaches `multi_ratio` (ceil of closed count) or MULTI_TOPUP_ROUNDS
        passes are exhausted. Replaces a single's content in place (same row,
        same seq, same topic) with a freshly generated multi question. Never
        raises — a failed regeneration just leaves that single as-is."""
        for _round in range(MULTI_TOPUP_ROUNDS):
            # Intentional per-round re-SELECT: re-reads the pool so this round
            # picks up the previous round's conversions (updated multi_count and
            # the shrunken set of remaining singles).
            closed = (await self.db.execute(
                select(Question).where(
                    Question.session_id == session.id,
                    Question.type.in_(("single", "multi")),
                ).order_by(Question.seq)
            )).scalars().all()
            total = len(closed)
            if total == 0:
                return
            target = math.ceil(multi_ratio * total)
            multi_count = sum(1 for q in closed if q.type == "multi")
            if multi_count >= target:
                return
            singles = [q for q in closed if q.type == "single"]
            converted_this_round = 0
            for q in singles:
                if multi_count >= target:
                    break
                try:
                    batch = await self._generate_with_retry(
                        session.level, session.mode, [(q.topic_id, 1)],
                        avoid_stems=recent_stems[-40:], want_artifact=False,
                        multi_ratio=1.0,
                    )
                except Exception:
                    logger.exception(
                        "Multi top-up generation failed for session %s", session.id)
                    continue
                new_q = next(
                    (g for g in batch.questions if g.type == "multi"
                     and len(g.correct_keys) >= 2), None)
                if new_q is None:
                    continue
                # Validate converted multis with the SAME gate the main loop
                # uses — converted multis can be the majority of the pool, so a
                # structural check alone is not enough; reject invalid ones.
                if not (await self.client.validate_question(new_q)).valid:
                    continue
                norm = new_q.stem.strip().lower()
                if norm in seen_stems:
                    continue
                # Convert the stored single into the new multi (keep seq/topic).
                seen_stems.discard(q.stem.strip().lower())
                seen_stems.add(norm)
                q.type = "multi"
                q.stem = new_q.stem
                q.artifact_kind = "none"
                q.artifact_content = None
                q.options = [o.model_dump() for o in new_q.options]
                q.correct_keys = new_q.correct_keys
                q.explanation = new_q.explanation
                multi_count += 1
                converted_this_round += 1
                # Keep recent_stems updated so subsequent converts in this/next
                # round avoid the just-added stem (cap to the last 40).
                recent_stems.append(new_q.stem)
                if len(recent_stems) > 40:
                    del recent_stems[: len(recent_stems) - 40]
            await self.db.commit()
            if converted_this_round == 0:
                return  # no progress this round — stop, accept what we have

    async def _generate_with_retry(
        self, level, mode, slice_, avoid_stems=None, want_artifact=False,
        multi_ratio=None, mermaid_only=False,
    ):
        delay = 0.0
        last = None
        for attempt in range(self.max_batch_retries):
            try:
                return await self.client.generate_batch(
                    level, mode, slice_,
                    avoid_stems=avoid_stems, want_artifact=want_artifact,
                    multi_ratio=multi_ratio, mermaid_only=mermaid_only,
                )
            except Exception as e:  # noqa: BLE001
                last = e
                if delay:
                    await asyncio.sleep(delay)
                delay = (delay or 0.1) * 2
        raise last
