from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Union
from urllib.parse import urlparse

from config import Settings
from services.media_store import MediaStore

if TYPE_CHECKING:
    from services.mongo_media_store import MongoMediaStore

logger = logging.getLogger(__name__)

MediaStoreBackend = Union[MediaStore, "MongoMediaStore"]


def _db_name_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    name = (parsed.path or "").strip("/").split("/")[0]
    return name or "logistics"


def create_media_store(settings: Settings) -> MediaStoreBackend:
    uri = (settings.mongodb_uri or "").strip()
    if uri:
        from services.mongo_media_store import MongoMediaStore

        db_name = (settings.mongodb_db or "").strip() or _db_name_from_uri(uri)
        store = MongoMediaStore(uri, db_name)
        if store.ping():
            logger.info("Media store: MongoDB database=%s", db_name)
            return store
        raise RuntimeError("MongoDB is configured but unreachable")

    media_root = Path(settings.database_path).resolve().parent / "media"
    logger.info("Media store: local files (%s)", media_root)
    return MediaStore(media_root)
