"""Sliding-window-log rate limiter backed by Redis ZSET."""

import logging
import time

import redis.asyncio as redis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings, RateLimitRule

logger = logging.getLogger(__name__)


_SLIDING_WINDOW_LUA = """
local key     = KEYS[1]
local now     = tonumber(ARGV[1])
local window  = tonumber(ARGV[2])
local limit   = tonumber(ARGV[3])
local member  = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, math.ceil(window / 1000))
    return {1, count + 1, now}
end

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local oldest_score = oldest[2] or now
return {0, count, tonumber(oldest_score)}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window-log limiter; keys by user_id when known, else by IP."""

    async def dispatch(self, request: Request, call_next):
        rule, prefix = self._match(request.url.path)
        if rule is None:
            return await call_next(request)

        redis_client: redis.Redis | None = getattr(request.app.state, "redis", None)
        if redis_client is None:
            return await call_next(request)

        key = self._key(request, prefix)
        if key is None:
            return await call_next(request)

        now_us = int(time.time() * 1_000_000)
        window_us = rule.window * 1_000_000
        member = f"{now_us}:{id(request)}"

        try:
            allowed, count, oldest_us = await redis_client.eval(
                _SLIDING_WINDOW_LUA, 1, key,
                now_us, window_us, rule.limit, member,
            )
        except Exception:
            logger.warning("rate limiter unavailable, failing open", exc_info=True)
            return await call_next(request)

        if not allowed:
            retry_after = max(1, int((oldest_us + window_us - now_us) / 1_000_000) + 1)
            logger.info(
                "rate limit hit key=%s path=%s count=%s",
                key, request.url.path, count,
            )
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rule.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(
                        int((oldest_us + window_us) / 1_000_000)
                    ),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rule.limit)
        response.headers["X-RateLimit-Remaining"] = str(
            max(rule.limit - count, 0)
        )
        return response

    def _match(self, path: str) -> tuple[RateLimitRule | None, str]:
        """Longest-prefix match against ``settings.rate_limit_rules``.

        Returns:
            ``(rule, prefix)`` for the longest matching prefix, or
            ``(None, "")`` when no rule applies (path is not limited).
        """
        best_prefix = ""
        for prefix in settings.rate_limit_rules:
            if path.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
        if not best_prefix:
            return None, ""
        return settings.rate_limit_rules[best_prefix], best_prefix

    def _key(self, request: Request, prefix: str) -> str | None:
        """Compose the Redis key: user_id when authenticated, else client IP."""
        safe = prefix.strip("/").replace("/", ":")

        user = getattr(request.state, "user_id", None)
        if user is not None:
            return f"rl:{safe}:u:{user}"

        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else None
        if not ip and request.client:
            ip = request.client.host
        if not ip:
            return None
        return f"rl:{safe}:ip:{ip}"