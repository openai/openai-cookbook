import pytest
from receipt_ledger import ReceiptError, ReceiptLedger

SECRET = b"a-test-secret-that-is-at-least-32-bytes-long"
ARGS = '{"amount_usd":8200,"destination":"acct_2471"}'


def ledger() -> ReceiptLedger:
    return ReceiptLedger(SECRET)


def issue(target: ReceiptLedger, *, now: float = 100.0):
    return target.issue(
        tool_name="transfer_funds",
        tool_call_id="call_123",
        raw_arguments=ARGS,
        reviewer="finance@example.com",
        ttl_seconds=60,
        now=now,
    )


def test_exact_action_consumes_once():
    target = ledger()
    receipt = issue(target)

    consumed = target.consume(
        tool_name="transfer_funds",
        tool_call_id="call_123",
        raw_arguments=ARGS,
        now=110.0,
    )

    assert consumed.receipt_id == receipt.receipt_id
    assert consumed.consumed_at == 110.0


def test_changed_arguments_fail_closed():
    target = ledger()
    issue(target)

    with pytest.raises(ReceiptError, match="exact action"):
        target.consume(
            tool_name="transfer_funds",
            tool_call_id="call_123",
            raw_arguments='{"amount_usd":82000,"destination":"acct_2471"}',
            now=110.0,
        )


def test_wrong_call_id_has_no_receipt():
    target = ledger()
    issue(target)

    with pytest.raises(ReceiptError, match="missing"):
        target.consume(
            tool_name="transfer_funds",
            tool_call_id="call_456",
            raw_arguments=ARGS,
            now=110.0,
        )


def test_expired_receipt_fails_closed():
    target = ledger()
    issue(target)

    with pytest.raises(ReceiptError, match="expired"):
        target.consume(
            tool_name="transfer_funds",
            tool_call_id="call_123",
            raw_arguments=ARGS,
            now=161.0,
        )


def test_replay_fails_closed():
    target = ledger()
    issue(target)
    target.consume(
        tool_name="transfer_funds",
        tool_call_id="call_123",
        raw_arguments=ARGS,
        now=110.0,
    )

    with pytest.raises(ReceiptError, match="already consumed"):
        target.consume(
            tool_name="transfer_funds",
            tool_call_id="call_123",
            raw_arguments=ARGS,
            now=111.0,
        )


def test_tampered_receipt_fails_closed():
    target = ledger()
    receipt = issue(target)
    receipt.reviewer = "attacker@example.com"

    with pytest.raises(ReceiptError, match="signature"):
        target.consume(
            tool_name="transfer_funds",
            tool_call_id="call_123",
            raw_arguments=ARGS,
            now=110.0,
        )
