from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_real_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip, default_limits=["120/minute"])
