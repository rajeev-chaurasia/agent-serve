# concurrency_notes.py — asyncio patterns, thread pools, and synchronisation primitives
#
# This file is a runnable reference; each section can be executed independently.

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


# --- asyncio basics ---

async def fetch_page(url: str, delay: float = 0.1) -> str:
    """Simulate an async HTTP fetch with a non-blocking sleep."""
    await asyncio.sleep(delay)       # yields control to the event loop
    return f"<html>{url}</html>"


async def fetch_all(urls: list[str]) -> list[str]:
    """Fetch all URLs concurrently using asyncio.gather."""
    # gather schedules all coroutines simultaneously; completes when all finish.
    results = await asyncio.gather(*(fetch_page(u) for u in urls))
    return list(results)


async def producer_consumer_demo() -> None:
    """asyncio.Queue decouples producers from consumers without locks."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    async def producer():
        for i in range(5):
            await queue.put(i)
            await asyncio.sleep(0.05)
        await queue.put(None)         # sentinel to signal completion

    async def consumer():
        while True:
            item = await queue.get()
            if item is None:
                break
            print(f"consumed: {item}")
            queue.task_done()

    await asyncio.gather(producer(), consumer())


# --- asyncio timeouts ---

async def with_timeout(coro, seconds: float):
    """Wrap a coroutine with a deadline; raises asyncio.TimeoutError on expiry."""
    return await asyncio.wait_for(coro, timeout=seconds)


# --- Thread pool (CPU/IO bound work from async code) ---

def cpu_bound_task(n: int) -> int:
    """Simulate CPU-bound work — summing squares up to n."""
    return sum(i * i for i in range(n))


async def run_in_thread(n: int) -> int:
    """Offload blocking/CPU work to a thread pool without blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, cpu_bound_task, n)


# --- Threading with locks ---

class SafeCounter:
    """Thread-safe counter using a reentrant lock."""

    def __init__(self):
        self._value = 0
        self._lock = threading.RLock()

    def increment(self, by: int = 1) -> None:
        with self._lock:             # acquired on enter, released on exit (even on exception)
            self._value += by

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


def thread_pool_demo() -> None:
    """Use ThreadPoolExecutor for concurrent I/O-bound tasks in synchronous code."""
    def blocking_io(i: int) -> str:
        time.sleep(0.1)              # simulates network/disk wait
        return f"result-{i}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(blocking_io, i) for i in range(8)]
        results = [f.result() for f in futures]
    print(results)


# --- Process pool (true parallelism for CPU-bound) ---

def process_pool_demo(items: list[int]) -> list[int]:
    """ProcessPoolExecutor bypasses the GIL for real parallel CPU work."""
    with ProcessPoolExecutor() as pool:
        return list(pool.map(cpu_bound_task, items))


if __name__ == "__main__":
    urls = [f"https://example.com/page/{i}" for i in range(5)]
    pages = asyncio.run(fetch_all(urls))
    print(f"Fetched {len(pages)} pages concurrently")

    asyncio.run(producer_consumer_demo())
    thread_pool_demo()
