"""Small in-memory rate limits for what visitors (students, no login) can do."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class Window:
    """At most `limit` events per key in any `seconds`-long window."""

    instances: list["Window"] = []

    def __init__(self, limit: int, seconds: int, message: str):
        self.limit, self.seconds, self.message = limit, seconds, message
        self._seen: dict[str, deque[float]] = defaultdict(deque)
        Window.instances.append(self)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        seen = self._seen[key]
        while seen and now - seen[0] > self.seconds:
            seen.popleft()
        if len(seen) >= self.limit:
            return False
        seen.append(now)
        return True

    def check(self, request: Request) -> None:
        if not self.allow(request.client.host if request.client else "?"):
            raise HTTPException(429, self.message)

    @classmethod
    def reset_all(cls) -> None:
        for w in cls.instances:
            w._seen.clear()
