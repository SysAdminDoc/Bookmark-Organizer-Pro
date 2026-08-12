"""Shared cancellation, budget, and job-history contracts for AI work."""

from __future__ import annotations

import inspect
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


class AIOperationError(RuntimeError):
    """Base class for actionable, non-provider AI operation outcomes."""

    code = "ai_operation_error"


class AIOperationCancelled(AIOperationError):
    """Raised when a user or caller stops an AI operation."""

    code = "cancelled"


class AIBudgetExceeded(AIOperationError):
    """Raised when an AI operation reaches a declared safety budget."""

    code = "budget_exceeded"


class AICancellationToken:
    """Thread-safe stop signal shared by UI, service, retry, and stream layers."""

    def __init__(self, event: threading.Event | None = None):
        self._event = event or threading.Event()
        self._reason = "user requested stop"

    @property
    def event(self) -> threading.Event:
        return self._event

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str = "user requested stop") -> None:
        self._reason = str(reason or "user requested stop")[:200]
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def check(self) -> None:
        if self.cancelled:
            raise AIOperationCancelled(self._reason)


def estimate_tokens(text: object) -> int:
    """Use a conservative, provider-neutral character estimate for token caps."""
    value = str(text or "")
    return max(0, (len(value) + 3) // 4)


@dataclass
class AIBudget:
    """Mutable per-operation usage budget.

    Character counts are authoritative for deterministic local bounds. Token
    counts are conservative estimates used to prevent a provider call from
    exceeding the declared input/output envelope before SDK-specific usage
    metadata is available.
    """

    max_attempts: int = 3
    max_elapsed_seconds: float = 120.0
    max_input_chars: int = 40_000
    max_input_tokens: int = 10_000
    max_output_chars: int = 20_000
    max_output_tokens: int = 5_000
    started_monotonic: float = 0.0
    attempts: int = 0
    input_chars: int = 0
    input_tokens: int = 0
    output_chars: int = 0
    output_tokens: int = 0
    limit_reason: str = ""

    def __post_init__(self) -> None:
        self.max_attempts = max(1, min(20, int(self.max_attempts)))
        self.max_elapsed_seconds = max(0.1, min(3_600.0, float(self.max_elapsed_seconds)))
        self.max_input_chars = max(1, min(2_000_000, int(self.max_input_chars)))
        self.max_input_tokens = max(1, min(500_000, int(self.max_input_tokens)))
        self.max_output_chars = max(1, min(2_000_000, int(self.max_output_chars)))
        self.max_output_tokens = max(1, min(500_000, int(self.max_output_tokens)))
        if not self.started_monotonic:
            self.started_monotonic = time.monotonic()

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.max_elapsed_seconds - self.elapsed_seconds)

    def check_elapsed(self) -> None:
        if self.elapsed_seconds >= self.max_elapsed_seconds:
            self.limit_reason = "elapsed time"
            raise AIBudgetExceeded(
                f"AI operation exceeded its {self.max_elapsed_seconds:.1f}s time budget"
            )

    def begin_attempt(self) -> None:
        self.check_elapsed()
        if self.attempts >= self.max_attempts:
            self.limit_reason = "attempts"
            raise AIBudgetExceeded(
                f"AI operation reached its {self.max_attempts}-attempt budget"
            )
        self.attempts += 1

    def add_input(self, text: object) -> None:
        value = str(text or "")
        chars = len(value)
        tokens = estimate_tokens(value)
        if self.input_chars + chars > self.max_input_chars:
            self.limit_reason = "input characters"
            raise AIBudgetExceeded(
                f"AI input exceeds the {self.max_input_chars:,}-character budget"
            )
        if self.input_tokens + tokens > self.max_input_tokens:
            self.limit_reason = "input tokens"
            raise AIBudgetExceeded(
                f"AI input exceeds the {self.max_input_tokens:,}-token budget"
            )
        self.input_chars += chars
        self.input_tokens += tokens

    def add_output(self, text: object) -> None:
        value = str(text or "")
        chars = len(value)
        tokens = estimate_tokens(value)
        if self.output_chars + chars > self.max_output_chars:
            self.limit_reason = "output characters"
            raise AIBudgetExceeded(
                f"AI output exceeds the {self.max_output_chars:,}-character budget"
            )
        if self.output_tokens + tokens > self.max_output_tokens:
            self.limit_reason = "output tokens"
            raise AIBudgetExceeded(
                f"AI output exceeds the {self.max_output_tokens:,}-token budget"
            )
        self.output_chars += chars
        self.output_tokens += tokens

    def clamp_output_tokens(self, requested: int) -> int:
        try:
            value = int(requested)
        except (TypeError, ValueError):
            value = self.max_output_tokens
        return max(1, min(value, self.max_output_tokens))

    def snapshot(self) -> dict[str, int | float | str]:
        return {
            "attempts": self.attempts,
            "input_chars": self.input_chars,
            "input_tokens": self.input_tokens,
            "output_chars": self.output_chars,
            "output_tokens": self.output_tokens,
            "elapsed_ms": round(self.elapsed_seconds * 1000),
            "limit_reason": self.limit_reason,
        }


class AIOperation:
    """Own one cancellation token, usage budget, and optional job-ledger run."""

    def __init__(
        self,
        name: str,
        *,
        token: AICancellationToken | None = None,
        budget: AIBudget | None = None,
        job_ledger: Any = None,
        bookmark_id: int | None = None,
        url_or_domain: str = "",
        backend: str = "",
    ):
        self.name = str(name or "ai_operation").strip().lower().replace(" ", "_")[:40]
        self.token = token or AICancellationToken()
        self.budget = budget or AIBudget()
        self.status = "running"
        self._job_run = None
        if job_ledger is None:
            try:
                from bookmark_organizer_pro.services.job_ledger import JobLedger

                job_ledger = JobLedger()
            except Exception:
                job_ledger = None
        if job_ledger is not None:
            try:
                self._job_run = job_ledger.start(
                    f"ai_{self.name}",
                    bookmark_id=bookmark_id,
                    url_or_domain=url_or_domain,
                    backend=backend,
                )
            except Exception:
                self._job_run = None

    @property
    def job_run(self):
        return self._job_run

    def check(self) -> None:
        self.token.check()
        self.budget.check_elapsed()

    def begin_attempt(self) -> None:
        self.check()
        self.budget.begin_attempt()

    def add_input(self, text: object) -> None:
        self.check()
        self.budget.add_input(text)

    def add_output(self, text: object) -> None:
        self.check()
        self.budget.add_output(text)

    def output_tokens(self, requested: int) -> int:
        return self.budget.clamp_output_tokens(requested)

    def timeout(self, default_seconds: float) -> float:
        self.check()
        return max(0.05, min(float(default_seconds), self.budget.remaining_seconds))

    def wait(self, seconds: float) -> None:
        self.check()
        timeout = min(max(0.0, float(seconds)), self.budget.remaining_seconds)
        if self.token.wait(timeout):
            self.token.check()
        self.check()

    def _sync_metrics(self) -> None:
        if self._job_run is None:
            return
        metrics = self.budget.snapshot()
        record = self._job_run.record
        record.request_attempts = int(metrics["attempts"])
        record.input_chars = int(metrics["input_chars"])
        record.input_tokens = int(metrics["input_tokens"])
        record.output_chars = int(metrics["output_chars"])
        record.output_tokens = int(metrics["output_tokens"])
        record.limit_reason = str(metrics["limit_reason"])

    def succeed(self) -> None:
        if self.status != "running":
            return
        self.status = "success"
        self._sync_metrics()
        if self._job_run is not None:
            self._job_run.succeed(bytes_processed=self.budget.output_chars)

    def cancel(self, error: object = "cancelled") -> None:
        if self.status != "running":
            return
        self.status = "cancelled"
        self._sync_metrics()
        if self._job_run is not None:
            self._job_run.cancel(error)

    def fail(self, error: object, *, retryable: bool = True) -> None:
        if self.status != "running":
            return
        self.status = "failure"
        self._sync_metrics()
        if self._job_run is not None:
            self._job_run.fail(error, retryable=retryable, bytes_processed=self.budget.output_chars)

    def __enter__(self) -> "AIOperation":
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        if exc_type is AIOperationCancelled:
            self.cancel(exc or "cancelled")
        elif exc_type is AIBudgetExceeded:
            self.fail(exc or "AI budget exceeded", retryable=False)
        elif exc is not None:
            self.fail(exc, retryable=True)
        elif self.status == "running":
            self.succeed()
        return False


@contextmanager
def operation_scope(
    name: str,
    *,
    operation: AIOperation | None = None,
    token: AICancellationToken | None = None,
    budget: AIBudget | None = None,
    job_ledger: Any = None,
    bookmark_id: int | None = None,
    url_or_domain: str = "",
    backend: str = "",
) -> Iterator[AIOperation]:
    """Use a caller-owned operation or create/finish one for this call."""
    if operation is not None:
        yield operation
        return
    with AIOperation(
        name,
        token=token,
        budget=budget,
        job_ledger=job_ledger,
        bookmark_id=bookmark_id,
        url_or_domain=url_or_domain,
        backend=backend,
    ) as owned:
        yield owned


def call_ai(method, *args, operation: AIOperation | None = None, **kwargs):
    """Call old test doubles and new operation-aware clients safely."""
    if operation is None:
        return method(*args, **kwargs)
    try:
        parameters = inspect.signature(method).parameters.values()
        accepts_operation = any(
            parameter.name == "operation" or parameter.kind == parameter.VAR_KEYWORD
            for parameter in parameters
        )
    except (TypeError, ValueError):
        accepts_operation = True
    if accepts_operation:
        kwargs["operation"] = operation
    return method(*args, **kwargs)
