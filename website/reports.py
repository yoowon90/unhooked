from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Response
from flask_login import login_required, current_user
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

@reports.route('/', methods=['GET', 'POST'])  # url (homepage). run function when opening root.
@login_required
def home():

    if request.method == 'POST' or request.method == 'GET':
        # get current time
        current_time = datetime.datetime.now() # Get the current time
        ten_days = datetime.timedelta(days=10)
        last_purchase_date = current_user.last_purchase_date
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


    return render_template("home.html",
                user=current_user,
                current_time=current_time,
                ten_days=ten_days,
                last_purchase_date=last_purchase_date,
                default_report_start=report_start,
                default_report_end=report_end,
                spenditure=spenditure,
                saves=saves
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

    # Calculate total purchase amount for the date range
    total_purchase_amount = 0
    purchased_items = WishItem.query.filter_by(
        user_id=current_user.id,
        purchased=True,
        unhooked=False
    ).all()

    for item in purchased_items:
        if item.purchase_date and start_date <= item.purchase_date <= end_date:
            total_purchase_amount += item.taxed_price

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
        'category_chart': category_chart,
        'brand_chart': brand_chart,
        'purchased_category_chart': purchased_category_chart,
        'purchased_brand_chart': purchased_brand_chart,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })

