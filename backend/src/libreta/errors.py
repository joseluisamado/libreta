class LibretaError(Exception):
    status_code: int = 500


class PageNotFoundError(LibretaError):
    status_code = 404


class AssetNotFoundError(LibretaError):
    status_code = 404


class InvalidPathError(LibretaError):
    status_code = 400


class ContentRepoUnavailableError(LibretaError):
    status_code = 503


class PageAlreadyExistsError(LibretaError):
    status_code = 409


class PageNotEmptyError(LibretaError):
    status_code = 409


class FrontmatterInBodyError(LibretaError):
    """A page body was passed with a leading ``---`` YAML fence.

    Frontmatter is set via the ``meta`` channel, not embedded in ``body``. A
    body that opens with ``---`` is almost always a caller mistake (e.g. an MCP
    client pasting full markdown); persisting it would store the YAML as visible
    page content. Raised instead of silently corrupting the page.
    """

    status_code = 422


class WatchedLabelNotFoundError(LibretaError):
    status_code = 404


class WatchedFolderAlreadyExistsError(LibretaError):
    status_code = 409


class WatchedFileOutsideRootError(LibretaError):
    status_code = 400


class WatchedFolderNotAccessibleError(LibretaError):
    status_code = 400


class GitSourceNotFoundError(LibretaError):
    status_code = 404


class GitSourceAlreadyExistsError(LibretaError):
    status_code = 409


class GitSourceCloneError(LibretaError):
    status_code = 500


class GitSourceSyncError(LibretaError):
    status_code = 500


class SshKeyNotFoundError(LibretaError):
    status_code = 404


class SshKeyAlreadyExistsError(LibretaError):
    status_code = 409


class SshKeyInvalidError(LibretaError):
    status_code = 400


class GiteaServerNotFoundError(LibretaError):
    status_code = 404


class GiteaServerAlreadyExistsError(LibretaError):
    status_code = 409


class GiteaDiscoveryError(LibretaError):
    # The upstream Gitea server rejected the request or was unreachable.
    status_code = 502
