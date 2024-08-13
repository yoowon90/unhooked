from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, Response
from flask_login import login_required, current_user
from .models import Note, WishItem
from . import db
import json
import os
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import datetime
import io
import requests
from bs4 import BeautifulSoup

# store standard routes (url defined), anything that users can navitage to.

views = Blueprint('views', __name__)  # define blueprint
TAX = {'11217': 0.0875}
# manhattan, brooklyn, queens, bronx, staten island
NYC = ['10001', '10011', '11019', '10023', '10128',
                '11201', '11211', '11217', '11231', '11238',
                '11101', '11354', '11375', '11432', '11691', 
                '10451', '10452', '10463', '10467', '10469',
                '10301', '10304', '10306', '10314']


@views.route('/delete-item', methods=['POST'])
def delete_item():  
    wishitem = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    wishitemId = wishitem['wishItemId']
    print(f"wishitemId: {wishitemId}")
    wishitem = WishItem.query.get(wishitemId)
    if wishitem:
        print("there is a wishitem")
        if wishitem.user_id == current_user.id:
            db.session.delete(wishitem)
            db.session.commit()
    print(f"jsonify: {jsonify({})}")
    return jsonify({})

# notes
@views.route('/delete-note', methods=['POST'])
def delete_note():  
    note = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    noteId = note['noteId']
    print(f"noteId: {noteId}")
    note = Note.query.get(noteId)
    if note:
        print("there is a note")
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()
    print(f"jsonify: {jsonify({})}")
    return jsonify({})

# test
@views.route('/test', methods=['GET', 'POST'])
def test():
    if request.method == 'POST': 
        wishitem = request.form.get('wishitem')  #Gets the wish item from the HTML 

        if len(wishitem) < 1:
            flash('Item is too short!', category='error') 
        else:
            new_item = WishItem(data=wishitem, user_id=current_user.id)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("test.html", user=current_user)  # return html when we got root

def dir_last_updated(folder):
    # https://stackoverflow.com/questions/41144565/flask-does-not-see-change-in-js-file
    return str(max(os.path.getmtime(os.path.join(root_path, f))
                   for root_path, dirs, files in os.walk(folder)
                   for f in files))

# wishlist
@views.route('/my-wishlist', methods=['GET', 'POST'])
def wishlist():
    if request.method == 'POST':         
        # allow flexibility with price
        raw_price = request.form.get('price')
        if raw_price.startswith('$'):
            raw_price = raw_price[1:].strip().replace(',', '')
        wish_item_price = float(raw_price) 

        # format name
        raw_name = request.form.get('name')
        raw_names = raw_name.split(' ')
        wish_item_name = ' '.join([raw_name.capitalize() for raw_name in raw_names])

        # grab other fields
        wish_item_delivery_fee = float(request.form.get('delivery-fee')) if request.form.get('delivery-fee') != "" else 0
        wish_item_category = request.form.get('category')
        wish_item_tag = request.form.get('tag')
        wish_item_brand = request.form.get('brand')
        wish_item_link = request.form.get('link')
        wish_item_description = request.form.get('description')
        if wish_item_price < 0:
            flash('Price cannot be below zero!', category='error')
        if wish_item_delivery_fee is not None and wish_item_delivery_fee < 0:
           flash('Delivery fee cannot be below zero!', category='error')

        if len(wish_item_name) < 1:
            flash('Item is too short!', category='error')
        if len(wish_item_category) < 1:
            flash('Speciy a category!', category='error')
        if len(wish_item_brand) < 1:
            flash('Specify a brand!', category='error')
        if (len(wish_item_link) < 5):
            flash('Invalid link!', category='error')
        
        else:
            # print(f"delivery_fee: {wish_item_delivery_fee}")
            # extra tax rules for nyc
            zipcode = current_user.zipcode
            tax = 0 if (zipcode in NYC and (wish_item_price < 110.00)) else TAX.get(zipcode, 0)
            taxed_price = wish_item_price*(1+tax)
            new_item = WishItem(user_id=current_user.id,
                                category=wish_item_category,
                                tag=wish_item_tag,
                                brand=wish_item_brand,
                                name=wish_item_name, 
                                price=wish_item_price,
                                taxed_price=taxed_price,
                                delivery_fee=wish_item_delivery_fee,
                                total_price=taxed_price + wish_item_delivery_fee,  # taxed price plus delivery fee
                                link=wish_item_link,
                                description=wish_item_description)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # create pie chart for brand
    elif request.method == 'GET': 
        data = dict()  # brand data
        for wishitem in current_user.wishitems:
            brand = wishitem.brand
            if brand in data.keys():
                data[brand] += 1
            else:
                data[brand] = 1
        
        labels = list(data.keys())
        values = list(data.values())
        # pie = plt.pie(values, labels=labels)
        #  plt.show()
        # pie.savefig('./website/img/brand-pie.png')
    
    # get current time
    current_time = datetime.datetime.utcnow() # Get the current time

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("wishlist.html", user=current_user, last_updated=dir_last_updated(r'./website/static'), current_time=current_time)  # return html when we got root


# wishlist
@views.route('/toggle-wishitem', methods=['POST'])
def toggle_wishitem():
    # sample data: {'wishItemId': 2, 'unhooked': False, 'purchased': False}
    wishItemId = json.loads(request.data)['wishItemId']
    unhooked =  json.loads(request.data)['unhooked']
    purchased = json.loads(request.data)['purchased']
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
            wishitem.unhooked = unhooked
            wishitem.purchased = purchased
            if unhooked and not purchased:
                flash("Item unhooked!", category='success')
            elif not unhooked and purchased:
                flash("Item purchased.", category='success')
            elif not unhooked and not purchased:
                flash("Item added to wish list", category='success')
            db.session.commit()
    return jsonify({})

@views.route('/add-wishitem-period', methods=['POST'])
def add_wishitem_period():
    wishItemId = json.loads(request.data)['wishItemId']
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
            current_time = datetime.datetime.utcnow()
            wish_timedelta = current_time - wishitem.date
            wishitem.wish_period = current_time - wishitem.date
            db.session.commit()
    return jsonify({})

# unhooked-list
@views.route('/unhooked-list', methods=['GET', 'POST'])
def unhooked_list():
    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("unhooked.html", user=current_user, last_updated=dir_last_updated(r'./website/static'))  # return html when we got root

# purchased-list
@views.route('/purchased-list', methods=['GET', 'POST'])
def purchased_list():
    # define wish_to_purchase_period
    return render_template("purchased.html", user=current_user, last_updated=dir_last_updated(r'./website/static'))  # return html when we got root


@views.route('/fetch-url-info', methods=['POST'])
def fetch_url_info():
    header = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36" ,
        'referer':'https://www.google.com/'
        }

    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    try:
        response = requests.get(url, headers=header)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        try:
            # Reformation
            # Find the script tag with type "application/ld+json"
            script_tag = soup.find('script', {'type': 'application/ld+json'})
            if script_tag:
                json_data = json.loads(script_tag.string)
                name = json_data.get('name')
                price = json_data.get('offers', {}).get('price')
                brand = json_data.get('brand', {}).get('name')
                print(name, price, brand)
                return jsonify({'success': True, 'name': name, 'price': price, 'brand': brand})
            else:
                return jsonify({'success': False, 'error': 'No JSON-LD script tag found'})
            
            # Sezane
            # Need to get around captcha

            # Rouje
    

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})