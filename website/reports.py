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
# @login_required
def home():

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
                print(f"purchase_date: {purchase_date}, price: {purchased_item['price']}")
                spenditure[purchase_date] += purchased_item['price']
            else:
                spenditure[purchase_date] = purchased_item['price']
        spenditure = {date: format_money(spend) for date, spend in spenditure.items()}
        
        unhooked_wishitems = [item.to_dict() for item in current_user.wishitems if item.unhooked and item.unhooked_date is not None]
        print(f"unhooked_wishitems : {unhooked_wishitems}")
        saves = {}

        for unhooked_item in unhooked_wishitems:
            unhooked_date = unhooked_item['unhooked_date'][:10]
            if unhooked_date in saves:
                print(f"unhooked_date: {unhooked_date}, price: {unhooked_item['price']}")
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

def create_figure(figure_type, figure_content):
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)

    figure_types = {'wishlist': {'unhooked': False, 'purchased': False},
                    'unhooked_list': {'unhooked': True, 'purchased': False},
                    'purchased_list': {'unhooked': False, 'purchased': True}
                    }
    
    # if figure_content == 'category':
    # Query the WishItem model to get the category breakdown for the current_user's wishlist, unhooked_list, or purchased_list
    unhooked = figure_types.get(figure_type).get('unhooked')
    purchased = figure_types.get(figure_type).get('purchased')
    wishitems = WishItem.query.filter_by(user_id=current_user.id, unhooked=unhooked, purchased=purchased).all()  # not unhooked and not purchased
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
    
    # Prepare data for the pie chart
    labels = contents_counts.keys()
    sizes = contents_counts.values()

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

