import asyncio
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Question, TestSession


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
            remaining = {tid: count for tid, count in plan}
            slot_attempts = 0
            while sum(remaining.values()) > 0:
                slice_ = self._next_slice(remaining)
                batch = await self._generate_with_retry(
                    session.level, session.mode, slice_
                )
                for q in batch.questions:
                    if remaining.get(q.topic_id, 0) <= 0:
                        continue
                    verdict = await self.client.validate_question(q)
                    if not verdict.valid:
                        continue
                    seq += 1
                    self.db.add(Question(
                        session_id=session.id, seq=seq, topic_id=q.topic_id,
                        type=q.type, stem=q.stem, artifact_kind=q.artifact_kind,
                        artifact_content=q.artifact_content,
                        options=[o.model_dump() for o in q.options],
                        correct_keys=q.correct_keys, explanation=q.explanation,
                        validation_status="passed",
                    ))
                    remaining[q.topic_id] -= 1
                    session.generated_count = seq
                await self.db.commit()
                slot_attempts += 1
                if slot_attempts > (session.total_questions + 1) * (self.max_slot_retries + 1):
                    break

            if sum(remaining.values()) > 0:
                session.status = "failed"
                await self.db.commit()
                return

            session.status = "ready"
            session.timer_started_at = dt.datetime.now(dt.timezone.utc)
            await self.db.commit()
        except Exception:
            session.status = "failed"
            await self.db.commit()

    def _next_slice(self, remaining):
        slice_ = []
        budget = self.batch_size
        for tid, need in remaining.items():
            if need <= 0:
                continue
            take = min(need, budget)
            if take <= 0:
                break
            slice_.append((tid, take))
            budget -= take
            if budget <= 0:
                break
        return slice_

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
