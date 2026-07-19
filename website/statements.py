"""Read-only ledger statements for the API and mobile clients.

The ledger remains the source of truth: statements derive every amount from
immutable entries and transaction timestamps. Building a statement never
changes entries or transactions, though first access may initialize the user's
standard checking/savings account rows through ``get_or_create_accounts``.
"""
import datetime
from dataclasses import dataclass
from typing import Literal, TypedDict

from . import db
from . import ledger
from .models import LedgerAccount, LedgerEntry, LedgerTransaction

AccountKind = Literal['checking', 'savings']


class StatementLinePayload(TypedDict):
    """JSON shape for one statement line."""

    transaction_id: int
    amount_cents: int
    status: str
    memo: str
    created_at: str


class StatementPayload(TypedDict):
    """JSON shape returned by the ledger statement endpoint."""

    account: AccountKind
    start_date: str
    end_date: str
    opening_balance_cents: int
    closing_balance_cents: int
    net_change_cents: int
    transaction_count: int
    average_amount: str
    saved_cents: int
    line_items: list[StatementLinePayload]


class StatementError(ValueError):
    """Raised when a statement request is internally inconsistent."""


@dataclass(frozen=True)
class StatementLine:
    """One signed ledger entry in a statement period."""

    transaction_id: int
    amount_cents: int
    status: str
    memo: str
    created_at: datetime.datetime

    def to_dict(self) -> StatementLinePayload:
        """Serialize the line for the JSON API."""
        return {
            'transaction_id': self.transaction_id,
            'amount_cents': self.amount_cents,
            'status': self.status,
            'memo': self.memo,
            'created_at': self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class LedgerStatement:
    """Derived account balances and activity for a half-open date interval."""

    account: AccountKind
    start: datetime.datetime
    end: datetime.datetime
    opening_balance_cents: int
    closing_balance_cents: int
    line_items: list[StatementLine]
    saved_cents: int

    @property
    def net_change_cents(self) -> int:
        """Return the difference between closing and opening balances."""
        return self.closing_balance_cents - self.opening_balance_cents

    @property
    def transaction_count(self) -> int:
        """Return the number of entries shown in the statement."""
        return len(self.line_items)

    @property
    def average_amount(self) -> str:
        """Format the average absolute line-item amount in dollars."""
        if not self.line_items:
            return '$0.00'
        total_cents: int = sum(abs(line.amount_cents) for line in self.line_items)
        average_dollars: float = round(total_cents / self.transaction_count / 100, 2)
        return f'${average_dollars:,.2f}'

    def to_dict(self) -> StatementPayload:
        """Serialize the statement for the JSON API."""
        return {
            'account': self.account,
            'start_date': self.start.date().isoformat(),
            'end_date': self.end.date().isoformat(),
            'opening_balance_cents': self.opening_balance_cents,
            'closing_balance_cents': self.closing_balance_cents,
            'net_change_cents': self.net_change_cents,
            'transaction_count': self.transaction_count,
            'average_amount': self.average_amount,
            'saved_cents': self.saved_cents,
            'line_items': [line.to_dict() for line in self.line_items],
        }


def _balance_before(account_id: int, boundary: datetime.datetime) -> int:
    """Derive an account balance immediately before ``boundary``."""
    total: int = int(
        db.session.query(db.func.coalesce(db.func.sum(LedgerEntry.amount_cents), 0))
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerTransaction.created_at < boundary,
        )
        .scalar()
    )
    return total


def _saved_cents(user_id: int, start: datetime.datetime, end: datetime.datetime) -> int:
    """Return positive savings credits created during the statement period."""
    accounts: dict[str, LedgerAccount] = ledger.get_or_create_accounts(user_id)
    savings: LedgerAccount = accounts['savings']
    total: int = int(
        db.session.query(db.func.coalesce(db.func.sum(LedgerEntry.amount_cents), 0))
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .filter(
            LedgerEntry.account_id == savings.id,
            LedgerEntry.amount_cents > 0,
            LedgerTransaction.created_at >= start,
            LedgerTransaction.created_at < end,
        )
        .scalar()
    )
    return total


def build_statement(
    user_id: int,
    account_kind: AccountKind,
    start: datetime.datetime,
    end: datetime.datetime,
) -> LedgerStatement:
    """Build a read-only account statement over ``[start, end)``."""
    if start >= end:
        raise StatementError('start_date must be before end_date')

    accounts: dict[str, LedgerAccount] = ledger.get_or_create_accounts(user_id)
    account: LedgerAccount = accounts[account_kind]
    opening_balance_cents: int = _balance_before(account.id, start)
    closing_balance_cents: int = ledger.account_balance_cents(account.id)
    rows: list[tuple[LedgerEntry, LedgerTransaction]] = (
        db.session.query(LedgerEntry, LedgerTransaction)
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .filter(
            LedgerEntry.account_id == account.id,
            LedgerTransaction.user_id == user_id,
            LedgerTransaction.created_at >= start,
            LedgerTransaction.created_at < end,
        )
        .order_by(LedgerTransaction.created_at, LedgerTransaction.id)
        .all()
    )
    line_items: list[StatementLine] = [
        StatementLine(
            transaction_id=transaction.id,
            amount_cents=entry.amount_cents,
            status=transaction.status,
            memo=transaction.memo or '',
            created_at=transaction.created_at,
        )
        for entry, transaction in rows
    ]
    saved_cents: int = _saved_cents(user_id, start, end)
    return LedgerStatement(
        account=account_kind,
        start=start,
        end=end,
        opening_balance_cents=opening_balance_cents,
        closing_balance_cents=closing_balance_cents,
        line_items=line_items,
        saved_cents=saved_cents,
    )
