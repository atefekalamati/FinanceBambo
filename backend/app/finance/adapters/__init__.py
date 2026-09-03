"""Host integration ports; concrete adapters belong to BAMBO core."""

from .ports import AuthContextProvider, FileStorage, InvoiceImageExtractor, InvoiceVoiceExtractor, ProgressSnapshotProvider

__all__ = ["AuthContextProvider", "FileStorage", "InvoiceImageExtractor", "InvoiceVoiceExtractor", "ProgressSnapshotProvider"]
