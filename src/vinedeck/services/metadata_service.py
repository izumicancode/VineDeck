"""Aggregates metadata providers. The UI depends on this, never on a provider."""

from __future__ import annotations

from ..core.metadata import LocalMetadataProvider, Metadata, MetadataProvider
from ..utils.logging import get_logger

log = get_logger("metadata")


class MetadataService:
    def __init__(self, providers: list[MetadataProvider] | None = None):
        self.providers = providers if providers is not None else [LocalMetadataProvider()]

    def lookup(self, executable_path: str) -> Metadata | None:
        for provider in self.providers:
            try:
                result = provider.lookup(executable_path)
            except Exception as exc:               # a provider must never break the UI
                log.warning("Metadata provider %s failed: %s", type(provider).__name__, exc)
                continue
            if result:
                return result
        return None
