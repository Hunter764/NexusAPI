"""
Redis-backed sliding window rate limiter.
60 requests per minute per organisation across all product endpoints.

Strategy: Fail-open — if Redis is unavailable, requests are allowed through
with a warning log. API availability is prioritised over rate limiting.
"""

import time
import structlog
from redis.asyncio import Redis

from app.config import settings
from app.exceptions import RateLimitExceededError

logger = structlog.get_logger("nexusapi.rate_limiter")

# Rate limit configuration
WINDOW_SECONDS = 60
MAX_REQUESTS = settings.RATE_LIMIT_PER_MINUTE


class RateLimiter:
    """
    Sliding window rate limiter using Redis sorted sets.

    Uses a sorted set per org where each element is a timestamp.
    On each request:
    1. Remove entries older than the window
    2. Count remaining entries
    3. If under limit, add the new timestamp
    4. If over limit, raise RateLimitExceededError with Retry-After
    """

    def __init__(self, redis_client: Redis | None):
        self.redis = redis_client

    async def check_rate_limit(self, organisation_id: str) -> None:
        """
        Check and enforce rate limit for the given organisation.

        Args:
            organisation_id: UUID string of the organisation.

        Raises:
            RateLimitExceededError: If the organisation has exceeded the limit.
        """
        if self.redis is None:
            logger.warning(
                "rate_limiter_skipped",
                reason="redis_unavailable",
                organisation_id=organisation_id,
            )
            return  # Fail open

        key = f"rate_limit:{organisation_id}"
        now = time.time()
        window_start = now - WINDOW_SECONDS

        try:
            pipe = self.redis.pipeline(transaction=True)
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current window entries
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Set key expiry to auto-cleanup
            pipe.expire(key, WINDOW_SECONDS + 1)
            results = await pipe.execute()

            request_count = results[1]  # zcard result

            if request_count >= MAX_REQUESTS:
                # Calculate retry_after: time until the oldest entry expires
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_timestamp = oldest[0][1]
                    retry_after = int(
                        WINDOW_SECONDS - (now - oldest_timestamp)
                    )
                    retry_after = max(1, retry_after)
                else:
                    retry_after = WINDOW_SECONDS

                # Remove the entry we just added since it exceeds the limit
                await self.redis.zrem(key, str(now))

                raise RateLimitExceededError(retry_after=retry_after)

        except RateLimitExceededError:
            raise
        except Exception as e:
            # Fail open — log the error but allow the request
            logger.error(
                "rate_limiter_error",
                error=str(e),
                organisation_id=organisation_id,
            )
            return
