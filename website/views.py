from flask import Blueprint, render_template, request, flash, jsonify
from flask_login import login_required, current_user
from .models import Note, Wishlist
from . import db
import json

# store standard routes (url defined), anything that users can navitage to.

views = Blueprint('views', __name__)  # define blueprint


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


@views.route('/delete-note', methods=['POST'])
def delete_note():  
    note = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    noteId = note['noteId']
    note = Note.query.get(noteId)
    if note:
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()

    return jsonify({})


@views.route('/my-wishlist', methods=['GET', 'POST'])
def wishlist():
    if request.method == 'POST': 
        wishitem = request.form.get('wishitem')#Gets the wish item from the HTML 

        if len(wishitem) < 1:
            flash('Item is too short!', category='error') 
        else:
            new_item = Wishlist(data=wishlist, user_id=current_user.id)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("wishlist.html", user=current_user)  # return html when we got root

@views.route('/test', methods=['GET', 'POST'])
def test():
    if request.method == 'POST': 
        wishitem = request.form.get('wishitem')#Gets the wish item from the HTML 

        if len(wishitem) < 1:
            flash('Item is too short!', category='error') 
        else:
            new_item = Wishlist(data=wishlist, user_id=current_user.id)  #providing the schema for the note 
            db.session.add(new_item) #adding the note to the database 
            db.session.commit()
            flash('Item added to Wish List!', category='success')

    # render the template using name of template
    # now when go to '/', render home.html
    return render_template("test.html", user=current_user)  # return html when we got root