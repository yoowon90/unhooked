from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import login_required, current_user
from .models import Note, WishItem
from . import db
import json
import os

# store standard routes (url defined), anything that users can navitage to.

views = Blueprint('views', __name__)  # define blueprint

# login
@views.route('/', methods=['GET', 'POST'])  # url (homepage). run function when opening root.
@login_required
def home():
    if request.method == 'POST': 
        # TODO: edit home.html to say "Welcome!" such as via <p> Welcome </p>
        note = request.form.get('note')#Gets the note from the HTML 

        if len(note) < 1:
            flash('Note is too short!', category='error') 
        else:
            new_note = Note(data=note, user_id=current_user.id)  #providing the schema for the note 
            db.session.add(new_note) #adding the note to the database 
            db.session.commit()
            flash('Note added!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("home.html", user=current_user)  # return html when we got root

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
        wish_item_name = request.form.get('name')#Gets the wish item from the HTML 
        wish_item_price = request.form.get('price')#Gets the wish item from the HTML  
        wish_item_category = request.form.get('category')#Gets the wish item from the HTML
        wish_item_brand = request.form.get('brand')
        wish_item_link = request.form.get('link')

        try:
            wish_item_price = float(wish_item_price)
            if wish_item_price < 0:
                flash('Price cannot be below zero!', category='error')
        except:
            flash('Price must be a number!', category='error')

        if len(wish_item_name) < 1:
            flash('Item is too short!', category='error')
        if len(wish_item_category) < 1:
            flash('Speciy a category!', category='error')
        if len(wish_item_brand) < 1:
            flash('Specify a brand!', category='error')
        if (len(wish_item_link) < 5) or not (('.com' in wish_item_link.lower()) 
                                       or ('.org' in wish_item_link.lower()) 
                                       or ('.net' in wish_item_link.lower())):
            flash('Invalid link!', category='error')
                    
        else:
            new_item = WishItem(user_id=current_user.id,
                                name=wish_item_name, 
                                price=wish_item_price,
                                category=wish_item_category,
                                brand=wish_item_brand,
                                link=wish_item_link)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("wishlist.html", user=current_user, last_updated=dir_last_updated(r'./website/static'))  # return html when we got root


@views.route('/add-wishitem', methods=['GET', 'POST'])
def add_wishitem():
    if request.method == 'POST': 
        wish_item_name = request.form.get('name')#Gets the wish item from the HTML 
        wish_item_price = request.form.get('price')#Gets the wish item from the HTML  
        wish_item_category = request.form.get('category')#Gets the wish item from the HTML
        wish_item_brand = request.form.get('brand')
        wish_item_link = request.form.get('link')

        if len(wish_item_name) < 1:
            flash('Item is too short!', category='error') 
        if float(wish_item_price) < 0:
            flash('Price cannot be below zero!', category='error')
        if len(wish_item_category) < 1:
            flash('Speciy a category!', category='error')
        if len(wish_item_brand) < 1:
            flash('Specify a brand!', category='error')
        if (len(wish_item_link) < 5) or not (('.com' in wish_item_link.lower()) 
                                    or ('.org' in wish_item_link.lower()) 
                                    or ('.net' in wish_item_link.lower())):
            flash('Invalid link!', category='error')
                    
        else:
            new_item = WishItem(user_id=current_user.id,
                                name=wish_item_name, 
                                price=wish_item_price,
                                category=wish_item_category,
                                brand=wish_item_brand,
                                link=wish_item_link)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("wishitem.html", user=current_user)  # return html when we got root



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
            if not unhooked and purchased:
                flash("Item purchased.", category='success')  # lol
            db.session.commit()
    return jsonify({})


@views.route('/unhooked-list', methods=['GET', 'POST'])
def unhooked_list():
    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("unhooked.html", user=current_user, last_updated=dir_last_updated(r'./website/static'))  # return html when we got root

@views.route('/purchased-list', methods=['GET', 'POST'])
def purchased_list():
    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("purchased.html", user=current_user, last_updated=dir_last_updated(r'./website/static'))  # return html when we got root
