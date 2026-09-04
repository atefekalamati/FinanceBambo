# -*- coding: utf-8 -*-
"""The asynchronous extraction path: 202 now, work later.

No database and no model. The repository, storage and extractors are doubles, and the
"background" is a list the test drains by hand -- so the moment the response is produced and
the moment the work runs are separately observable, which is the whole point of the change.

The rule these tests protect: **one file, one extraction.** A second request while work is
in flight must be refused rather than queue a second run, because two runs mean two drafts
for one document and a reviewer with no way to tell which is current.
"""

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.security.guards import FinanceScope
from app.finance.services.extractions import (AIExtractionFailed, ExtractionForbidden,
                                              FinanceExtractionService)

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
SCOPE = FinanceScope(organization_id=ORG, project_id="p1", actor_user_id=ACTOR)

GOOD = {"fields": [{"key": "rawText", "extractedValue": "جمع کل ۱۳۵٬۰۰۰٬۰۰۰",
                    "confidence": 0.97, "editedByUser": False}]}


class Attachment:
    def __init__(self, status="uploaded"):
        self.file_id = FILE_ID
        self.organization_id, self.project_id = ORG, "p1"
        self.logical_type = "invoice_image"
        self.stored_name = "%s.png" % FILE_ID
        self.storage_key = "%s.png" % FILE_ID
        self.uploaded_by = ACTOR
        self.processing_status = status


class Attachments:
    """Stands in for the attachment repository AND records every status move."""

    def __init__(self, status="uploaded"):
        self.value = Attachment(status)
        self.transitions = []

    async def get(self, _scope, _file_id):
        return self.value

    async def transition(self, _scope, value, target):
        self.transitions.append((value.processing_status, target))
        self.value.processing_status = target
        return self.value


class Drafts:
    def __init__(self, existing=None):
        self.existing, self.created = existing, []

    async def latest_for_file(self, _scope, _file_id):
        return self.existing

    async def create_next(self, _scope, draft):
        self.created.append(draft)
        return draft


class Storage:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    async def get(self, organization_id, project_id, key):
        self.calls.append((organization_id, project_id, key))
        if self.error is not None:
            raise self.error
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class Extractor:
    adapter_name = "image-adapter"

    def __init__(self, result=GOOD, error=None):
        self.result, self.error, self.calls = result, error, 0

    async def extract(self, _file, _hints):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class Background:
    """Collects the queued callables instead of running them, so the test decides when."""

    def __init__(self):
        self.tasks = []

    def add(self, run):
        self.tasks.append(run)

    async def drain(self):
        while self.tasks:
            await self.tasks.pop(0)()


def service(attachments=None, drafts=None, storage=None, extractor=None):
    return FinanceExtractionService(
        drafts or Drafts(), attachments or Attachments(), storage or Storage(),
        extractor or Extractor(), Extractor(), invoice_service=None,
        id_factory=uuid4, clock=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc))


def run(coroutine):
    return asyncio.run(coroutine)


class AcceptanceTests(unittest.TestCase):
    def test_the_request_returns_before_any_work_happens(self):
        """202 is only honest if the extractor has NOT been called yet."""
        attachments, background, extractor = Attachments(), Background(), Extractor()
        svc = service(attachments=attachments, extractor=extractor)

        attachment, existing = run(svc.schedule(SCOPE, FILE_ID, background.add))

        self.assertIsNone(existing)
        self.assertEqual(0, extractor.calls, "work must not run inside the request")
        self.assertEqual(1, len(background.tasks), "exactly one run was queued")

    def test_the_answer_says_processing_because_the_row_says_processing(self):
        """The status returned is read back from the row, not asserted about the future.

        Before this, `schedule` returned the attachment untouched -- so a 202 reported
        `uploaded` while claiming work had begun, and the next poll could still say
        `uploaded` with nothing to distinguish "queued" from "never started".
        """
        attachments, background = Attachments(), Background()
        attachment, _ = run(service(attachments=attachments).schedule(
            SCOPE, FILE_ID, background.add))
        self.assertEqual("processing", attachment.processing_status)
        self.assertEqual("processing", attachments.value.processing_status)
        self.assertEqual([("uploaded", "processing")], attachments.transitions)


class LifecycleTests(unittest.TestCase):
    def test_success_moves_the_file_to_ready_and_creates_one_draft(self):
        attachments, drafts, background = Attachments(), Drafts(), Background()
        svc = service(attachments=attachments, drafts=drafts)

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()

        run(main())
        self.assertEqual([("uploaded", "processing"), ("processing", "ready")],
                         attachments.transitions)
        self.assertEqual("ready", attachments.value.processing_status)
        self.assertEqual(1, len(drafts.created))
        self.assertEqual("awaitingReview", drafts.created[0].review_status)

    def test_a_provider_failure_moves_the_file_to_failed_and_creates_no_draft(self):
        attachments, drafts, background = Attachments(), Drafts(), Background()
        svc = service(attachments=attachments, drafts=drafts,
                      extractor=Extractor(error=RuntimeError("model down")))

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()

        run(main())
        self.assertEqual([("uploaded", "processing"), ("processing", "failed")],
                         attachments.transitions)
        self.assertEqual([], drafts.created, "a failed run must not leave a draft")

    def test_a_missing_file_also_ends_as_failed(self):
        """The storage read is inside the same guard as the provider call."""
        attachments, background = Attachments(), Background()
        svc = service(attachments=attachments,
                      storage=Storage(error=FileNotFoundError("not stored")))

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()

        run(main())
        self.assertEqual("failed", attachments.value.processing_status)

    def test_the_background_run_never_raises(self):
        """There is no request left to answer, so an exception would only be lost.

        The status carries the outcome instead, which is what the client polls.
        """
        background = Background()
        svc = service(extractor=Extractor(error=RuntimeError("boom")))

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()          # must not raise

        run(main())

    def test_the_storage_is_read_by_the_key_the_file_was_written_under(self):
        storage, background = Storage(), Background()
        svc = service(storage=storage)

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()

        run(main())
        self.assertEqual((str(ORG), "p1", "%s.png" % FILE_ID), storage.calls[0])


class DuplicateTests(unittest.TestCase):
    def test_a_second_request_while_processing_is_refused(self):
        """The claim happens in the request, so the second one sees it.

        Both requests used to read `uploaded`, both passed the guard and both queued a run:
        two extractions and two drafts for one file.
        """
        attachments, background, extractor = Attachments(), Background(), Extractor()
        svc = service(attachments=attachments, extractor=extractor)

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add)
            with self.assertRaises(AIExtractionFailed):
                await svc.schedule(SCOPE, FILE_ID, background.add)
            await background.drain()

        run(main())
        self.assertEqual(1, len(background.tasks) + extractor.calls,
                         "exactly one run, not two")
        self.assertEqual(1, extractor.calls)

    def test_an_existing_draft_is_returned_instead_of_extracting_again(self):
        existing = object()
        background, extractor = Background(), Extractor()
        svc = service(drafts=Drafts(existing=existing), extractor=extractor)

        attachment, returned = run(svc.schedule(SCOPE, FILE_ID, background.add))

        self.assertIs(existing, returned)
        self.assertEqual([], background.tasks, "nothing queued when a draft already exists")
        self.assertEqual(0, extractor.calls)
        self.assertEqual("uploaded", attachment.processing_status,
                         "an untouched file must not be moved to processing")

    def test_force_new_extracts_again_even_with_a_draft_present(self):
        background, extractor = Background(), Extractor()
        svc = service(drafts=Drafts(existing=object()), extractor=extractor)

        async def main():
            await svc.schedule(SCOPE, FILE_ID, background.add, force_new=True)
            await background.drain()

        run(main())
        self.assertEqual(1, extractor.calls)

    def test_a_ready_file_can_be_extracted_again(self):
        """`ready` means a previous run finished, not that the file is closed."""
        attachments, background = Attachments(status="ready"), Background()
        run(service(attachments=attachments).schedule(SCOPE, FILE_ID, background.add))
        self.assertEqual("processing", attachments.value.processing_status)

    def test_a_failed_file_can_be_retried(self):
        attachments, background = Attachments(status="failed"), Background()
        run(service(attachments=attachments).schedule(SCOPE, FILE_ID, background.add))
        self.assertEqual("processing", attachments.value.processing_status)


class AuthorityTests(unittest.TestCase):
    def test_only_the_uploader_may_schedule(self):
        background = Background()
        other = FinanceScope(organization_id=ORG, project_id="p1", actor_user_id=OTHER)
        with self.assertRaises(ExtractionForbidden):
            run(service().schedule(other, FILE_ID, background.add))
        self.assertEqual([], background.tasks, "a refused request queues nothing")


if __name__ == "__main__":
    unittest.main()
