from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Response
from flask_login import login_required, current_user
from .models import WishItem
from . import db
import json
import os
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import datetime
import io
import random

reports = Blueprint('reports', __name__)  # define blueprint

@reports.route('/', methods=['GET', 'POST'])  # url (homepage). run function when opening root.
@login_required
def home():
    if request.method == 'POST' or request.method == 'GET': 

        return render_template("home.html", user=current_user)  # return html when we got root

def create_figure(figure_type, colors=None):
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    
    if figure_type == 'category':
        # Query the WishItem model to get the category breakdown for the current_user
        wishitems = WishItem.query.filter_by(user_id=current_user.id).all()
        categories = [item.category for item in wishitems]
        
        # Count the occurrences of each category
        category_counts = {}
        for category in categories:
            if category in category_counts:
                category_counts[category] += 1
            else:
                category_counts[category] = 1
        
        # Prepare data for the pie chart
        labels = category_counts.keys()
        sizes = category_counts.values()

        # Define a default pastel color scheme if no colors are provided
        if colors is None:
            colors = ['#ff9999','#66b3ff','#99ff99','#ffcc99','#c2c2f0','#ffb3e6',
                      '#c4e17f','#76d7c4','#ff6f61','#6b5b95','#88b04b','#f7cac9']
        
        # Generate the pie chart
        axis.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
        axis.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    else:
        xs = range(100)
        ys = [random.randint(1, 50) for x in xs]
        axis.plot(xs, ys)
    
    return fig

@reports.route('/category.png')
def plot_category_png():
    fig = create_figure('category')
    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    return Response(output.getvalue(), mimetype='image/png')
