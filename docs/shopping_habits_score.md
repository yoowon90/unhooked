# Shopping Habits Score

A 0-100 metric on the `/home` dashboard reflecting how mindful the user has been with online purchases over a rolling 90-day window. The UI surfaces only a category-level summary on hover of the ⓘ icon — never thresholds or point values — so weights can be tuned without retraining users on the meaning.

## Inputs (rolling 90-day window)

For each `WishItem` whose decision date (`purchase_date` or `unhooked_date`) falls within the last 90 days:

- **Waiting time** for the decision. Pulled from `WishItem.wish_period` (Interval) when present, otherwise computed as `decision_date - date`.

We tally:

- **Purchased items** bucketed by waiting-time band.
- **Unhooked items** bucketed by waiting-time band.
- **Unhook-to-purchase ratio** for the window.
- **Savings follow-through** per purchase (v3): the outcome of the
  post-purchase "Move money to savings?" interstitial (`WishItem.savings_decision`).

## Formula

```
score = base_score
      + sum(purchase_bucket_points)
      + sum(unhook_bucket_points)
      + sum(savings_decision_points)
      + ratio_bonus
score = clamp(score, 0, 100)
```

Constants live in `SCORE_WEIGHTS` at the top of `website/reports.py` so changes are localized.

### Purchase waiting-time buckets (rewards reflection before buying)

| Days waited | Points per item |
| --- | --- |
| < 7    | -8 (impulsive) |
| 7-29   | 0 |
| 30-59  | +2 |
| 60+    | +4 |

### Unhook waiting-time buckets (rewards patience before deciding not to buy)

| Days waited | Points per item |
| --- | --- |
| < 15   | 0 |
| 15-29  | +2 |
| 30-59  | +3 |
| 60-89  | +4 |
| 90+    | +5 |

### Savings-decision points (rewards following through on the savings match)

Applied once per purchase in the window, from the interstitial outcome:

| `savings_decision` | Points per item |
| --- | --- |
| `'moved'`    | +3 |
| `'declined'` | -3 |
| `None` (never prompted) | 0 |

`None` is deliberately neutral so purchases predating the feature (and
Gmail-backfilled orders, which are never prompted) don't move the score.

### Unhook-to-purchase ratio bonus

| ratio = unhooks / purchases | Bonus |
| --- | --- |
| ≥ 1.0    | +10 |
| 0.5-1.0  | +5 |
| 0.25-0.5 | 0 |
| < 0.25   | -5 |

If `purchases == 0` and `unhooks > 0`, the ratio bonus is the maximum (+10).

### Base score

`base_score = 50` so a brand-new account with no signals lands mid-pack, and bonuses can move the score in either direction within the clamp.

## Tier labels

| Score  | Tier             |
| ---    | ---              |
| 80-100 | Mindful Shopper  |
| 60-79  | Getting There    |
| 40-59  | Mixed Habits     |
| 0-39   | Impulse-prone    |

## "Not enough data"

If there are zero purchases AND zero unhooks in the last 90 days, the card shows `—` with the caption "Not enough activity in the last 90 days." rather than a misleading 50.

## UI

- 7th card on `/home`, mascot: `logo-thinking-hard.png`.
- Big number: `74 / 100`. Detail line: tier label.
- Inline ⓘ icon next to the card label. Tooltip on hover states only the high-level signals (waiting time before purchases / unhooks, balance of unhooks vs purchases, rolling 90 days) — never the bucket boundaries, point values, or formula.

## Change log

| Date       | Change |
| ---        | --- |
| 2026-05-06 | v1: signals = purchase waiting time, unhook waiting time, unhook-to-purchase ratio. Rolling 90-day window. |
| 2026-05-28 | v2: steepened impulse penalty (`< 7` days: -3 → -8) and raised long-wait rewards (30-59: +1 → +2, 60+: +2 → +4) so a single fast purchase reads as low rather than mid-pack. Base score, unhook buckets, and ratio bonus unchanged. |
| 2026-07-05 | v3: added savings follow-through signal — the post-purchase "Move money to savings?" decision now scores `moved` +3 / `declined` -3 / never-prompted 0 per purchase (`savings_bucket` in `SCORE_WEIGHTS`). All v2 buckets unchanged. |
