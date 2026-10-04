"""Wires the long-lived services together; passed to the UI instead of globals."""

from __future__ import annotations

from dataclasses import dataclass

from .core.process_manager import ProcessManager
from .core.wine_manager import WineManager
from .database.database import Database
from .services.image_service import ImageService
from .services.metadata_service import MetadataService
from .ui.artwork import Artwork
from .ui.theme import ThemeManager
from .utils.config import Settings
from .utils.paths import AppPaths


@dataclass
class AppContext:
    paths: AppPaths
    settings: Settings
    db: Database
    images: ImageService
    artwork: Artwork
    wine: WineManager
    processes: ProcessManager
    metadata: MetadataService
    theme: ThemeManager

    @classmethod
    def create(cls, paths: AppPaths) -> "AppContext":
        paths.ensure()
        settings = Settings(paths.config_file)
        images = ImageService(paths)
        return cls(
            paths=paths, settings=settings, db=Database(paths.db_path), images=images,
            artwork=Artwork(images), wine=WineManager(settings["wine_binary"], settings["runner"]),
            processes=ProcessManager(paths.logs_dir), metadata=MetadataService(),
            theme=ThemeManager(settings, paths.theme_cache_dir))

    def close(self) -> None:
        self.settings.save()
        self.db.close()
