"""Metadata provider architecture.

The UI only talks to :class:`MetadataProvider`. Only the local provider exists today;
an external provider (e.g. a game database) can be added later by subclassing
:class:`ExternalMetadataProvider` and registering it in
:class:`vinedeck.services.metadata_service.MetadataService`, without touching the UI.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Metadata:
    name: str = ""
    developer: str = ""
    publisher: str = ""
    version: str = ""
    genre: str = ""
    release_year: str = ""
    website: str = ""
    description: str = ""


class MetadataProvider(ABC):
    @abstractmethod
    def lookup(self, executable_path: str) -> Metadata | None: ...


class LocalMetadataProvider(MetadataProvider):
    """Derives a friendly name from the executable's file name. Works offline."""

    def lookup(self, executable_path: str) -> Metadata | None:
        stem = Path(executable_path).stem
        if not stem:
            return None
        name = re.sub(r"[_\-.]+", " ", stem)
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)       # CamelCase -> Camel Case
        name = re.sub(r"\s+", " ", name).strip()
        return Metadata(name=name or stem)


class ExternalMetadataProvider(MetadataProvider, ABC):
    """Base class for network-backed providers (none implemented yet)."""
