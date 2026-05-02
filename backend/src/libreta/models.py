from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PageMeta(BaseModel):
    title: str
    created: datetime | None = None
    updated: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class PageWrite(BaseModel):
    body: str
    is_index: bool = False


class PageRead(BaseModel):
    path: str
    meta: PageMeta
    body: str
    # True when the page is stored as ``<path>/index.md``. Lets the client
    # resolve relative asset references against the right base directory.
    is_index: bool = False


class PageMove(BaseModel):
    new_path: str


class PageNode(BaseModel):
    path: str
    title: str
    is_directory: bool
    children: list[PageNode] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class InfoResponse(BaseModel):
    name: str
    version: str
    content_dir: str
    content_dir_exists: bool


PageNode.model_rebuild()
