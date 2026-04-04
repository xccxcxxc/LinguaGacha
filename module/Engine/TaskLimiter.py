import threading
import time
from typing import Callable


class TaskLimiter:
    SECONDS_PER_MINUTE = 60
    SECONDS_PER_DAY = 86400

    def __init__(
        self,
        rps: int,
        rpm: int,
        max_concurrency: int = 0,
        tpm: int = 0,
        tpd: int = 0,
    ) -> None:
        self.rps = int(rps)
        self.rpm = int(rpm)
        self.tpm = int(tpm)
        self.tpd = int(tpd)

        self.max_capacity = self.calculate_max_capacity()
        self.rate_per_second = self.calculate_stricter_rate()
        self.current_capacity = self.max_capacity
        self.current_tpm_capacity = self.calculate_token_capacity(self.tpm)
        self.current_tpd_capacity = self.calculate_token_capacity(self.tpd)
        self.tpm_rate_per_second = self.calculate_token_refill_rate(
            self.tpm,
            self.SECONDS_PER_MINUTE,
        )
        self.tpd_rate_per_second = self.calculate_token_refill_rate(
            self.tpd,
            self.SECONDS_PER_DAY,
        )
        self.last_refill_time = time.time()

        # 使用 BoundedSemaphore 避免 release 失配导致并发上限“被抬高”。
        self.semaphore: threading.BoundedSemaphore | None = (
            threading.BoundedSemaphore(max_concurrency) if max_concurrency > 0 else None
        )
        self.max_concurrency = int(max_concurrency)

        self.in_use_concurrency = 0
        self.in_use_concurrency_lock = threading.Lock()

        # 令牌桶必须线程安全。
        self.bucket_lock = threading.Lock()

    def calculate_max_capacity(self) -> float:
        # 这里的“令牌”表示“请求许可”。每次请求消耗 1 个令牌。
        # 当 rpm < 60 时，rate_per_second 会小于 1；如果桶容量也被钳制到 < 1，
        # 则 current_capacity 永远无法累计到 >= 1，wait() 会进入永久等待。
        stricter_rate = self.calculate_stricter_rate()
        if stricter_rate == float("inf"):
            return float("inf")
        return max(1.0, stricter_rate)

    def calculate_stricter_rate(self) -> float:
        return min(
            self.rps if self.rps > 0 else float("inf"),
            self.rpm / self.SECONDS_PER_MINUTE if self.rpm > 0 else float("inf"),
        )

    def calculate_token_capacity(self, token_limit: int) -> float:
        if token_limit <= 0:
            return float("inf")
        return float(token_limit)

    def calculate_token_refill_rate(
        self, token_limit: int, window_seconds: int
    ) -> float:
        if token_limit <= 0:
            return float("inf")
        return float(token_limit) / float(window_seconds)

    def refill_buckets(self, now: float) -> None:
        elapsed_time = now - self.last_refill_time
        if elapsed_time <= 0:
            return

        # 请求额度和 token 额度共用同一刷新时钟，避免不同窗口各自漂移。
        self.current_capacity = min(
            self.max_capacity,
            self.current_capacity + elapsed_time * self.rate_per_second,
        )
        self.current_tpm_capacity = min(
            self.calculate_token_capacity(self.tpm),
            self.current_tpm_capacity + elapsed_time * self.tpm_rate_per_second,
        )
        self.current_tpd_capacity = min(
            self.calculate_token_capacity(self.tpd),
            self.current_tpd_capacity + elapsed_time * self.tpd_rate_per_second,
        )
        self.last_refill_time = now

    def acquire(self, stop_checker: Callable[[], bool] | None = None) -> bool:
        if self.semaphore is None:
            if stop_checker is not None and stop_checker():
                return False
            with self.in_use_concurrency_lock:
                self.in_use_concurrency += 1
            return True

        while True:
            if stop_checker is not None and stop_checker():
                return False
            acquired = self.semaphore.acquire(timeout=0.1)
            if not acquired:
                continue
            with self.in_use_concurrency_lock:
                self.in_use_concurrency += 1
            return True

    def release(self) -> None:
        if self.semaphore is not None:
            self.semaphore.release()
        with self.in_use_concurrency_lock:
            if self.in_use_concurrency > 0:
                self.in_use_concurrency -= 1

    def get_concurrency_in_use(self) -> int:
        with self.in_use_concurrency_lock:
            return self.in_use_concurrency

    def get_concurrency_limit(self) -> int:
        return max(0, int(self.max_concurrency))

    def consume_tokens(self, token_count: int) -> None:
        if token_count <= 0:
            return

        with self.bucket_lock:
            now = time.time()
            self.refill_buckets(now)

            # 真实 token 用量只有请求完成后才知道，因此这里按实际消耗记账，
            # 后续请求再等待额度恢复，避免 UI 配置成了可见但不生效的摆设。
            if self.current_tpm_capacity != float("inf"):
                self.current_tpm_capacity = self.current_tpm_capacity - float(
                    token_count
                )
            if self.current_tpd_capacity != float("inf"):
                self.current_tpd_capacity = self.current_tpd_capacity - float(
                    token_count
                )

    def wait(self, stop_checker: Callable[[], bool] | None = None) -> bool:
        if (
            self.max_capacity == float("inf")
            and self.current_tpm_capacity == float("inf")
            and self.current_tpd_capacity == float("inf")
        ):
            return True

        while True:
            if stop_checker is not None and stop_checker():
                return False

            with self.bucket_lock:
                now = time.time()
                self.refill_buckets(now)

                has_request_budget = self.current_capacity >= 1
                has_tpm_budget = self.current_tpm_capacity >= 0
                has_tpd_budget = self.current_tpd_capacity >= 0

                if has_request_budget and has_tpm_budget and has_tpd_budget:
                    self.current_capacity = self.current_capacity - 1
                    return True

                wait_time = 0.0
                if not has_request_budget and self.rate_per_second != float("inf"):
                    wait_time = max(
                        wait_time,
                        (1 - self.current_capacity) / self.rate_per_second,
                    )
                if not has_tpm_budget and self.tpm_rate_per_second != float("inf"):
                    wait_time = max(
                        wait_time,
                        (0 - self.current_tpm_capacity) / self.tpm_rate_per_second,
                    )
                if not has_tpd_budget and self.tpd_rate_per_second != float("inf"):
                    wait_time = max(
                        wait_time,
                        (0 - self.current_tpd_capacity) / self.tpd_rate_per_second,
                    )

            time.sleep(min(wait_time, 0.25))
