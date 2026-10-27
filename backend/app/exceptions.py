"""서비스 계층 예외. HTTP 상태 코드로 바꾸는 일은 main.py가 한다."""


class AppError(Exception):
    status_code = 400
    headers: dict[str, str] | None = None

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnauthorizedError(AppError):
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class InvalidInputError(AppError):
    status_code = 422


class UpstreamError(AppError):
    """Supabase 같은 외부 서비스 호출 실패."""

    status_code = 502
