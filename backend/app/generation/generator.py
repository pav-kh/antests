import asyncio
import datetime as dt
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Question, TestSession

logger = logging.getLogger(__name__)


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
                    batch = await self._generate_with_retry(
                        session.level, session.mode, [(topic_id, take)]
                    )
                    for q in batch.questions:
                        if needed <= 0:
                            break
                        verdict = await self.client.validate_question(q)
                        if not verdict.valid:
                            continue
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
            session.timer_started_at = dt.datetime.now(dt.timezone.utc)
            await self.db.commit()
        except Exception:
            logger.exception("Generation failed for session %s", session_id)
            session.status = "failed"
            await self.db.commit()

    async def _generate_with_retry(self, level, mode, slice_):
        delay = 0.0
        last = None
        for attempt in range(self.max_batch_retries):
            try:
                return await self.client.generate_batch(level, mode, slice_)
            except Exception as e:  # noqa: BLE001
                last = e
                if delay:
                    await asyncio.sleep(delay)
                delay = (delay or 0.1) * 2
        raise last
