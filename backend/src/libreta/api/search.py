from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.models import SearchResult
from libreta.storage.search import search as search_index

router = APIRouter()


@router.get("/search", response_model=list[SearchResult])
async def search_pages(
    settings: Annotated[Settings, Depends(get_settings)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SearchResult]:
    results = await search_index(settings.meta_dir, q, limit)
    out: list[SearchResult] = []
    for r in results:
        key: str = r["path"]
        # Keys are source_id:page_path — split them
        sid, _, page_path = key.partition(":")
        out.append(
            SearchResult(
                path=page_path,
                title=r["title"],
                snippet=r["snippet"],
                updated=r["updated"],
                tags=r["tags"],
                source_id=sid if sid else None,
            )
        )
    return out
