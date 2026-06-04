import asyncio
import logging
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Question, TestSession

logger = logging.getLogger(__name__)

# Topics that naturally carry an embedded artifact (code/SQL/JSON/XML/diagram).
# Used to steer the artifact quota toward questions where an artifact is
# pedagogically appropriate instead of bolted on.
ARTIFACT_TOPICS = {
    "data", "integration", "modeling", "architecture", "fundamentals", "security",
}


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
            # Aim a bit above the 10% floor so the quota comfortably clears it
            # even after a few artifact questions get rejected by validation.
            total_questions = sum(c for _, c in plan)
            artifact_target = max(1, math.ceil(0.15 * total_questions))
            artifact_count = 0
            # Process one topic at a time. Routing questions by the model's
            # returned topic_id is unreliable — the model echoes the topic TITLE
            # (or a paraphrase), not the canonical key — so we generate per topic
            # and stamp the known key ourselves. This prevents an infinite loop
            # where every question is discarded for a "mismatched" topic_id.
            for topic_id, count in plan:
                needed = count
                attempts = 0
                max_attempts = (count + 1) * (self.max_slot_retries + 1)
                # Track stems generated for THIS topic so we can both ask the
                # model to diversify (avoid_stems) and hard-skip exact repeats
                # (seen_stems), preventing near-duplicate questions early in a
                # test run.
                topic_stems = []
                seen_stems = set()
                while needed > 0 and attempts < max_attempts:
                    attempts += 1
                    take = min(needed, self.batch_size)
                    # Only request artifacts on artifact-friendly topics, and
                    # only while we still owe the session its quota.
                    want_artifact = (
                        topic_id in ARTIFACT_TOPICS
                        and artifact_count < artifact_target
                    )
                    batch = await self._generate_with_retry(
                        session.level, session.mode, [(topic_id, take)],
                        avoid_stems=topic_stems, want_artifact=want_artifact,
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
                        self.db.add(Question(
                            session_id=session.id, seq=seq, topic_id=topic_id,
                            type=q.type, stem=q.stem, artifact_kind=q.artifact_kind,
                            artifact_content=q.artifact_content,
                            options=[o.model_dump() for o in q.options],
                            correct_keys=q.correct_keys, explanation=q.explanation,
                            validation_status="passed",
                        ))
                        needed -= 1
                        topic_stems.append(q.stem)
                        if q.artifact_kind != "none":
                            artifact_count += 1
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

            session.status = "ready"
            # NB: the generator no longer starts the timer. The timer starts
            # when the user first opens the exam screen (POST /sessions/{id}/start),
            # so the prep time spent waiting for the pool isn't billed against them.
            await self.db.commit()
        except Exception:
            logger.exception("Generation failed for session %s", session_id)
            session.status = "failed"
            await self.db.commit()

    async def _generate_with_retry(
        self, level, mode, slice_, avoid_stems=None, want_artifact=False
    ):
        delay = 0.0
        last = None
        for attempt in range(self.max_batch_retries):
            try:
                return await self.client.generate_batch(
                    level, mode, slice_,
                    avoid_stems=avoid_stems, want_artifact=want_artifact,
                )
            except Exception as e:  # noqa: BLE001
                last = e
                if delay:
                    await asyncio.sleep(delay)
                delay = (delay or 0.1) * 2
        raise last
