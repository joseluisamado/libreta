from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Git sources
# ---------------------------------------------------------------------------


class GitSourceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=128)
    remote_url: str = Field(min_length=1)
    branch: str = Field(default="main", min_length=1, max_length=128)
    ssh_key_id: str | None = None
    http_username: str | None = None
    http_password: str | None = None
    sync_interval_minutes: int = Field(default=5, ge=1, le=1440)


class GitSourceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    branch: str | None = Field(default=None, min_length=1, max_length=128)
    ssh_key_id: str | None = None
    http_username: str | None = None
    http_password: str | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)


class GitSourceResponse(BaseModel):
    id: str
    label: str
    remote_url: str
    branch: str
    ssh_key_id: str | None
    http_username: str | None
    sync_interval_minutes: int
    local_path: str
    cloned: bool
    last_synced_at: datetime | None
    last_sync_error: str | None


class SshKeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    private_key: str = Field(min_length=1)


class SshKeyResponse(BaseModel):
    id: str
    label: str
    fingerprint: str


class PageMeta(BaseModel):
    title: str
    created: datetime | None = None
    updated: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class PageWrite(BaseModel):
    body: str


class PageRead(BaseModel):
    path: str
    meta: PageMeta
    body: str


class PageMove(BaseModel):
    new_path: str


class PageNode(BaseModel):
    path: str
    title: str
    is_directory: bool
    children: list[PageNode] = Field(default_factory=list)


class HistoryEntry(BaseModel):
    sha: str  # first 7 chars
    message: str  # first line
    author: str
    timestamp: datetime


class RecentChange(BaseModel):
    sha: str  # first 7 chars
    message: str  # first line
    author: str
    timestamp: datetime
    path: str  # page path relative to pages/ dir


class DiffEntry(BaseModel):
    old_sha: str
    new_sha: str
    old_path: str | None
    new_path: str | None
    patch: str  # unified diff text; empty when contents are identical


class AssetUploadResponse(BaseModel):
    # Filename relative to the page's directory; the editor embeds it as `![](filename)`.
    filename: str
    size: int
    sha256: str
    kind: str  # "image" | "file"
    deduped: bool = False


class SearchResult(BaseModel):
    path: str
    title: str
    snippet: str
    updated: str
    tags: str


class HealthResponse(BaseModel):
    status: str


class InfoResponse(BaseModel):
    name: str
    version: str
    content_dir: str
    content_dir_exists: bool


class WatchedFolderResponse(BaseModel):
    label: str
    path: str
    exists: bool


class WatchedFolderCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    path: str = Field(min_length=1)


PageNode.model_rebuild()
