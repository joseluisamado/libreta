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
