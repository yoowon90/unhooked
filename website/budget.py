"""Monthly spending budget.

A user sets a single monthly budget (in dollars). The home dashboard and the
REST API surface, for the *current calendar month*:

  - how much has been spent so far,
  - how much of the budget remains,
  - what percent of the budget has been used, and
  - whether the user has gone over budget.

"Spent" means the money the user actually parted with for items purchased in
the month — i.e. the taxed price plus any delivery fee (``total_price``), not
the sticker price.
"""
import datetime


def _month_bounds(day):
    """Return ``[start, end)`` datetimes bounding the calendar month that
    contains ``day`` (a date or datetime).

    ``start`` is midnight on the 1st; ``end`` is midnight on the 1st of the
    following month, so the range is half-open and a purchase made at 23:59 on
    the last day of the month still falls inside it.
    """
    start = datetime.datetime(day.year, day.month, 1)
    end = start.replace(month=start.month + 1)
    return start, end


def month_spend(items, as_of=datetime.datetime.now()):
    """Total actually spent on items purchased during the calendar month of
    ``as_of``. ``items`` is an iterable of WishItem."""
    start, end = _month_bounds(as_of)
    total = 0.0
    for item in items:
        if item.purchased and item.purchase_date is not None:
            if start <= item.purchase_date < end:
                total += item.price or 0
    return round(total, 2)


def budget_status(user, as_of=None):
    """Build the budget summary dict rendered by the home page and returned by
    the API. ``as_of`` defaults to now (used to pick the calendar month)."""
    if as_of is None:
        as_of = datetime.datetime.now()

    budget = user.monthly_budget
    spent = month_spend(user.wishitems, as_of)
    remaining = budget - spent
    percent_used = round(spent / budget * 100)

    return {
        'budget': round(budget, 2),
        'spent': spent,
        'remaining': round(remaining, 2),
        'percent_used': percent_used,
        'over_budget': remaining < 0,
        'month_label': as_of.strftime('%B %Y'),
    }
