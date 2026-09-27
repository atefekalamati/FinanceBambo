# -*- coding: utf-8 -*-
"""The durable job queue (0040): a job is a row, a worker drains it, a restart loses nothing.

Built 2026-09-27 because the production composition refused async extraction outright
(503) rather than run it in a web-worker callback that a restart would take with it.
"""
import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.background_jobs import (DONE, FAILED, KIND_EXTRACTION, QUEUED, RUNNING,
                                                JobRefused, JobScope, JobSpec)
from app.finance.domain.errors import FinanceDomainError
from app.finance.services.background_jobs import (BackgroundWorker, DurableBackgroundExecutor,
                                                  default_handlers, extraction_handler,
                                                  extraction_job)
from app.finance.repositories.background_jobs import PsycopgBackgroundJobRepository

ORG = UUID("40000000-0000-4000-8000-000000000001")
ACTOR = UUID("40000000-0000-4000-8000-000000000002")
FILE_ID = UUID("40000000-0000-4000-8000-000000000003")
SCOPE = SimpleNamespace(organization_id=ORG, project_id="terrace", actor_user_id=ACTOR, locale="fa-IR")


class Queue:
    """The repository, as a list of dicts with the claim rule the SQL states."""

    def __init__(self):
        self.rows = []
        self.now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    async def enqueue(self, spec):
        row = {"id": uuid4(), "organization_id": spec.organization_id, "project_id": spec.project_id,
               "kind": spec.kind, "payload": dict(spec.payload), "status": QUEUED, "attempts": 0,
               "max_attempts": spec.max_attempts, "available_at": self.now, "lease_until": None,
               "started_at": None, "finished_at": None, "error": None,
               "created_by": spec.created_by, "created_at": self.now}
        self.rows.append(row)
        return dict(row)

    async def claim(self, worker, lease):
        due = [r for r in self.rows if (r["status"] == QUEUED and r["available_at"] <= self.now)
               or (r["status"] == RUNNING and r["lease_until"] is not None and r["lease_until"] < self.now)]
        if not due:
            return None
        row = sorted(due, key=lambda r: (r["available_at"], r["created_at"]))[0]
        row.update(status=RUNNING, attempts=row["attempts"] + 1, started_at=self.now,
                   lease_until=self.now + lease, error=None)
        return dict(row)

    async def finish(self, job_id, organization_id=None, *, error=None, retry=False):
        row = next(r for r in self.rows if r["id"] == job_id)
        if error is None:
            row.update(status=DONE, error=None, finished_at=self.now)
        elif retry:
            row.update(status=QUEUED, error=error, available_at=self.now + timedelta(seconds=30))
        else:
            row.update(status=FAILED, error=error, finished_at=self.now)
        row["lease_until"] = None
        return dict(row)

    async def latest_for_payload(self, scope, kind, key, value):
        rows = [r for r in self.rows if r["kind"] == kind and str(r["payload"].get(key)) == str(value)]
        return dict(rows[-1]) if rows else None


def go(coroutine):
    return asyncio.run(coroutine)


class SubmitTests(unittest.TestCase):
    def test_submit_writes_a_queued_row_and_returns_before_any_work(self):
        queue = Queue()
        spec = extraction_job(SCOPE, FILE_ID, {"locale": "fa-IR"})
        row = go(DurableBackgroundExecutor(queue).submit(spec))
        self.assertEqual(QUEUED, row["status"])
        self.assertEqual(KIND_EXTRACTION, row["kind"])
        self.assertEqual({"attachmentId": str(FILE_ID), "actorUserId": str(ACTOR), "locale": "fa-IR",
                          "hints": {"locale": "fa-IR"}}, row["payload"], "ids and options; no callable")
        self.assertEqual(ACTOR, row["created_by"])

    def test_the_spec_carries_only_data(self):
        spec = extraction_job(SCOPE, FILE_ID)
        self.assertIsInstance(spec, JobSpec)
        for value in spec.payload.values():
            self.assertNotIn("function", type(value).__name__)


class WorkerTests(unittest.TestCase):
    def worker(self, queue, handler):
        return BackgroundWorker(queue, {KIND_EXTRACTION: handler}, name="w1", poll_interval=0)

    def test_a_job_is_run_with_the_scope_rebuilt_from_its_row_and_marked_done(self):
        queue, seen = Queue(), []
        go(DurableBackgroundExecutor(queue).submit(extraction_job(SCOPE, FILE_ID, {"x": 1})))

        async def handler(scope, payload):
            seen.append((scope, payload))

        row = go(self.worker(queue, handler).run_once())
        self.assertEqual(DONE, row["status"])
        scope, payload = seen[0]
        self.assertIsInstance(scope, JobScope)
        self.assertEqual((ORG, "terrace", ACTOR, "fa-IR"),
                         (scope.organization_id, scope.project_id, scope.actor_user_id, scope.locale))
        self.assertEqual({"x": 1}, payload["hints"])

    def test_an_idle_queue_yields_nothing(self):
        self.assertIsNone(go(self.worker(Queue(), lambda s, p: None).run_once()))

    def test_a_transient_failure_is_retried_until_the_attempts_run_out(self):
        queue = Queue()
        go(DurableBackgroundExecutor(queue).submit(extraction_job(SCOPE, FILE_ID)))

        async def handler(scope, payload):
            raise RuntimeError("model would not load")

        worker = self.worker(queue, handler)
        first = go(worker.run_once())
        self.assertEqual((QUEUED, 1), (first["status"], first["attempts"]), "queued again, not failed")
        self.assertIn("RuntimeError", first["error"])
        self.assertGreater(first["available_at"], queue.now, "not immediately")
        queue.now += timedelta(minutes=1)
        second = go(worker.run_once())
        self.assertEqual((QUEUED, 2), (second["status"], second["attempts"]))
        queue.now += timedelta(minutes=1)
        third = go(worker.run_once())
        self.assertEqual((FAILED, 3), (third["status"], third["attempts"]), "the third try was the last")

    def test_a_refusal_fails_at_once_and_is_not_retried(self):
        queue = Queue()
        go(DurableBackgroundExecutor(queue).submit(extraction_job(SCOPE, FILE_ID)))

        async def handler(scope, payload):
            raise JobRefused("the uploader is gone")

        row = go(self.worker(queue, handler).run_once())
        self.assertEqual((FAILED, 1), (row["status"], row["attempts"]))
        self.assertEqual("the uploader is gone", row["error"])

    def test_a_job_whose_worker_died_is_taken_back_after_its_lease(self):
        """The property the queue exists for."""
        queue = Queue()
        go(DurableBackgroundExecutor(queue).submit(extraction_job(SCOPE, FILE_ID)))
        claimed = go(queue.claim("w-dead", timedelta(minutes=5)))
        self.assertEqual(RUNNING, claimed["status"])
        ran = []

        async def handler(scope, payload):
            ran.append(payload["attachmentId"])

        worker = self.worker(queue, handler)
        self.assertIsNone(go(worker.run_once()), "while the lease holds, nobody else may run it")
        queue.now += timedelta(minutes=6)
        row = go(worker.run_once())
        self.assertEqual(DONE, row["status"])
        self.assertEqual(2, row["attempts"], "the dead worker's attempt still counts")
        self.assertEqual([str(FILE_ID)], ran)

    def test_a_kind_nobody_handles_fails_rather_than_waiting_forever(self):
        queue = Queue()
        go(queue.enqueue(JobSpec(kind="mystery", organization_id=ORG, project_id="terrace")))
        row = go(self.worker(queue, lambda s, p: None).run_once())
        self.assertEqual(FAILED, row["status"])
        self.assertIn("mystery", row["error"])


class ExtractionHandlerTests(unittest.TestCase):
    """The one handler: `start` on the file, claimed, forcing a new draft."""

    class Service:
        def __init__(self, error=None):
            self.error, self.calls = error, []

        async def start(self, scope, attachment_id, hints, force_new=False, claimed=False):
            self.calls.append((scope, attachment_id, hints, force_new, claimed))
            if self.error is not None:
                raise self.error
            return SimpleNamespace(draft_id=uuid4())

    def test_it_calls_start_as_the_route_would_have(self):
        service = self.Service()
        go(extraction_handler(service)(JobScope(ORG, "terrace", ACTOR),
                                       {"attachmentId": str(FILE_ID), "hints": {"locale": "fa-IR"}}))
        scope, attachment_id, hints, force_new, claimed = service.calls[0]
        self.assertEqual((FILE_ID, {"locale": "fa-IR"}, True, True), (attachment_id, hints, force_new, claimed))
        self.assertEqual(ACTOR, scope.actor_user_id, "the uploader check in `start` sees the uploader")

    def test_a_domain_failure_is_a_refusal_because_start_already_moved_the_file_to_failed(self):
        class Provider(FinanceDomainError):
            pass
        with self.assertRaises(JobRefused) as caught:
            go(extraction_handler(self.Service(error=Provider("ocr down")))(
                JobScope(ORG, "terrace", ACTOR), {"attachmentId": str(FILE_ID)}))
        self.assertIn("ocr down", str(caught.exception))

    def test_anything_else_propagates_and_is_the_workers_retry(self):
        with self.assertRaises(ConnectionError):
            go(extraction_handler(self.Service(error=ConnectionError("db away")))(
                JobScope(ORG, "terrace", ACTOR), {"attachmentId": str(FILE_ID)}))

    def test_the_default_handlers_cover_the_one_kind_there_is(self):
        self.assertEqual({KIND_EXTRACTION}, set(default_handlers(self.Service())))


class TheClaimStatementTests(unittest.TestCase):
    """What the SQL says, asserted on the SQL."""

    def test_two_workers_cannot_take_one_job_and_a_dead_workers_job_is_retaken(self):
        import inspect
        source = inspect.getsource(PsycopgBackgroundJobRepository.claim)
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("lease_until < now()", source, "an expired lease is fair game")
        self.assertIn("attempts = attempts + 1", source, "counted at the claim, so a crash counts")
        self.assertIn("LIMIT 1", source)


if __name__ == "__main__":
    unittest.main()
