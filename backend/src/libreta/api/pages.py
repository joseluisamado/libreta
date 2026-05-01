from typing import Annotated

from fastapi import APIRouter, Depends

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.models import PageNode, PageRead
from libreta.storage.pages import read_page, walk_tree

router = APIRouter(prefix="/pages")


@router.get("/tree", response_model=list[PageNode])
async def get_tree(settings: Annotated[Settings, Depends(get_settings)]) -> list[PageNode]:
    return await walk_tree(settings.content_dir)


@router.get("/{path:path}", response_model=PageRead)
async def get_page(
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    return await read_page(settings.content_dir, path)
