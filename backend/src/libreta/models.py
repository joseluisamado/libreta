from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PageMeta(BaseModel):
    title: str
    created: datetime | None = None
    updated: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class PageRead(BaseModel):
    path: str
    meta: PageMeta
    body: str


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
