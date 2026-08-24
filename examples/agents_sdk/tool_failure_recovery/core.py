"""Account-scoped recovery primitives for agent tool failures."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Literal,
    Protocol,
    TypeVar,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError


IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$"
MAX_SEARCH_RESULTS = 50


# Strict operation and outcome contracts.
class StrictModel(BaseModel):
    """Reject fields that are not part of the documented tool contract."""

    model_config = ConfigDict(extra="forbid")


class OrderStatus(StrictModel):
    order_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: Literal["in_transit", "delayed", "delivered"]
    carrier: str
    last_scan: str
    estimated_delivery: str | None = None


class EscalationRequest(StrictModel):
    account_id: str = Field(pattern=IDENTIFIER_PATTERN)
    order_id: str = Field(pattern=IDENTIFIER_PATTERN)
    reason: str = Field(min_length=10)
    idempotency_key: str = Field(min_length=8)


class EscalationRecord(StrictModel):
    escalation_id: str
    account_id: str = Field(pattern=IDENTIFIER_PATTERN)
    order_id: str = Field(pattern=IDENTIFIER_PATTERN)
    reason: str
    idempotency_key: str
    status: Literal["open"] = "open"


class AttemptEvent(StrictModel):
    operation: str
    attempt: int = Field(ge=1)
    fault_kind: str
    result: str
    error_code: str | None = None
    retryable: bool = False
    side_effect_committed: bool = False


class ToolOutcome(StrictModel):
    status: Literal["success", "handoff_required"]
    data: dict[str, Any] | None = None
    error_code: str | None = None
    attempts: int = Field(ge=1)
    confirmed_side_effect: bool = False
    events: list[AttemptEvent] = Field(default_factory=list)


class SyntheticToolError(RuntimeError):
    """Base error raised by the synthetic dependency."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        committed: bool | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.committed = committed
        self.retry_after_seconds = retry_after_seconds


class TransientToolError(SyntheticToolError):
    """A failure that may succeed on a later attempt."""


class PermanentToolError(SyntheticToolError):
    """A failure that should not be retried."""


class AcknowledgementLostError(TransientToolError):
    """The write committed, but its success response was lost."""


# Deterministic dependency fault injection.
class FaultKind(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    INCOMPLETE_RESPONSE = "incomplete_response"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    SLOW_RESPONSE = "slow_response"
    COMMIT_THEN_TIMEOUT = "commit_then_timeout"
    ACKNOWLEDGEMENT_LOST = "acknowledgement_lost_after_commit"
    PERMANENT_AFTER_COMMIT = "permanent_failure_after_commit"


@dataclass(frozen=True)
class FaultStep:
    kind: FaultKind
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")


@dataclass
class FaultPlan:
    steps: list[FaultStep]
    attempts: int = 0
    last_step: FaultStep | None = None

    def next_step(self) -> FaultStep:
        if self.attempts < len(self.steps):
            step = self.steps[self.attempts]
        else:
            step = FaultStep(FaultKind.SUCCESS)

        self.attempts += 1
        self.last_step = step
        return step


def make_fault_plan(*kinds: FaultKind) -> FaultPlan:
    return FaultPlan([FaultStep(kind) for kind in kinds])


def make_slow_then_success_plan(delay_seconds: float) -> FaultPlan:
    return FaultPlan(
        [
            FaultStep(FaultKind.SLOW_RESPONSE, delay_seconds),
            FaultStep(FaultKind.SUCCESS),
        ]
    )


@runtime_checkable
class DeliveryServiceAdapter(Protocol):
    """Application-owned boundary for authorized production dependencies."""

    def authorize_account(self, account_id: str) -> None:
        """Reject an account outside the authenticated application scope."""

    async def authorize_order(
        self, account_id: str, order_id: str
    ) -> None:
        """Verify an order against trusted account ownership."""

    async def read_order(
        self, account_id: str, order_id: str
    ) -> dict[str, Any]:
        """Read one account-scoped order from the real dependency."""

    async def find_orders(
        self, account_id: str, filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Return account-scoped records matching trusted filters."""

    async def create_escalation(
        self, account_id: str, request: EscalationRequest
    ) -> dict[str, Any]:
        """Create one application-authorized idempotent escalation."""

    async def lookup_escalation(
        self, account_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        """Fetch authoritative state without replaying a write."""

    def remember_escalation(
        self, record: EscalationRecord, request: EscalationRequest
    ) -> None:
        """Cache only an account- and fingerprint-verified record."""

    def get_escalation_by_key(
        self, account_id: str, idempotency_key: str
    ) -> EscalationRecord | None:
        """Expose previously verified state to synchronous renderers."""

    @property
    def escalation_count(self) -> int:
        """Count authoritative records confirmed during this workflow."""


# Account-scoped delivery service and authoritative write ledger.
class SyntheticDeliveryService:
    def __init__(self) -> None:
        self.orders = {
            "ORDER-1001": OrderStatus(
                order_id="ORDER-1001",
                status="delayed",
                carrier="Example Carrier",
                last_scan="Regional sorting facility",
                estimated_delivery="2026-07-24",
            ),
            "ORDER-2002": OrderStatus(
                order_id="ORDER-2002",
                status="delayed",
                carrier="Example Carrier",
                last_scan="Another customer's sorting facility",
            ),
        }
        self.account_id = "ACCOUNT-001"
        self.order_account_ids = {
            "ORDER-1001": "ACCOUNT-001",
            "ORDER-2002": "ACCOUNT-002",
        }
        self.read_account_ids: list[str] = []
        self.search_account_ids: list[str] = []
        self.search_filter_history: list[dict[str, str]] = []
        self.write_account_ids: list[str] = []
        self.reconciliation_account_ids: list[str] = []
        self._escalations_by_key: dict[
            tuple[str, str], EscalationRecord
        ] = {}
        self._escalation_sequence = 0

    @property
    def escalation_count(self) -> int:
        return len(self._escalations_by_key)

    def _authorize_account(self, account_id: str) -> None:
        if account_id != self.account_id:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )

    def _authorize_order(
        self, account_id: str, order_id: str
    ) -> None:
        self._authorize_account(account_id)
        owner_account_id = self.order_account_ids.get(order_id)
        if owner_account_id != account_id:
            raise PermanentToolError(
                "order_not_found",
                retryable=False,
                status_code=404,
                committed=False,
            )

    def _raise_precommit_fault(self, kind: FaultKind) -> None:
        if kind == FaultKind.TIMEOUT:
            raise TransientToolError(
                "timeout", retryable=True, committed=False
            )
        if kind == FaultKind.RATE_LIMITED:
            raise TransientToolError(
                "rate_limited",
                retryable=True,
                status_code=429,
                committed=False,
            )
        if kind == FaultKind.UNAVAILABLE:
            raise TransientToolError(
                "dependency_unavailable",
                retryable=True,
                status_code=503,
                committed=False,
            )
        if kind == FaultKind.FORBIDDEN:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )
        if kind == FaultKind.NOT_FOUND:
            raise PermanentToolError(
                "not_found",
                retryable=False,
                status_code=404,
                committed=False,
            )

    def execute_order_status_step(
        self, account_id: str, order_id: str, step: FaultStep
    ) -> dict[str, Any]:
        self.read_account_ids.append(account_id)
        self._authorize_order(account_id, order_id)
        self._raise_precommit_fault(step.kind)

        if step.kind == FaultKind.ACKNOWLEDGEMENT_LOST:
            raise PermanentToolError(
                "invalid_fault_for_read", retryable=False
            )

        order = self.orders[order_id]

        if step.kind == FaultKind.MALFORMED_RESPONSE:
            return {"unexpected": "payload"}
        if step.kind == FaultKind.INCOMPLETE_RESPONSE:
            return {"order_id": order_id, "status": order.status}

        return order.model_dump(mode="json")

    def get_order_status(
        self, account_id: str, order_id: str, fault_plan: FaultPlan
    ) -> dict[str, Any]:
        return self.execute_order_status_step(
            account_id, order_id, fault_plan.next_step()
        )

    def search_orders(
        self, account_id: str, filters: dict[str, str]
    ) -> list[OrderStatus]:
        self.search_account_ids.append(account_id)
        self.search_filter_history.append(dict(filters))
        self._authorize_account(account_id)
        if set(filters) - {"status", "carrier"}:
            raise PermanentToolError("invalid_search_filter", retryable=False)
        return [
            order
            for order in self.orders.values()
            if self.order_account_ids[order.order_id] == account_id
            and all(
                getattr(order, name) == value
                for name, value in filters.items()
            )
        ]

    def execute_order_search_step(
        self,
        account_id: str,
        filters: dict[str, str],
        step: FaultStep,
    ) -> list[dict[str, Any]]:
        self._authorize_account(account_id)
        self._raise_precommit_fault(step.kind)
        if step.kind == FaultKind.ACKNOWLEDGEMENT_LOST:
            raise PermanentToolError(
                "invalid_fault_for_read", retryable=False
            )

        orders = self.search_orders(account_id, filters)
        if step.kind == FaultKind.MALFORMED_RESPONSE:
            return [{"unexpected": "payload"}]
        if step.kind == FaultKind.INCOMPLETE_RESPONSE:
            return [{"order_id": "ORDER-1001"}]

        return [order.model_dump(mode="json") for order in orders]

    def _commit_escalation(
        self, account_id: str, request: EscalationRequest
    ) -> EscalationRecord:
        self._authorize_order(account_id, request.order_id)
        if request.account_id != account_id:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )
        ledger_key = (account_id, request.idempotency_key)
        existing = self._escalations_by_key.get(ledger_key)
        if existing is not None:
            if (
                existing.account_id != request.account_id
                or existing.order_id != request.order_id
                or existing.reason != request.reason
            ):
                raise PermanentToolError(
                    "idempotency_key_conflict",
                    retryable=False,
                    committed=False,
                )
            return existing

        if self.orders[request.order_id].status != "delayed":
            raise PermanentToolError(
                "write_precondition_failed",
                retryable=False,
                status_code=409,
                committed=False,
            )

        self._escalation_sequence += 1
        record = EscalationRecord(
            escalation_id=f"ESC-{self._escalation_sequence:04d}",
            account_id=account_id,
            order_id=request.order_id,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
        )
        self._escalations_by_key[ledger_key] = record
        return record

    def execute_escalation_step(
        self,
        account_id: str,
        request: EscalationRequest,
        step: FaultStep,
    ) -> dict[str, Any]:
        self.write_account_ids.append(account_id)
        self._authorize_order(account_id, request.order_id)
        if request.account_id != account_id:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )
        self._raise_precommit_fault(step.kind)
        record = self._commit_escalation(account_id, request)

        if step.kind == FaultKind.ACKNOWLEDGEMENT_LOST:
            raise AcknowledgementLostError(
                "acknowledgement_lost",
                retryable=True,
                committed=True,
            )
        if step.kind == FaultKind.PERMANENT_AFTER_COMMIT:
            raise PermanentToolError(
                "post_commit_permanent_failure",
                retryable=False,
                committed=True,
            )
        if step.kind == FaultKind.MALFORMED_RESPONSE:
            return {"unexpected": "payload"}
        if step.kind == FaultKind.INCOMPLETE_RESPONSE:
            return {"escalation_id": record.escalation_id}

        return record.model_dump(mode="json")

    def create_delivery_escalation(
        self,
        account_id: str,
        request: EscalationRequest,
        fault_plan: FaultPlan,
    ) -> dict[str, Any]:
        return self.execute_escalation_step(
            account_id, request, fault_plan.next_step()
        )

    def get_escalation_by_key(
        self, account_id: str, idempotency_key: str
    ) -> EscalationRecord | None:
        self._authorize_account(account_id)
        record = self._escalations_by_key.get(
            (account_id, idempotency_key)
        )
        if record is not None and record.account_id != account_id:
            raise PermanentToolError(
                "idempotency_key_conflict", retryable=False
            )
        return record

    def execute_escalation_lookup_step(
        self,
        account_id: str,
        idempotency_key: str,
        step: FaultStep,
    ) -> dict[str, Any] | None:
        self.reconciliation_account_ids.append(account_id)
        self._authorize_account(account_id)
        self._raise_precommit_fault(step.kind)
        if step.kind == FaultKind.MALFORMED_RESPONSE:
            return {"unexpected": "payload"}
        if step.kind == FaultKind.INCOMPLETE_RESPONSE:
            return {"account_id": account_id}
        record = self.get_escalation_by_key(
            account_id, idempotency_key
        )
        if record is None:
            return None
        return record.model_dump(mode="json")


RecoveryService = SyntheticDeliveryService | DeliveryServiceAdapter


# Intentionally unsafe baseline used for controlled comparison.
def run_unsafe_read(fault_plan: FaultPlan) -> dict[str, Any]:
    service = SyntheticDeliveryService()

    try:
        raw_result = service.get_order_status(
            "ACCOUNT-001", "ORDER-1001", fault_plan
        )
    except SyntheticToolError as error:
        return {
            "result": "stopped_on_error",
            "error_code": error.code,
            "attempts": fault_plan.attempts,
        }

    try:
        OrderStatus.model_validate(raw_result)
        result = "valid_output_returned"
    except ValidationError:
        result = "invalid_output_returned"

    return {
        "result": result,
        "error_code": None,
        "attempts": fault_plan.attempts,
    }


# Shared bounded retry and handoff policy.
class RecoveryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    base_delay_seconds: float = Field(default=0.1, ge=0)
    jitter_ratio: float = Field(default=0.25, ge=0, le=1)
    max_delay_seconds: float = Field(default=2.0, gt=0)
    retry_invalid_output: bool = True


class FailureDecision(StrictModel):
    error_code: str
    should_retry: bool


def fault_name(fault_plan: FaultPlan) -> str:
    if fault_plan.last_step is None:
        return "unknown"
    return fault_plan.last_step.kind.value


def decide_failure(
    *,
    error_code: str,
    retryable: bool,
    attempt: int,
    policy: RecoveryPolicy,
    retry_after_seconds: float = 0.0,
) -> FailureDecision:
    return FailureDecision(
        error_code=error_code,
        should_retry=(
            retryable
            and attempt < policy.max_attempts
            and retry_after_seconds <= policy.max_delay_seconds
        ),
    )


async def wait_before_retry(
    attempt: int,
    policy: RecoveryPolicy,
    *,
    sleep_fn: Callable[[float], Awaitable[None]],
    randomizer: random.Random,
    minimum_delay_seconds: float = 0,
) -> None:
    if minimum_delay_seconds > policy.max_delay_seconds:
        raise ValueError(
            "Dependency Retry-After exceeds the retry-delay budget."
        )
    base_delay = policy.base_delay_seconds * (2 ** (attempt - 1))
    jitter = randomizer.uniform(0, base_delay * policy.jitter_ratio)
    requested_delay = max(
        base_delay + jitter,
        max(minimum_delay_seconds, 0),
    )
    await sleep_fn(min(requested_delay, policy.max_delay_seconds))


def handoff_outcome(
    decision: FailureDecision,
    attempt: int,
    events: list[AttemptEvent],
) -> ToolOutcome:
    return ToolOutcome(
        status="handoff_required",
        error_code=decision.error_code,
        attempts=attempt,
        events=events,
    )


# Deadline-aware dependency operation adapters.
ResultT = TypeVar("ResultT")


async def with_attempt_deadline(
    operation: Callable[[], Awaitable[ResultT]],
    timeout_seconds: float,
) -> ResultT:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    try:
        return await asyncio.wait_for(
            operation(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError as error:
        raise TransientToolError("timeout", retryable=True) from error


def authorize_service_account(
    service: RecoveryService, account_id: str
) -> None:
    if isinstance(service, SyntheticDeliveryService):
        service._authorize_account(account_id)
    else:
        service.authorize_account(account_id)


async def authorize_service_order(
    service: RecoveryService, account_id: str, order_id: str
) -> None:
    if isinstance(service, SyntheticDeliveryService):
        service._authorize_order(account_id, order_id)
    else:
        await service.authorize_order(account_id, order_id)


async def get_order_status_once(
    service: RecoveryService,
    account_id: str,
    order_id: str,
    fault_plan: FaultPlan,
    *,
    skip_pre_read_authorization: bool = False,
) -> dict[str, Any]:
    step = fault_plan.next_step()
    if not skip_pre_read_authorization:
        await authorize_service_order(service, account_id, order_id)
    if isinstance(service, SyntheticDeliveryService):
        await asyncio.sleep(step.delay_seconds)
        return service.execute_order_status_step(
            account_id, order_id, step
        )
    return await service.read_order(account_id, order_id)


async def create_delivery_escalation_once(
    service: RecoveryService,
    account_id: str,
    request: EscalationRequest,
    fault_plan: FaultPlan,
) -> dict[str, Any]:
    step = fault_plan.next_step()
    await authorize_service_order(
        service, account_id, request.order_id
    )
    if request.account_id != account_id:
        raise PermanentToolError(
            "forbidden",
            retryable=False,
            status_code=403,
            committed=False,
        )
    if isinstance(service, SyntheticDeliveryService):
        if step.kind == FaultKind.COMMIT_THEN_TIMEOUT:
            committed_result = service.execute_escalation_step(
                account_id, request, step
            )
            await asyncio.sleep(step.delay_seconds)
            return committed_result
        await asyncio.sleep(step.delay_seconds)
        return service.execute_escalation_step(
            account_id, request, step
        )
    return await service.create_escalation(account_id, request)


async def get_escalation_by_key_once(
    service: RecoveryService,
    account_id: str,
    idempotency_key: str,
    fault_plan: FaultPlan,
) -> dict[str, Any] | None:
    step = fault_plan.next_step()
    authorize_service_account(service, account_id)
    if isinstance(service, SyntheticDeliveryService):
        await asyncio.sleep(step.delay_seconds)
        return service.execute_escalation_lookup_step(
            account_id, idempotency_key, step
        )
    return await service.lookup_escalation(
        account_id, idempotency_key
    )


# Account- and order-bound read recovery.
async def run_read_with_recovery(
    service: RecoveryService,
    account_id: str,
    order_id: str,
    fault_plan: FaultPlan | None = None,
    policy: RecoveryPolicy | None = None,
    *,
    attempt_timeout_seconds: float = 1.0,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_seed: int | None = None,
    skip_pre_read_authorization: bool = False,
) -> ToolOutcome:
    fault_plan = fault_plan or make_fault_plan(FaultKind.SUCCESS)
    policy = policy or RecoveryPolicy()
    events: list[AttemptEvent] = []
    randomizer = random.Random(random_seed)

    async def read_verified_order() -> OrderStatus:
        raw_result = await get_order_status_once(
            service,
            account_id,
            order_id,
            fault_plan,
            skip_pre_read_authorization=skip_pre_read_authorization,
        )
        order = OrderStatus.model_validate(raw_result)
        if order.order_id != order_id:
            raise PermanentToolError(
                "unexpected_order_identity", retryable=False
            )
        if not (
            skip_pre_read_authorization
            and not isinstance(service, SyntheticDeliveryService)
            and getattr(service, "read_results_are_authorized", False)
            is True
        ):
            await authorize_service_order(
                service, account_id, order.order_id
            )
        return order

    for attempt in range(1, policy.max_attempts + 1):
        retry_after_seconds = 0.0
        try:
            order = await with_attempt_deadline(
                read_verified_order,
                attempt_timeout_seconds,
            )
        except ValidationError:
            decision = decide_failure(
                error_code="invalid_tool_output",
                retryable=policy.retry_invalid_output,
                attempt=attempt,
                policy=policy,
            )
            result = "invalid_output"
        except SyntheticToolError as error:
            retry_after_seconds = error.retry_after_seconds or 0.0
            decision = decide_failure(
                error_code=error.code,
                retryable=error.retryable,
                attempt=attempt,
                policy=policy,
                retry_after_seconds=retry_after_seconds,
            )
            result = "error"
        else:
            events.append(
                AttemptEvent(
                    operation="get_order_status",
                    attempt=attempt,
                    fault_kind=fault_name(fault_plan),
                    result="success",
                )
            )
            return ToolOutcome(
                status="success",
                data=order.model_dump(mode="json"),
                attempts=attempt,
                events=events,
            )

        events.append(
            AttemptEvent(
                operation="get_order_status",
                attempt=attempt,
                fault_kind=fault_name(fault_plan),
                result=result,
                error_code=decision.error_code,
                retryable=decision.should_retry,
            )
        )
        if not decision.should_retry:
            return handoff_outcome(decision, attempt, events)

        await wait_before_retry(
            attempt,
            policy,
            sleep_fn=sleep_fn,
            randomizer=randomizer,
            minimum_delay_seconds=retry_after_seconds,
        )

    raise AssertionError("The bounded retry loop returned no outcome.")

# Filter-preserving semantic search recovery.
class OrderSearchResults(StrictModel):
    orders: list[OrderStatus] = Field(strict=True)


async def search_orders_once(
    service: RecoveryService,
    account_id: str,
    filters: dict[str, str],
    fault_plan: FaultPlan,
) -> list[dict[str, Any]]:
    step = fault_plan.next_step()
    authorize_service_account(service, account_id)
    if isinstance(service, SyntheticDeliveryService):
        await asyncio.sleep(step.delay_seconds)
        return service.execute_order_search_step(
            account_id, filters, step
        )
    return await service.find_orders(account_id, filters)


async def run_order_search_with_recovery(
    service: RecoveryService,
    account_id: str,
    requested_filters: dict[str, str],
    inferred_filters: dict[str, str],
    policy: RecoveryPolicy,
    *,
    fault_plan: FaultPlan | None = None,
    attempt_timeout_seconds: float = 1.0,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_seed: int | None = None,
) -> ToolOutcome:
    events: list[AttemptEvent] = []
    randomizer = random.Random(random_seed)
    fault_plan = fault_plan or make_fault_plan(FaultKind.SUCCESS)

    if (
        "account_id" in requested_filters
        or "account_id" in inferred_filters
    ):
        decision = decide_failure(
            error_code="invalid_search_filter",
            retryable=False,
            attempt=1,
            policy=policy,
        )
        events.append(
            AttemptEvent(
                operation="search_orders",
                attempt=1,
                fault_kind="scope_violation",
                result="error",
                error_code=decision.error_code,
            )
        )
        return handoff_outcome(decision, 1, events)

    effective_inferred_filters = {
        name: value
        for name, value in inferred_filters.items()
        if name not in requested_filters
    }
    filters = {**effective_inferred_filters, **requested_filters}

    async def search_verified_orders() -> list[OrderStatus]:
        raw_orders = await search_orders_once(
            service, account_id, filters, fault_plan
        )
        if isinstance(raw_orders, list) and len(raw_orders) > MAX_SEARCH_RESULTS:
            raise PermanentToolError(
                "search_result_limit_exceeded", retryable=False
            )
        orders = OrderSearchResults.model_validate(
            {"orders": raw_orders}
        ).orders
        results_are_authorized = (
            not isinstance(service, SyntheticDeliveryService)
            and getattr(service, "search_results_are_authorized", False)
            is True
        )
        seen_order_ids: set[str] = set()
        for order in orders:
            if not results_are_authorized:
                await authorize_service_order(
                    service, account_id, order.order_id
                )
            if order.order_id in seen_order_ids:
                raise PermanentToolError(
                    "duplicate_search_result", retryable=False
                )
            seen_order_ids.add(order.order_id)
            if any(
                getattr(order, name, None) != value
                for name, value in filters.items()
            ):
                raise PermanentToolError(
                    "search_result_filter_mismatch",
                    retryable=False,
                )
        return orders

    for attempt in range(1, policy.max_attempts + 1):
        retry_after_seconds = 0.0
        try:
            orders = await with_attempt_deadline(
                search_verified_orders,
                attempt_timeout_seconds,
            )
        except ValidationError:
            decision = decide_failure(
                error_code="invalid_tool_output",
                retryable=policy.retry_invalid_output,
                attempt=attempt,
                policy=policy,
            )
            result = "invalid_output"
        except SyntheticToolError as error:
            retry_after_seconds = error.retry_after_seconds or 0.0
            decision = decide_failure(
                error_code=error.code,
                retryable=error.retryable,
                attempt=attempt,
                policy=policy,
                retry_after_seconds=retry_after_seconds,
            )
            result = "error"
        else:
            if orders or not effective_inferred_filters:
                events.append(
                    AttemptEvent(
                        operation="search_orders",
                        attempt=attempt,
                        fault_kind=fault_name(fault_plan),
                        result="success",
                    )
                )
                return ToolOutcome(
                    status="success",
                    data={
                        "result_count": len(orders),
                        "applied_filters": dict(filters),
                        "order_ids": [
                            order.order_id for order in orders
                        ],
                        "orders": [
                            order.model_dump(mode="json")
                            for order in orders
                        ],
                    },
                    attempts=attempt,
                    events=events,
                )

            decision = decide_failure(
                error_code="semantic_empty_unverified",
                retryable=True,
                attempt=attempt,
                policy=policy,
            )
            result = "semantic_empty"
            effective_inferred_filters = {}
            filters = dict(requested_filters)

        events.append(
            AttemptEvent(
                operation="search_orders",
                attempt=attempt,
                fault_kind=fault_name(fault_plan),
                result=result,
                error_code=decision.error_code,
                retryable=decision.should_retry,
            )
        )
        if not decision.should_retry:
            return handoff_outcome(decision, attempt, events)

        await wait_before_retry(
            attempt,
            policy,
            sleep_fn=sleep_fn,
            randomizer=randomizer,
            minimum_delay_seconds=retry_after_seconds,
        )

    raise AssertionError("The bounded order search returned no outcome.")


# Authorized, fingerprint-safe write reconciliation.
def validate_escalation_fingerprint(
    account_id: str,
    request: EscalationRequest,
    record: EscalationRecord,
) -> None:
    if (
        record.account_id != account_id
        or record.account_id != request.account_id
        or record.order_id != request.order_id
        or record.reason != request.reason
        or record.idempotency_key != request.idempotency_key
    ):
        raise PermanentToolError(
            "idempotency_key_conflict", retryable=False
        )


async def reconcile_escalation_record(
    service: RecoveryService,
    account_id: str,
    request: EscalationRequest,
    fault_plan: FaultPlan,
    timeout_seconds: float,
) -> EscalationRecord | None:
    raw_record = await with_attempt_deadline(
        lambda: get_escalation_by_key_once(
            service, account_id, request.idempotency_key, fault_plan
        ),
        timeout_seconds,
    )
    if raw_record is None:
        return None
    record = EscalationRecord.model_validate(raw_record)
    validate_escalation_fingerprint(account_id, request, record)
    if not isinstance(service, SyntheticDeliveryService):
        service.remember_escalation(record, request)
    return record


async def run_write_with_reconciliation(
    service: RecoveryService,
    account_id: str,
    request: EscalationRequest,
    fault_plan: FaultPlan | None = None,
    policy: RecoveryPolicy | None = None,
    *,
    write_authorized: bool,
    reconciliation_fault_plan: FaultPlan | None = None,
    reconciliation_timeout_seconds: float | None = None,
    attempt_timeout_seconds: float = 1.0,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_seed: int | None = None,
) -> ToolOutcome:
    fault_plan = fault_plan or make_fault_plan(FaultKind.SUCCESS)
    policy = policy or RecoveryPolicy()
    events: list[AttemptEvent] = []
    randomizer = random.Random(random_seed)
    reconciliation_fault_plan = (
        reconciliation_fault_plan
        or make_fault_plan(FaultKind.SUCCESS)
    )
    reconciliation_deadline = (
        attempt_timeout_seconds
        if reconciliation_timeout_seconds is None
        else reconciliation_timeout_seconds
    )

    if write_authorized is not True or request.account_id != account_id:
        error_code = (
            "write_not_authorized"
            if write_authorized is not True
            else "forbidden"
        )
        decision = decide_failure(
            error_code=error_code,
            retryable=False,
            attempt=1,
            policy=policy,
        )
        events.append(
            AttemptEvent(
                operation="create_delivery_escalation",
                attempt=1,
                fault_kind="authorization",
                result="error",
                error_code=error_code,
            )
        )
        return handoff_outcome(decision, 1, events)

    for attempt in range(1, policy.max_attempts + 1):
        committed: EscalationRecord | None = None
        must_reconcile = False
        known_committed = False
        retry_after_seconds = 0.0
        try:
            raw_result = await with_attempt_deadline(
                lambda: create_delivery_escalation_once(
                    service, account_id, request, fault_plan
                ),
                attempt_timeout_seconds,
            )
            record = EscalationRecord.model_validate(raw_result)
            validate_escalation_fingerprint(
                account_id, request, record
            )
        except AcknowledgementLostError as error:
            error_code = error.code
            result = "ambiguous"
            retryable = False
            must_reconcile = True
            known_committed = True
        except ValidationError:
            error_code = "invalid_tool_output"
            result = "invalid_output"
            retryable = policy.retry_invalid_output
            must_reconcile = True
        except SyntheticToolError as error:
            error_code = error.code
            result = "error"
            retryable = error.retryable
            retry_after_seconds = error.retry_after_seconds or 0.0
            must_reconcile = (
                error.retryable or error.committed is not False
            )
            known_committed = error.committed is True
        else:
            events.append(
                AttemptEvent(
                    operation="create_delivery_escalation",
                    attempt=attempt,
                    fault_kind=fault_name(fault_plan),
                    result="success",
                    side_effect_committed=True,
                )
            )
            return ToolOutcome(
                status="success",
                data=record.model_dump(mode="json"),
                attempts=attempt,
                confirmed_side_effect=True,
                events=events,
            )

        if must_reconcile:
            try:
                committed = await reconcile_escalation_record(
                    service,
                    account_id,
                    request,
                    reconciliation_fault_plan,
                    reconciliation_deadline,
                )
            except (SyntheticToolError, ValidationError) as error:
                lookup_error_code = (
                    error.code
                    if isinstance(error, SyntheticToolError)
                    else "invalid_tool_output"
                )
                final_error_code = (
                    lookup_error_code
                    if lookup_error_code in {
                        "forbidden", "idempotency_key_conflict"
                    }
                    else "ambiguous_write"
                )
                events.append(
                    AttemptEvent(
                        operation="create_delivery_escalation",
                        attempt=attempt,
                        fault_kind=fault_name(fault_plan),
                        result="reconciliation_failed",
                        error_code=(
                            f"reconciliation_{lookup_error_code}"
                        ),
                    )
                )
                return handoff_outcome(
                    FailureDecision(
                        error_code=final_error_code,
                        should_retry=False,
                    ),
                    attempt,
                    events,
                )

            if committed is not None:
                if error_code == "acknowledgement_lost":
                    result = "reconciled"
                elif error_code == "invalid_tool_output":
                    result = "reconciled_invalid_output"
                elif not retryable:
                    result = "reconciled_permanent_error"
                else:
                    result = "reconciled_transient_error"
                retryable = False
            elif known_committed:
                error_code = "ambiguous_write"
                result = "ambiguous"
                retryable = False

        decision = decide_failure(
            error_code=error_code,
            retryable=retryable,
            attempt=attempt,
            policy=policy,
            retry_after_seconds=retry_after_seconds,
        )
        events.append(
            AttemptEvent(
                operation="create_delivery_escalation",
                attempt=attempt,
                fault_kind=fault_name(fault_plan),
                result=result,
                error_code=decision.error_code,
                retryable=decision.should_retry,
                side_effect_committed=committed is not None,
            )
        )

        if committed is not None:
            return ToolOutcome(
                status="success",
                data=committed.model_dump(mode="json"),
                attempts=attempt,
                confirmed_side_effect=True,
                events=events,
            )
        if not decision.should_retry:
            return handoff_outcome(decision, attempt, events)

        await wait_before_retry(
            attempt,
            policy,
            sleep_fn=sleep_fn,
            randomizer=randomizer,
            minimum_delay_seconds=retry_after_seconds,
        )

    raise AssertionError("The bounded retry loop returned no outcome.")
