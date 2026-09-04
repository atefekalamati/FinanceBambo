import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from ..domain.errors import FinanceDomainError
from ..domain.extractions import ExtractionDraft, ExtractionField
from ..domain.resources import FinanceRecordNotFound
from ..schemas.extractions import ProviderExtractionResult
from .attachments import storage_name


#: Background work has no response to fail into, so the log is the only trace.
LOG = logging.getLogger("finance.extraction")


class AIExtractionFailed(FinanceDomainError):
    status = 503
    code = "AI_EXTRACTION_FAILED"


class AIExtractionContentError(FinanceDomainError):
    status = 422
    code = "AI_EXTRACTION_FAILED"


class ExtractionForbidden(FinanceDomainError):
    status = 403
    code = "FINANCE_FORBIDDEN"


class ExtractionConflict(FinanceDomainError):
    status = 409
    code = "STALE_VERSION"


class FinanceExtractionService:
    def __init__(self, extraction_repository, attachment_repository, storage,
                 image_extractor, voice_extractor, invoice_service=None, id_factory=uuid4,
                 clock=lambda: datetime.now(timezone.utc)):
        self.repo, self.attachments, self.storage = extraction_repository, attachment_repository, storage
        self.image_extractor, self.voice_extractor = image_extractor, voice_extractor
        self.invoices = invoice_service
        self.ids, self.clock = id_factory, clock

    async def get(self, scope, draft_id):
        value = await self.repo.get(scope, draft_id)
        if value is None: raise FinanceRecordNotFound("extraction draft not found")
        return value

    async def list(self, scope, page=1, page_size=50, review_status=None,
                   source=None, file_id=None, linked_invoice_id=None):
        return await self.repo.list(scope,page,page_size,review_status,source,file_id,linked_invoice_id)

    async def start(self, scope, attachment_id, hints=None, force_new=False, claimed=False):
        """Run one extraction to completion. Synchronous: the caller waits.

        `claimed` says the caller has ALREADY moved this attachment to `processing` and is
        handing the work over -- which is what `schedule` does before it queues the
        background task. Without it the background run would read its own caller's
        `processing` and refuse with "file is already processing", so the claim that stops
        a duplicate request would also stop the real one.
        """
        attachment = await self.attachments.get(scope, attachment_id)
        if attachment is None: raise FinanceRecordNotFound("file not found")
        if scope.actor_user_id != attachment.uploaded_by: raise ExtractionForbidden("only the uploader can process this file")
        if not force_new:
            existing = await self.repo.latest_for_file(scope, attachment_id)
            if existing is not None: return existing
        if not claimed and attachment.processing_status not in {"uploaded", "failed", "ready"}:
            raise AIExtractionFailed("file is already processing")
        # `claimed` work is already in `processing`, so there is nothing to move it to, but
        # it still has to be moved OUT of it when the run ends.
        changes_file_status = claimed or attachment.processing_status != "ready"
        if changes_file_status and not claimed:
            attachment = await self.attachments.transition(scope, attachment, "processing")
        extractor = self.image_extractor if attachment.logical_type == "invoice_image" else self.voice_extractor
        try:
            # `storage_name`, not `file_id`: the file was PUT under `{file_id}.{extension}`.
            # Asking by the bare id raised FileNotFoundError, which the broad `except` below
            # turned into "extraction provider is unavailable" -- so this line, not the
            # provider, was why no extraction ever succeeded.
            stored_file = await self.storage.get(str(scope.organization_id), scope.project_id,
                                                 storage_name(attachment))
            raw = await extractor.extract(stored_file, hints or {})
            parsed = ProviderExtractionResult.model_validate(raw)
        except ValueError as error:
            if changes_file_status: await self.attachments.transition(scope, attachment, "failed")
            raise AIExtractionContentError("provider output does not match the extraction contract") from error
        except Exception as error:
            if changes_file_status: await self.attachments.transition(scope, attachment, "failed")
            raise AIExtractionFailed("extraction provider is unavailable") from error
        if changes_file_status: attachment = await self.attachments.transition(scope, attachment, "ready")
        fields = [ExtractionField(**field.model_dump()) for field in parsed.fields]
        draft = ExtractionDraft(self.ids(), scope.organization_id, scope.project_id, attachment, 0,
            "awaitingReview", "draft", extractor.adapter_name, fields, scope.actor_user_id, self.clock(), Decimal(0))
        return await self.repo.create_next(scope, draft)

    async def schedule(self, scope, attachment_id, background, hints=None, force_new=False):
        """Start an extraction without holding the request open.

        A local OCR or transcription takes seconds to minutes. Running it inline would keep
        an HTTP connection open for the whole of it and, with a synchronous model call, block
        the worker as well -- so an upload would appear to hang and a second upload would
        queue behind it.

        The status the caller polls is the attachment's, not a new one. `finance_attachments`
        already carries `uploaded -> processing -> ready | failed`, and `start` already moves
        it through them; adding a second status column would give the same fact two homes and
        eventually two answers. The draft appears when the work finishes, and
        `GET /extractions?fileId=` is how the client notices.

        Returns the attachment AFTER it has been moved to `processing`, so the 202 reports
        the status the row actually holds rather than a promise about it.
        """
        attachment = await self.attachments.get(scope, attachment_id)
        if attachment is None: raise FinanceRecordNotFound("file not found")
        if scope.actor_user_id != attachment.uploaded_by:
            raise ExtractionForbidden("only the uploader can process this file")
        if attachment.processing_status not in {"uploaded", "failed", "ready"}:
            raise AIExtractionFailed("file is already processing")
        if not force_new:
            existing = await self.repo.latest_for_file(scope, attachment_id)
            if existing is not None:
                return attachment, existing

        # Claimed BEFORE the task is queued, not inside it. Two requests arriving together
        # both read `uploaded`, both passed the guard above and both queued a run -- two
        # extractions and two drafts for one file. Moving the attachment to `processing`
        # here means the second request reads `processing` and is refused, and it also makes
        # the 202 truthful: the status returned is the status the row now holds.
        attachment = await self.attachments.transition(scope, attachment, "processing")

        async def run():
            # Every failure mode is already handled inside `start`, which moves the
            # attachment to `failed` and leaves it retryable. Nothing is re-raised here:
            # there is no request left to answer, and an unhandled exception in a background
            # task would be a log line nobody reads instead of a status the user can see.
            #
            # Logged either way. A background failure has no response to appear in, so
            # without this line the only trace of it is a status change, and nobody can tell
            # a provider outage from a corrupt file.
            try:
                draft = await self.start(scope, attachment_id, hints, force_new=True,
                                         claimed=True)
                LOG.info("extraction finished file=%s draft=%s", attachment_id,
                         getattr(draft, "id", None))
            except FinanceDomainError as error:
                LOG.warning("extraction failed file=%s %s: %s", attachment_id,
                            type(error).__name__, error)

        background(run)
        return attachment, None

    async def retry(self, scope, draft_id, hints=None):
        current = await self.get(scope, draft_id)
        if current.submitted_by != scope.actor_user_id: raise ExtractionForbidden("only the uploader can retry this extraction")
        return await self.start(scope, current.file.file_id, hints, force_new=True)

    async def reject(self, scope, draft_id, command):
        current = await self.get(scope, draft_id)
        if current.submitted_by != scope.actor_user_id: raise ExtractionForbidden("only the uploader can reject this extraction")
        if current.review_status != "awaitingReview" or current.version != command.expected_version:
            raise ExtractionConflict("extraction version is stale or not awaiting review")
        try:
            return await self.repo.reject(scope,current,command.reason,self.ids(),self.clock())
        except ValueError as error:
            raise ExtractionConflict("competing extraction mutation") from error

    async def confirm(self, scope, draft_id, command):
        if self.invoices is None: raise RuntimeError("invoice service is required for extraction confirmation")
        current = await self.get(scope, draft_id)
        if current.submitted_by != scope.actor_user_id: raise ExtractionForbidden("only the uploader can confirm this extraction")
        if current.review_status == "accepted" and current.file.invoice_id is not None:
            previous = await self.invoices.get(scope, current.file.invoice_id)
            if previous.idempotency_key == command.idempotency_key: return previous
            raise ExtractionConflict("extraction is already confirmed")
        if current.review_status != "awaitingReview" or current.version != command.expected_version:
            raise ExtractionConflict("extraction version is stale or not awaiting review")
        if await self.invoices.get_by_idempotency(scope, command.idempotency_key) is not None:
            raise ExtractionConflict("idempotency key belongs to another invoice")
        edits = {item.key: item.confirmed_value for item in command.field_confirmations}
        known = {field.key for field in current.fields}
        unknown = set(edits) - known
        if unknown: raise AIExtractionContentError(f"unknown extracted fields: {sorted(unknown)}")
        confirmed_fields = [ExtractionField(field.key, field.extracted_value,
            edits.get(field.key, field.extracted_value), field.confidence,
            field.key in edits and edits[field.key] != field.extracted_value) for field in current.fields]
        at = self.clock()
        source = "image" if current.file.logical_type == "invoice_image" else "voice"
        invoice = await self.invoices.prepare_extracted(scope, command.invoice, source, command.idempotency_key, at)
        try:
            return await self.repo.confirm_with_invoice(scope, current, confirmed_fields, invoice, command.invoice.duplicate_reason, self.ids(), self.ids(), at)
        except ValueError as error:
            repeated = await self.invoices.get_by_idempotency(scope, command.idempotency_key)
            linked_id = await self.repo.get_linked_invoice_id(scope, current.file.file_id)
            if repeated is not None and repeated.id == linked_id: return repeated
            raise ExtractionConflict("competing extraction confirmation") from error
