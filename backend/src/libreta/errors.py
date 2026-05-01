class LibretaError(Exception):
    status_code: int = 500


class PageNotFoundError(LibretaError):
    status_code = 404


class InvalidPathError(LibretaError):
    status_code = 400


class ContentRepoUnavailableError(LibretaError):
    status_code = 503
