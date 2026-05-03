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
    results = await search_index(settings.content_dir, q, limit)
    return [SearchResult(**r) for r in results]
