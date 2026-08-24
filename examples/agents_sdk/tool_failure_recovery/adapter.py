"""Connect account-scoped recovery to application-owned async dependencies."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any, Awaitable, Callable, ClassVar, TypeVar
from urllib.error import URLError

from .core import (
    EscalationRecord,
    EscalationRequest,
    MAX_SEARCH_RESULTS,
    OrderStatus,
    PermanentToolError,
    SyntheticToolError,
    TransientToolError,
    validate_escalation_fingerprint,
)

AuthorizeOrder = Callable[[str, str], Awaitable[bool]]
ReadOrder = Callable[[str, str], Awaitable[dict[str, Any]]]
SearchOrders = Callable[
    [str, dict[str, str]], Awaitable[list[dict[str, Any]]]
]
CreateEscalation = Callable[
    [str, EscalationRequest], Awaitable[dict[str, Any]]
]
LookupEscalation = Callable[
    [str, str], Awaitable[dict[str, Any] | None]
]
ResultT = TypeVar("ResultT")


@dataclass
class CallableDeliveryServiceAdapter:
    """Bind authenticated async backends to the reusable recovery boundary.

    The application owns account identity and the order-authorization
    callback. The create callback must enforce its current business
    precondition and idempotency key atomically in the backing service.
    Read and search records must identify their account or tenant; records
    without either scope field receive an explicit ownership check instead.
    """

    read_results_are_authorized: ClassVar[bool] = True
    search_results_are_authorized: ClassVar[bool] = True
    authenticated_account_id: str
    authorize_order_fn: AuthorizeOrder
    read_order_fn: ReadOrder
    search_orders_fn: SearchOrders
    create_escalation_fn: CreateEscalation
    lookup_escalation_fn: LookupEscalation
    _verified_escalations: dict[
        tuple[str, str], EscalationRecord
    ] = field(default_factory=dict, init=False, repr=False)

    @property
    def account_id(self) -> str:
        return self.authenticated_account_id

    @property
    def escalation_count(self) -> int:
        return len(self._verified_escalations)

    @staticmethod
    def _parse_retry_after(value: Any) -> float | None:
        try:
            delay_seconds = float(value)
        except (TypeError, ValueError, OverflowError):
            try:
                retry_at = parsedate_to_datetime(str(value))
            except (TypeError, ValueError, IndexError, OverflowError):
                return None
            if retry_at is None:
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay_seconds = (
                retry_at - datetime.now(timezone.utc)
            ).total_seconds()

        if not isfinite(delay_seconds):
            return None
        return max(delay_seconds, 0.0)

    @staticmethod
    def _normalize_dependency_error(
        error: Exception,
    ) -> SyntheticToolError:
        if isinstance(error, SyntheticToolError):
            return error

        response = getattr(error, "response", None)
        status_code = next(
            (
                value
                for source in (error, response)
                if source is not None
                for attribute in ("status_code", "status", "code")
                if isinstance(
                    value := getattr(source, attribute, None), int
                )
                and not isinstance(value, bool)
            ),
            None,
        )
        if not isinstance(status_code, int):
            if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
                return TransientToolError("timeout", retryable=True)
            if isinstance(error, (ConnectionError, socket.gaierror, URLError)):
                return TransientToolError(
                    "timeout"
                    if isinstance(getattr(error, "reason", None), TimeoutError)
                    else "dependency_unavailable",
                    retryable=True,
                )

            module_name = type(error).__module__.split(".", 1)[0]
            error_name = type(error).__name__
            if module_name in {"httpx", "httpcore", "aiohttp"}:
                if "Timeout" in error_name:
                    return TransientToolError("timeout", retryable=True)
                if isinstance(error, OSError) or any(
                    marker in error_name
                    for marker in (
                        "Connect",
                        "Network",
                        "Transport",
                        "Protocol",
                        "Disconnected",
                        "ReadError",
                        "WriteError",
                        "ProxyError",
                    )
                ):
                    return TransientToolError(
                        "dependency_unavailable", retryable=True
                    )
            return PermanentToolError(
                "dependency_error", retryable=False
            )

        headers = getattr(error, "headers", None)
        if headers is None and response is not None:
            headers = getattr(response, "headers", None)
        retry_after_seconds = None
        if headers is not None:
            retry_after = headers.get("Retry-After")
            if retry_after is None:
                retry_after = headers.get("retry-after")
            if retry_after is not None:
                retry_after_seconds = (
                    CallableDeliveryServiceAdapter._parse_retry_after(
                        retry_after
                    )
                )

        if status_code == 429:
            return TransientToolError(
                "rate_limited",
                retryable=True,
                status_code=status_code,
                retry_after_seconds=retry_after_seconds,
            )
        if status_code == 408 or 500 <= status_code <= 599:
            return TransientToolError(
                "timeout" if status_code == 408
                else "dependency_unavailable",
                retryable=True,
                status_code=status_code,
                retry_after_seconds=retry_after_seconds,
            )
        error_code = (
            "forbidden" if status_code in {401, 403}
            else "order_not_found" if status_code == 404
            else f"dependency_http_{status_code}"
        )
        return PermanentToolError(
            error_code,
            retryable=False,
            status_code=status_code,
        )

    async def _call_dependency(
        self,
        operation: Callable[[], Awaitable[ResultT]],
        *,
        definitively_not_committed: bool = False,
    ) -> ResultT:
        try:
            return await operation()
        except Exception as error:
            normalized = self._normalize_dependency_error(error)
            if definitively_not_committed:
                normalized.committed = False
            if normalized is error:
                raise
            raise normalized from error

    def authorize_account(self, account_id: str) -> None:
        if account_id != self.authenticated_account_id:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )

    @staticmethod
    def _validate_record_scope(
        record: dict[str, Any], account_id: str
    ) -> None:
        for scope_field in ("account_id", "tenant_id"):
            if scope_field in record and record[scope_field] != account_id:
                raise PermanentToolError(
                    "forbidden", retryable=False, status_code=403
                )

    def _normalize_order_record(
        self,
        account_id: str,
        record: dict[str, Any],
        *,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(record, dict):
            return record
        self._validate_record_scope(record, account_id)
        if order_id is not None and record.get("order_id") != order_id:
            raise PermanentToolError(
                "unexpected_order_identity", retryable=False
            )
        return {
            name: record[name]
            for name in OrderStatus.model_fields
            if name in record
        }

    def _normalize_escalation_record(
        self, account_id: str, record: dict[str, Any]
    ) -> EscalationRecord:
        if isinstance(record, dict):
            self._validate_record_scope(record, account_id)
            record = {
                name: record[name]
                for name in EscalationRecord.model_fields
                if name in record
            }
        return EscalationRecord.model_validate(record)

    async def authorize_order(
        self, account_id: str, order_id: str
    ) -> None:
        self.authorize_account(account_id)
        try:
            order_is_authorized = await self._call_dependency(
                lambda: self.authorize_order_fn(account_id, order_id),
                definitively_not_committed=True,
            )
        except PermanentToolError as error:
            if error.code != "forbidden" or error.status_code != 403:
                raise
            raise PermanentToolError(
                "order_not_found",
                retryable=False,
                status_code=404,
                committed=False,
            ) from error
        if order_is_authorized is not True:
            raise PermanentToolError(
                "order_not_found",
                retryable=False,
                status_code=404,
                committed=False,
            )

    async def read_order(
        self, account_id: str, order_id: str
    ) -> dict[str, Any]:
        await self.authorize_order(account_id, order_id)
        raw_record = await self._call_dependency(
            lambda: self.read_order_fn(account_id, order_id)
        )
        normalized_record = self._normalize_order_record(
            account_id, raw_record, order_id=order_id
        )
        if not isinstance(raw_record, dict) or not any(
            field in raw_record for field in ("account_id", "tenant_id")
        ):
            await self.authorize_order(account_id, order_id)
        return normalized_record

    async def find_orders(
        self, account_id: str, filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        self.authorize_account(account_id)
        raw_records = await self._call_dependency(
            lambda: self.search_orders_fn(account_id, dict(filters))
        )
        if not isinstance(raw_records, list):
            return raw_records
        if len(raw_records) > MAX_SEARCH_RESULTS:
            raise PermanentToolError(
                "search_result_limit_exceeded", retryable=False
            )

        normalized_records = []
        for record in raw_records:
            normalized = self._normalize_order_record(account_id, record)
            if isinstance(record, dict) and not any(
                field in record for field in ("account_id", "tenant_id")
            ):
                order = OrderStatus.model_validate(normalized)
                await self.authorize_order(account_id, order.order_id)
            normalized_records.append(normalized)
        return normalized_records

    async def create_escalation(
        self, account_id: str, request: EscalationRequest
    ) -> dict[str, Any]:
        await self.authorize_order(account_id, request.order_id)
        if request.account_id != account_id:
            raise PermanentToolError(
                "forbidden",
                retryable=False,
                status_code=403,
                committed=False,
            )
        raw_record = await self._call_dependency(
            lambda: self.create_escalation_fn(account_id, request)
        )
        record = self._normalize_escalation_record(
            account_id, raw_record
        )
        self.remember_escalation(record, request)
        return record.model_dump(mode="json")

    async def lookup_escalation(
        self, account_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        self.authorize_account(account_id)
        raw_record = await self._call_dependency(
            lambda: self.lookup_escalation_fn(
                account_id, idempotency_key
            )
        )
        if raw_record is None:
            return None
        record = self._normalize_escalation_record(
            account_id, raw_record
        )
        if (
            record.account_id != account_id
            or record.idempotency_key != idempotency_key
        ):
            raise PermanentToolError(
                "idempotency_key_conflict", retryable=False
            )
        await self.authorize_order(account_id, record.order_id)
        return record.model_dump(mode="json")

    def remember_escalation(
        self, record: EscalationRecord, request: EscalationRequest
    ) -> None:
        self.authorize_account(record.account_id)
        validate_escalation_fingerprint(
            record.account_id, request, record
        )
        ledger_key = (record.account_id, record.idempotency_key)
        existing = self._verified_escalations.get(ledger_key)
        if existing is not None and existing != record:
            raise PermanentToolError(
                "idempotency_key_conflict", retryable=False
            )
        self._verified_escalations[ledger_key] = record

    def get_escalation_by_key(
        self, account_id: str, idempotency_key: str
    ) -> EscalationRecord | None:
        self.authorize_account(account_id)
        return self._verified_escalations.get(
            (account_id, idempotency_key)
        )
