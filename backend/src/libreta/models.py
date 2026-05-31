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
    # When set, the source clones/fetches/pushes over HTTPS using the token
    # stored for this Gitea server. Resolved at git-op time so rotating the
    # token in one place updates every source imported from that server.
    gitea_server_id: str | None = None
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
    gitea_server_id: str | None = None
    sync_interval_minutes: int
    local_path: str
    cloned: bool
    last_synced_at: datetime | None
    last_sync_error: str | None
    # Number of local commits ahead of origin/<branch>. Populated by the
    # backend on every list/get; the SPA flips the source's status dot to
    # amber when this is > 0.
    pending_count: int = 0


class PendingCommit(BaseModel):
    sha: str
    message: str
    author: str
    timestamp: datetime
    # `.md` page paths (no `.md` suffix) touched by the commit. Empty when
    # the commit only changed non-page files (assets, .gitkeep, etc.).
    paths: list[str]


class SshKeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    private_key: str = Field(min_length=1)


class SshKeyResponse(BaseModel):
    id: str
    label: str
    fingerprint: str


# ---------------------------------------------------------------------------
# Gitea servers (remembered credential groups)
# ---------------------------------------------------------------------------


class GiteaServerCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    # Base URL of the Gitea instance, e.g. https://git.example.com (no
    # trailing /api). The username is the account the token belongs to; it is
    # reused as the HTTPS basic-auth username when cloning.
    base_url: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=128)
    token: str = Field(min_length=1)


class GiteaServerResponse(BaseModel):
    # The token is never returned — it stays in a 0600 file on the backend,
    # exactly like SSH private keys.
    id: str
    label: str
    base_url: str
    username: str


class GiteaRepo(BaseModel):
    name: str
    full_name: str
    clone_url: str
    description: str = ""
    empty: bool = False
    # True when a source already points at this clone_url, so the UI can
    # disable the row instead of creating a duplicate.
    already_added: bool = False


class GiteaDiscoverRequest(BaseModel):
    # The org or user whose repos to list. The server (and its token) is
    # identified by the path param, so no credential travels in this body.
    owner: str = Field(min_length=1, max_length=128)


class GiteaImportRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=128)
    # full_name values (e.g. "team/handbook") selected from a prior discover.
    repos: list[str] = Field(min_length=1)


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


class OtherFile(BaseModel):
    """A non-page file in a directory (image, diagram, binary, etc.)."""

    name: str  # filename with extension
    path: str  # relative path within the source
    kind: str  # "image" | "drawio" | "text" | "binary"


class DirChildren(BaseModel):
    """Response for a directory's children, including non-page files."""

    children: list[PageNode] = Field(default_factory=list)
    other_files: list[OtherFile] = Field(default_factory=list)


class PageNode(BaseModel):
    path: str
    title: str  # markdown H1, or beautified stem fallback
    filename: str  # sidebar label / on-disk filename including extension (e.g. "foo.md")
    is_directory: bool
    children: list[PageNode] = Field(default_factory=list)
    has_more: bool = False
    kind: str = "page"  # "page" | "pdf"
    other_files: list[OtherFile] = Field(default_factory=list)


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
    source_id: str | None = None


class HealthResponse(BaseModel):
    status: str


class ClientConfig(BaseModel):
    drawio_url: str


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
