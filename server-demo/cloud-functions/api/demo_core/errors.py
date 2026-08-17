"""把 SDK 的类型化异常映射成 HTTP 状态码。

这是把 SDK 用进任何 HTTP 服务时都要写的一层。SDK 只负责抛出语义明确的异常，
怎么翻译成 HTTP 语义是调用方的决定 —— 下面这张表就是本 demo 的决定。

这张表和 Node 版 errors.ts 完全一致，两个仓库的 API 行为因此对齐。
"""

from __future__ import annotations

from makers_sdk import (
    AuthError,
    ConflictError,
    MakersError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
    UploadError,
    ValidationError,
)

# 顺序有意义：DeploymentTimeoutError 继承 TimeoutError，子类必须排在父类前面。
STATUS_TABLE: tuple[tuple[type[BaseException], int], ...] = (
    (ValidationError, 400),
    (AuthError, 401),
    (NotFoundError, 404),
    (ConflictError, 409),
    (RateLimitError, 429),
    (UploadError, 502),
    (TimeoutError, 504),
)


def http_status_for(error: BaseException) -> int:
    for error_type, status in STATUS_TABLE:
        if isinstance(error, error_type):
            return status
    return 500


def serialize_error(error: BaseException) -> dict[str, object]:
    if isinstance(error, MakersError):
        # 网络层失败时 code / request_id / http_status 全是 None，前端要能接受这一点。
        return {
            "name": type(error).__name__,
            "message": str(error),
            "code": error.code,
            "requestId": error.request_id,
            "httpStatus": error.http_status,
        }
    return {
        "name": type(error).__name__,
        "message": str(error),
        "code": None,
        "requestId": None,
        "httpStatus": None,
    }
