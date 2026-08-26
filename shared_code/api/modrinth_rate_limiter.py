import asyncio
import time
import httpx

class ModrinthRateLimiter:
    def __init__(self, max_concurrency: int = 8, buffer_seconds: float = 1.0, full_reset_seconds: float = 61.0):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.buffer_seconds = buffer_seconds
        self.full_reset_seconds = full_reset_seconds
        self.pause_until = 0.0
        self.lock = asyncio.Lock()

    async def wait_if_paused(self) -> None:
        while True:
            async with self.lock:
                now = time.monotonic()
                wait_seconds = self.pause_until - now

            if wait_seconds <= 0:
                return

            await asyncio.sleep(wait_seconds)

    async def update_from_response(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")

        if remaining is None or reset is None:
            return

        try:
            remaining_int = int(remaining)
            reset_seconds = float(reset)
        except ValueError:
            return

        if remaining_int <= 0:
            async with self.lock:
                new_pause_until = time.monotonic() + reset_seconds + self.buffer_seconds
                self.pause_until = max(self.pause_until, new_pause_until)

    async def update_from_429(self, response: httpx.Response) -> None:
        reset = response.headers.get("X-Ratelimit-Reset")

        try:
            reset_seconds = float(reset) if reset is not None else 60.0
        except ValueError:
            reset_seconds = 60.0

        async with self.lock:
            new_pause_until = time.monotonic() + reset_seconds + self.buffer_seconds
            self.pause_until = max(self.pause_until, new_pause_until)