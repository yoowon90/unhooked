from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Response
from flask_login import login_required, current_user
from . import db
from .models import WishItem
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import datetime
import io
import random
from pytz import timezone


reports = Blueprint('reports', __name__)  # define blueprint

def format_money(money):
        def add_commas(money):
            if len(money) <= 3:
                return money
            return add_commas(money[:-3]) + ',' + money[-3:]

        money = str(money)
        if "." in money:
            dollars = money.split(".")[0]
            cents = money.split(".")[1]
            if len(cents) == 1:
                cents += "0"
        else:
            dollars = money
            cents = "00"

        money = add_commas(dollars) + "." + cents
        return money

# Shopping Habits Score config — see docs/shopping_habits_score.md.
# Buckets are (max_days_exclusive, points); the last bucket uses float('inf').
SCORE_WEIGHTS = {
    'window_days': 90,
    'base_score': 50,
    'purchase_buckets': [
        (7, -8),
        (30, 0),
        (60, 2),
        (float('inf'), 4),
    ],
    'unhook_buckets': [
        (15, 0),
        (30, 2),
        (60, 3),
        (90, 4),
        (float('inf'), 5),
    ],
    # (min_ratio_inclusive, bonus). Iterated highest-min first.
    'ratio_bonus': [
        (1.0, 10),
        (0.5, 5),
        (0.25, 0),
        (0.0, -5),
    ],
}

# (min_score_inclusive, label). Iterated highest-min first.
SCORE_TIERS = [
    (80, 'Mindful Shopper'),
    (60, 'Getting There'),
    (40, 'Mixed Habits'),
    (0, 'Impulse-prone'),
]


def _strip_tz(dt):
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _bucket_points(days, buckets):
    for max_days, points in buckets:
        if days < max_days:
            return points
    return 0


def _wait_days(item, decision_date):
    if item.wish_period is not None:
        return max(item.wish_period.days, 0)
    item_date = _strip_tz(item.date)
    decision_date = _strip_tz(decision_date)
    if item_date is not None and decision_date is not None:
        return max((decision_date - item_date).days, 0)
    return 0


def compute_shopping_habits_score(user):
    """Returns a dict: {has_data, score, tier, purchases, unhooks}.

    Score reflects the last `window_days` of purchase + unhook decisions.
    `has_data` is False when there were zero decisions in the window — the
    UI shows a placeholder rather than a misleading mid-pack 50.
    """
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=SCORE_WEIGHTS['window_days'])
    purchase_count = 0
    unhook_count = 0
    total_points = 0
    for item in user.wishitems:
        if item.purchased and not item.unhooked:
            decision_date = _strip_tz(item.purchase_date)
            if decision_date is not None and decision_date >= cutoff:
                days = _wait_days(item, decision_date)
                total_points += _bucket_points(days, SCORE_WEIGHTS['purchase_buckets'])
                purchase_count += 1
        elif item.unhooked:
            decision_date = _strip_tz(item.unhooked_date)
            if decision_date is not None and decision_date >= cutoff:
                days = _wait_days(item, decision_date)
                total_points += _bucket_points(days, SCORE_WEIGHTS['unhook_buckets'])
                unhook_count += 1

    if purchase_count + unhook_count == 0:
        return {'has_data': False, 'score': None, 'tier': None,
                'purchases': 0, 'unhooks': 0}

    if purchase_count == 0:
        ratio_bonus = SCORE_WEIGHTS['ratio_bonus'][0][1]
    else:
        ratio = unhook_count / purchase_count
        ratio_bonus = next(b for r, b in SCORE_WEIGHTS['ratio_bonus'] if ratio >= r)

    raw = SCORE_WEIGHTS['base_score'] + total_points + ratio_bonus
    score = max(0, min(100, raw))
    tier = next(label for threshold, label in SCORE_TIERS if score >= threshold)
    return {'has_data': True, 'score': score, 'tier': tier,
            'purchases': purchase_count, 'unhooks': unhook_count}


COLOR_SCHEME = [
        "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
        "#FFB3B3", "#FFCCB3", "#FFFFB3", "#B3FFB3", "#B3FFFF",
        "#FFB3D9", "#FFB3FF", "#D9B3FF", "#B3B3FF", "#B3D9FF",
        "#B3FFFF", "#B3FFD9", "#B3FFB3", "#D9FFB3", "#FFFFB3",
        "#FFCCB3", "#FFB3B3", "#FFB3CC", "#FFB3E6", "#FFB3FF",
        "#E6B3FF", "#CCB3FF", "#B3B3FF", "#B3CCFF", "#B3E6FF",
        "#B3FFFF", "#B3FFE6", "#B3FFCC", "#B3FFB3", "#CCFFB3",
        "#E6FFB3", "#FFFFB3", "#FFCCB3", "#FFB3B3", "#FFB3CC",
        "#FFB3E6", "#FFB3FF", "#E6B3FF", "#CCB3FF", "#B3B3FF",
        "#B3CCFF", "#B3E6FF", "#B3FFFF", "#B3FFE6", "#B3FFCC"
        ]

def _summarize_decisions(items, window_start, window_end):
    """Aggregates purchases and unhooks decided within [window_start, window_end).
    Returns counts, totals, and avg wait days. Used by the hero card to compute
    both the current and prior window so we can show period-over-period deltas."""
    saved = 0.0
    unhooks = 0
    purchased = 0.0
    purchases = 0
    purchase_wait_days = 0
    for item in items:
        if item.purchased and not item.unhooked:
            pdate = _strip_tz(item.purchase_date)
            if pdate is not None and window_start <= pdate < window_end:
                purchased += item.taxed_price or 0
                purchases += 1
                purchase_wait_days += _wait_days(item, pdate)
        elif item.unhooked:
            udate = _strip_tz(item.unhooked_date)
            if udate is not None and window_start <= udate < window_end:
                saved += item.price or 0
                unhooks += 1
    avg_buy_wait = round(purchase_wait_days / purchases) if purchases > 0 else None
    return {
        'saved': round(saved, 2),
        'unhooks': unhooks,
        'purchased': round(purchased, 2),
        'purchases': purchases,
        'avg_buy_wait_days': avg_buy_wait,
    }


def _delta(current, prior, good_direction):
    """Builds a delta dict for hero tiles. `good_direction` is 'up' or 'down' —
    whichever direction should render green. Returns None if either side is
    None (so the template can hide the indicator on first-month users)."""
    if current is None or prior is None:
        return None
    diff = current - prior
    if diff > 0:
        arrow = 'up'
        tone = 'good' if good_direction == 'up' else 'bad'
    elif diff < 0:
        arrow = 'down'
        tone = 'good' if good_direction == 'down' else 'bad'
    else:
        arrow = 'flat'
        tone = 'flat'
    return {'arrow': arrow, 'tone': tone, 'value': abs(diff)}


@reports.route('/', methods=['GET', 'POST'])  # url (homepage). run function when opening root.
@login_required
def home():

    if request.method == 'POST' or request.method == 'GET':
        # get current time
        current_time = datetime.datetime.now() # Get the current time
        ten_days = datetime.timedelta(days=10)
        last_purchase_date = (
            db.session.query(db.func.max(WishItem.purchase_date))
            .filter_by(user_id=current_user.id, purchased=True)
            .scalar()
        )
        report_end = datetime.datetime.now()
        report_start = datetime.datetime(report_end.year, report_end.month, 1, 0, 0, 0) # 1st day of the month
        if report_end.day == report_start.day:
            # if the report_end is the first day of the month, then we need to go back to the first day of yesterday's month
            yesterday = report_end - datetime.timedelta(days=1)
            report_start = datetime.datetime(yesterday.year, yesterday.month, 1, 0, 0, 0) # 1st day of yesterday's month

        # type(current_user.wishitems) is <class 'sqlalchemy.orm.collections.InstrumentedList'>
    # Convert InstrumentedList to a list of dictionaries
    purchased_wishitems = [item.to_dict() for item in current_user.wishitems if item.purchased and item.purchase_date is not None]
    spenditure = {}

    for purchased_item in purchased_wishitems:
        purchase_date = purchased_item['purchase_date'][:10]
        if purchase_date in spenditure:
            spenditure[purchase_date] += purchased_item['price']
        else:
            spenditure[purchase_date] = purchased_item['price']
    spenditure = {date: format_money(spend) for date, spend in spenditure.items()}

    unhooked_wishitems = [item.to_dict() for item in current_user.wishitems if item.unhooked and item.unhooked_date is not None]
    saves = {}

    for unhooked_item in unhooked_wishitems:
        unhooked_date = unhooked_item['unhooked_date'][:10]
        if unhooked_date in saves:
            saves[unhooked_date] += unhooked_item['price']
        else:
            saves[unhooked_date] = unhooked_item['price']
    saves = {date: format_money(save) for date, save in saves.items()}


    shopping_score = compute_shopping_habits_score(current_user)

    # ── Stat-forward hero: time-of-day greeting + last-30-day totals ──
    # Hero stats are fixed to a rolling 30-day window (rather than the
    # current calendar month) so early-month views aren't dominated by
    # near-empty tiles. The page-wide date-range bar below the hero still
    # governs the stat cards / graphs / pies independently.
    hour = current_time.hour
    if 5 <= hour < 12:
        greeting_phrase = "Good morning"
    elif 12 <= hour < 17:
        greeting_phrase = "Good afternoon"
    else:
        greeting_phrase = "Good evening"

    HERO_WINDOW_DAYS = 30
    cur_end = current_time
    cur_start = cur_end - datetime.timedelta(days=HERO_WINDOW_DAYS)
    prior_end = cur_start
    prior_start = prior_end - datetime.timedelta(days=HERO_WINDOW_DAYS)

    cur = _summarize_decisions(current_user.wishitems, cur_start, cur_end)
    prior = _summarize_decisions(current_user.wishitems, prior_start, prior_end)

    # Delta directions: each tile's "good" direction (the one rendered green).
    # Saved/unhooks more = good, purchases more = bad, patience longer = good.
    hero_stats = {
        'greeting': greeting_phrase,
        'window_label': f'last {HERO_WINDOW_DAYS} days',
        'saved': cur['saved'],
        'unhooks': cur['unhooks'],
        'purchased': cur['purchased'],
        'purchases': cur['purchases'],
        'avg_buy_wait_days': cur['avg_buy_wait_days'],
        'unhooks_delta': _delta(cur['unhooks'], prior['unhooks'], good_direction='up'),
        'purchases_delta': _delta(cur['purchases'], prior['purchases'], good_direction='down'),
        'buy_wait_delta': _delta(cur['avg_buy_wait_days'], prior['avg_buy_wait_days'], good_direction='up'),
    }

    return render_template("home.html",
                user=current_user,
                current_time=current_time,
                ten_days=ten_days,
                last_purchase_date=last_purchase_date,
                default_report_start=report_start,
                default_report_end=report_end,
                spenditure=spenditure,
                saves=saves,
                shopping_score=shopping_score,
                hero_stats=hero_stats
                )  # return html when we got root

def create_figure(figure_type, figure_content, start_date=None, end_date=None):

    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)

    figure_types = {'wishlist': {'unhooked': False, 'purchased': False},
                    'unhooked_list': {'unhooked': True, 'purchased': False},
                    'purchased_list': {'unhooked': False, 'purchased': True}
                    }

    # Query the WishItem model to get the category breakdown for the current_user's wishlist, unhooked_list, or purchased_list
    unhooked = figure_types.get(figure_type).get('unhooked')
    purchased = figure_types.get(figure_type).get('purchased')
    wishitems = WishItem.query.filter_by(user_id=current_user.id, unhooked=unhooked, purchased=purchased).all()  # not unhooked and not purchased

    # Filter wishitems by date range if provided
    filtered_wishitems = []
    if start_date and end_date:
        for item in wishitems:
            # Use appropriate date field based on item type
            if figure_type == 'purchased_list':
                # For purchased items, use the purchase date
                item_date = item.purchase_date
            elif figure_type == 'unhooked_list':
                # For unhooked items, use the unhooked date
                item_date = item.unhooked_date
            else:
                # For wishlist items, use the date when item was added to wishlist
                item_date = item.date

            if item_date and start_date <= item_date <= end_date:
                filtered_wishitems.append(item)
    else:
        # If no date range provided, include all items
        filtered_wishitems = wishitems

    if filtered_wishitems:
        wishitems = filtered_wishitems

    if figure_content == 'category':
        contents = [item.category for item in wishitems]
    elif figure_content == 'brand':
        contents = [item.brand for item in wishitems]
    else:
        contents = [item.category for item in wishitems]  # TODO: UPDATE AND ADD MORE HERE

    # Count the occurrences of each category
    contents_counts = {}
    for content in contents:
        if content in contents_counts:
            contents_counts[content] += 1
        else:
            contents_counts[content] = 1

    # Sort by count (descending) and limit to top 10
    sorted_contents = sorted(contents_counts.items(), key=lambda x: x[1], reverse=True)

    if len(sorted_contents) > 10:
        # Take top 10 and group the rest into "Others"
        top_10 = sorted_contents[:10]
        others_count = sum(count for _, count in sorted_contents[10:])

        # Prepare data for the pie chart with top 10 + Others
        labels = [item[0] for item in top_10] + ['Others']
        sizes = [item[1] for item in top_10] + [others_count]
    else:
        # If 10 or fewer, use all
        labels = [item[0] for item in sorted_contents]
        sizes = [item[1] for item in sorted_contents]

    # Define a default pastel color scheme
    colors = random.sample(COLOR_SCHEME, len(labels))

    # Generate the pie chart
    axis.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    axis.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    return fig

@reports.route('/wishlist_category.png')
def plot_category_png():
    fig = create_figure('wishlist', 'category')
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype='image/png')


@reports.route('/wishlist_brand.png')
def plot_brand_png():
    fig = create_figure('wishlist', 'brand')
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype='image/png')


@reports.route('/purchased_category.png')
def plot_purchased_category_png():
    fig = create_figure('purchased_list', 'category')
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype='image/png')


@reports.route('/purchased_brand.png')
def plot_purchased_brand_png():
    fig = create_figure('purchased_list', 'brand')
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype='image/png')


@reports.route('/generate-report', methods=['POST'])
@login_required
def generate_report():
    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'Start date and end date are required'}), 400

    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Calculate total purchase amount and purchased count for the date range
    total_purchase_amount = 0
    purchased_count = 0
    purchased_items = WishItem.query.filter_by(
        user_id=current_user.id,
        purchased=True,
        unhooked=False
    ).all()

    for item in purchased_items:
        if item.purchase_date and start_date <= item.purchase_date <= end_date:
            total_purchase_amount += item.taxed_price
            purchased_count += 1

    # Calculate total saved amount and unhooked item count for the date range
    total_saved_amount = 0
    unhooked_count = 0
    unhooked_items = WishItem.query.filter_by(
        user_id=current_user.id,
        unhooked=True
    ).all()
    for item in unhooked_items:
        if item.unhooked_date and start_date <= item.unhooked_date <= end_date:
            total_saved_amount += item.price or 0
            unhooked_count += 1

    # Count wishlist items added in the date range (any item with a creation date in range)
    wishlist_added_count = 0
    all_user_items = WishItem.query.filter_by(user_id=current_user.id).all()
    for item in all_user_items:
        if item.date and start_date <= item.date <= end_date:
            wishlist_added_count += 1

    # Generate new pie charts with date filtering
    fig_category = create_figure('wishlist', 'category', start_date, end_date)
    fig_brand = create_figure('wishlist', 'brand', start_date, end_date)
    fig_purchased_category = create_figure('purchased_list', 'category', start_date, end_date)
    fig_purchased_brand = create_figure('purchased_list', 'brand', start_date, end_date)

    # Convert figures to base64 for sending to frontend
    import base64

    def figure_to_base64(fig):
        output = io.BytesIO()
        FigureCanvas(fig).print_png(output)
        output.seek(0)
        return base64.b64encode(output.getvalue()).decode('utf-8')

    category_chart = figure_to_base64(fig_category)
    brand_chart = figure_to_base64(fig_brand)
    purchased_category_chart = figure_to_base64(fig_purchased_category)
    purchased_brand_chart = figure_to_base64(fig_purchased_brand)

    return jsonify({
        'total_purchase_amount': round(total_purchase_amount, 2),
        'total_saved_amount': round(total_saved_amount, 2),
        'unhooked_count': unhooked_count,
        'purchased_count': purchased_count,
        'wishlist_added_count': wishlist_added_count,
        'category_chart': category_chart,
        'brand_chart': brand_chart,
        'purchased_category_chart': purchased_category_chart,
        'purchased_brand_chart': purchased_brand_chart,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })

