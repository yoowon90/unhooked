""" Description: This file contains the routes for the website."""
# Imports
import re
import os
import datetime
import json
from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import current_user, login_required
from .models import Note, WishItem, normalize_category, clean_text
from . import db
from . import ledger
from . import reconciliation
from . import transfers
from .ledger import LedgerError
from .purchases import (mark_purchased, needs_savings_prompt,
                        record_savings_decision, savings_feature_enabled)
from .url_extraction import scrape_item
from .tax import taxed_price

# store standard routes (url defined), anything that users can navitage to.

views = Blueprint('views', __name__)  # define blueprint


@views.route('/delete-item', methods=['POST'])
@login_required
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
@login_required
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

def dir_last_updated(folder):
    # https://stackoverflow.com/questions/41144565/flask-does-not-see-change-in-js-file
    return str(max(os.path.getmtime(os.path.join(root_path, f))
                   for root_path, dirs, files in os.walk(folder)
                   for f in files))

# wishlist
@views.route('/my-wishlist', methods=['GET', 'POST'])
@login_required
def wishlist():
    if request.method == 'POST':
        # allow flexibility with price
        raw_price = request.form.get('price')
        if re.search(r'[A-Za-z]\s*$', raw_price):  # ends with an alphabet (optionally followed by spaces)
            raw_price = re.sub(r'[A-Za-z]+\s*$', '', raw_price)
        if raw_price.startswith('$'):
            raw_price = raw_price[1:].strip()
        raw_price = raw_price.replace(',', '')  # replace comma with period
        try:
            wish_item_price = float(raw_price)
        except Exception as e:
            flash('Price must be number!', category='error')
            print(f'Error: {e}')

        # format name
        raw_name = clean_text(request.form.get('name'))
        raw_names = raw_name.split(' ')
        wish_item_name = ' '.join([raw_name.capitalize() for raw_name in raw_names])

        # grab other fields
        wish_item_delivery_fee = float(request.form.get('delivery-fee')) if request.form.get('delivery-fee') != "" else 0
        wish_item_category = normalize_category(request.form.get('category'))
        wish_item_tag = clean_text(request.form.get('tag'))
        wish_item_brand = clean_text(request.form.get('brand'))
        wish_item_link = request.form.get('link')
        wish_item_description = clean_text(request.form.get('description').replace("<br>", ". ").replace("<br/>", ". "))
        wish_item_image_url = request.form.get('image_url', None)  # Get image_url from form
        if wish_item_price < 0:
            flash('Price cannot be below zero!', category='error')
        elif wish_item_delivery_fee is not None and wish_item_delivery_fee < 0:
           flash('Delivery fee cannot be below zero!', category='error')

        elif len(wish_item_name) < 1:
            flash('Item is too short!', category='error')
        elif len(wish_item_category) < 1:
            flash('Specify a category!', category='error')
        elif len(wish_item_brand) < 1:
            flash('Specify a brand!', category='error')
        elif (len(wish_item_link) < 5):
            flash('Invalid link!', category='error')

        else:
            # print(f"delivery_fee: {wish_item_delivery_fee}")
            taxed_item_price = taxed_price(current_user.zipcode, wish_item_price)

            # Server-side image fallback: run Google search only if no image_url provided
            if not wish_item_image_url:
                try:
                    fallback_image = ItemDetails.google_search_image_fallback(
                        wish_item_brand,
                        wish_item_name,
                        wish_item_description,
                        wish_item_price,
                    )
                    if fallback_image:
                        wish_item_image_url = fallback_image
                except Exception as e:
                    print(f"Error during server-side image fallback: {e}")

            new_item = WishItem(user_id=current_user.id,
                                category=wish_item_category,
                                tag=wish_item_tag,
                                brand=wish_item_brand,
                                name=wish_item_name,
                                price=wish_item_price,
                                taxed_price=taxed_item_price,
                                delivery_fee=wish_item_delivery_fee,
                                total_price=taxed_item_price + wish_item_delivery_fee,  # taxed price plus delivery fee
                                link=wish_item_link,
                                description=wish_item_description,
                                image_url=wish_item_image_url,
                                wish_period=datetime.timedelta(seconds=0),
                                date=datetime.datetime.now())  # providing the schema for the note
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


    # get current time
    current_time = datetime.datetime.now() # Get the current time

    # get all unique tags in wishlist
    wishlist_tags = set()
    for wishitem in current_user.wishitems:
        if not wishitem.purchased and not wishitem.unhooked:
            if not wishitem.tag == "" and wishitem.tag is not None:  # if not tag unknown
                wishlist_tags.add(wishitem.tag)
    tags = list(wishlist_tags)

    # get all unique categories in wishlist
    wishlist_cats = set()
    for wishitem in current_user.wishitems:
        if not wishitem.purchased and not wishitem.unhooked:
            if not wishitem.category == "" and wishitem.category is not None:  # if not category unknown
                wishlist_cats.add(wishitem.category)
    categories = list(wishlist_cats)
    categories.sort()

    # get all unique brands in wishlist
    wishlist_brands = set()
    for wishitem in current_user.wishitems:
        if not wishitem.purchased and not wishitem.unhooked:
            if not wishitem.brand == "" and wishitem.brand is not None:  # if not category unknown
                wishlist_brands.add(wishitem.brand)
    brands = list(wishlist_brands)
    brands.sort()

    # render the template using name of template
    # now when go to '/', render unhooked.html

    wishitems_sorted = WishItem.query.filter_by(user_id=current_user.id, unhooked=False, purchased=False).order_by(WishItem.date.desc()).all()

    return render_template("wishlist.html",
                           user=current_user,
                           last_updated=dir_last_updated(r'./website/static'),
                           current_time=current_time,
                           tags=tags,
                           categories=categories,
                           brands=brands,
                           wishitems=wishitems_sorted)  # return html when we got root


# wishlist
@views.route('/toggle-wishitem', methods=['POST'])
@login_required
def toggle_wishitem():
    # sample data: {'wishItemId': 2, 'unhooked': False, 'purchased': False}
    wishItemId = json.loads(request.data)['wishItemId']
    unhooked =  json.loads(request.data)['unhooked']
    purchased = json.loads(request.data)['purchased']
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
            if not unhooked and purchased:
                # Shared service (same path as the mobile API) stamps
                # purchase_date, wish_period, and last_purchase_date.
                mark_purchased(wishitem, current_user)
                flash("Item purchased.", category='success')
                # Send the browser to the savings interstitial instead of nextUrl.
                if needs_savings_prompt(wishitem):
                    return jsonify({'redirect': url_for('views.savings_prompt', item_id=wishitem.id)})
                return jsonify({})
            wishitem.unhooked = unhooked
            wishitem.purchased = purchased
            if unhooked and not purchased:
                print("Unhooking.. new wishitem unhooked date is {}".format(datetime.datetime.now()))
                wishitem.unhooked_date = datetime.datetime.now()
                if wishitem.date:
                    wishitem.wish_period = wishitem.unhooked_date - wishitem.date
                flash("Item unhooked!", category='success')
            elif not unhooked and not purchased:  # e.g. re-adding to wishlist
                # wishitem.date = datetime.datetime.now() # update date
                flash("Item added to wish list", category='success')
            db.session.commit()
    return jsonify({})


# ── Savings interstitial (post-purchase) ──────────────────────────────────────

@views.route('/purchase-savings-prompt/<int:item_id>', methods=['GET'])
@login_required
def savings_prompt(item_id):
    """Middle page after marking an item purchased: "Move $X to savings?"."""
    wishitem = WishItem.query.get(item_id)
    if not wishitem or wishitem.user_id != current_user.id:
        return redirect(url_for('views.purchased_list'))
    if not needs_savings_prompt(wishitem):  # not purchased, or already decided
        return redirect(url_for('views.purchased_list'))
    prefill = '%.2f' % wishitem.price if wishitem.price and wishitem.price > 0 else ''
    return render_template('savings_prompt.html', user=current_user,
                           wishitem=wishitem, prefill_amount=prefill, error=None)


@views.route('/purchase-savings-decision/<int:item_id>', methods=['POST'])
@login_required
def savings_decision(item_id):
    wishitem = WishItem.query.get(item_id)
    if not wishitem or wishitem.user_id != current_user.id:
        return redirect(url_for('views.purchased_list'))
    if not needs_savings_prompt(wishitem):
        return redirect(url_for('views.purchased_list'))

    decision = request.form.get('decision')
    if decision == 'declined':
        record_savings_decision(wishitem, current_user, 'declined')
        flash('Okay — not this time.', category='success')
        return redirect(url_for('views.purchased_list'))

    # decision == 'moved': validate the (editable) amount server-side too.
    raw_amount = (request.form.get('amount') or '').replace('$', '').replace(',', '').strip()
    try:
        amount_cents = ledger.dollars_to_cents(raw_amount)
    except LedgerError:
        amount_cents = None
    if amount_cents is None or amount_cents <= 0:
        return render_template('savings_prompt.html', user=current_user,
                               wishitem=wishitem, prefill_amount=raw_amount,
                               error='Please enter an amount greater than $0.'), 400

    record_savings_decision(wishitem, current_user, 'moved', amount_cents=amount_cents)

    # Originate the real (sandbox) ACH debit. Rail failure never undoes the
    # ledger posting — the intent stands and origination can be retried.
    result = transfers.originate_savings_transfer(current_user, wishitem.savings_txn)
    if result['originated']:
        flash(f'{ledger.format_cents(amount_cents)} on its way to savings! 💰 (ACH transfer originated)', category='success')
    elif result['reason'] == 'not_connected':
        flash(f'{ledger.format_cents(amount_cents)} recorded in your ledger. '
              'Connect a bank in Settings to originate real transfers.', category='success')
    else:
        flash(f'{ledger.format_cents(amount_cents)} recorded in your ledger, but the '
              f'bank transfer could not be originated: {result["detail"]}', category='error')
    return redirect(url_for('views.purchased_list'))

@views.route('/add-wishitem-period', methods=['POST'])
@login_required
def add_wishitem_period():
    wishItemId = json.loads(request.data)['wishItemId']
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
            current_time = datetime.datetime.now()
            wishitem.wish_period = current_time - wishitem.date
            db.session.commit()
    return jsonify({})

@views.route('/toggle-favorite-wishitem', methods=['POST'])
@login_required
def toggle_favorite_wishitem():
    print("wishitem click detected and now toggling")
    wishItemId = json.loads(request.data)['wishItemId']
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
            wishitem.favorited = not wishitem.favorited
            db.session.commit()
    return jsonify({})

@views.route('/save-table', methods=['POST'])
@login_required
def save_table():
    data = json.loads(request.data)
    wishItemId = data['wishItemId']

    # Process the data (e.g., save to the database)
    wishitem = WishItem.query.get(wishItemId)
    if wishitem:
        if wishitem.user_id == current_user.id:
                        # Check if this is a price update
            if 'field' in data and data['field'] == 'price':
                try:
                    new_price = float(data['value'])
                    if new_price < 0:
                        return jsonify({'error': 'Price cannot be negative'}), 400

                                        # Update the pre-tax price field (this is what the user actually entered)
                    wishitem.price = new_price

                    # Recalculate taxed price using the shared tax helper, which honors
                    # the NYC clothing exemption (<$110) and per-zipcode rules.
                    wishitem.taxed_price = taxed_price(current_user.zipcode, new_price)

                    # Update total price (including delivery fee if any)
                    if wishitem.delivery_fee:
                        wishitem.total_price = wishitem.taxed_price + wishitem.delivery_fee
                    else:
                        wishitem.total_price = wishitem.taxed_price

                    db.session.commit()
                    print(f"Price updated for wishitem {wishItemId}: pre-tax={new_price}, taxed={wishitem.taxed_price}")
                    return jsonify({'success': True, 'message': 'Price updated successfully'})
                except (ValueError, TypeError):
                    return jsonify({'error': 'Invalid price value'}), 400
            else:
                # Handle other field updates (existing logic)
                brand = clean_text(data['Brand'].split('\n')[0])
                category_and_tag = data['Category_Tag']
                category = normalize_category(category_and_tag.split('#')[0])
                tag = clean_text(category_and_tag.split('#')[1]) if '#' in category_and_tag else None
                name_and_desc = data['Name_Description']
                name = clean_text(name_and_desc.split('\n')[0])
                desc = clean_text(name_and_desc.split('\n')[1]) if '\n' in name_and_desc else None
                wishitem.brand = brand
                wishitem.category = category
                wishitem.tag = tag
                wishitem.name = name
                wishitem.description = desc
                db.session.commit()

    print(f"jsonify: {jsonify({})}")
    return jsonify({})

# unhooked-list
@views.route('/unhooked-list', methods=['GET', 'POST'])
@login_required
def unhooked_list():
    # render the template using name of template
    # now when go to '/', render unhooked.html
    # get all unique categories in unhooked list
    unhooked_cats = set()
    # get all unique brands in unhooked list
    unhooked_brands = set()
    for wishitem in current_user.wishitems:
        if not wishitem.purchased and wishitem.unhooked:
            if not wishitem.category == "" and wishitem.category is not None:  # if not category unknown
                unhooked_cats.add(wishitem.category)
            if not wishitem.brand == "" and wishitem.brand is not None:  # if not brand unknown
                unhooked_brands.add(wishitem.brand)

    unhooked_cats = list(unhooked_cats)
    unhooked_brands = list(unhooked_brands)
    unhooked_cats.sort()
    unhooked_brands.sort()

    # sort user's wishitems by unhooked date
    unhooked_items = WishItem.query.filter_by(user_id=current_user.id, unhooked=True, purchased=False).order_by(WishItem.unhooked_date.desc().nullslast()).all()

    return render_template("unhooked.html", user=current_user, last_updated=dir_last_updated(r'./website/static'),
                           unhooked_cats=unhooked_cats, unhooked_brands=unhooked_brands, unhooked_items=unhooked_items)  # return html when we got root

# purchased-list
@views.route('/purchased-list', methods=['GET', 'POST'])
@login_required
def purchased_list():
    # Opportunistic reconciliation: if any transfer we originated is still
    # pending, drain Plaid's event feed so the savings badges show current
    # rail status. Guarded (no Plaid call when nothing is in flight) and
    # non-fatal — a Plaid outage must never break this page.
    try:
        if savings_feature_enabled() and reconciliation.should_sync():
            reconciliation.reconcile_transfers()
    except Exception as e:
        print(f'Transfer reconciliation skipped: {e}')

    # get all unique categories in purchased list
    purchased_cats = set()
    # get all unique brands in purchased list
    purchased_brands = set()
    for wishitem in current_user.wishitems:
        if not wishitem.unhooked and wishitem.purchased:
            if not wishitem.category == "" and wishitem.category is not None:  # if not category unknown
                purchased_cats.add(wishitem.category)
            if not wishitem.brand == "" and wishitem.brand is not None:  # if not brand unknown
                purchased_brands.add(wishitem.brand)

    purchased_cats = list(purchased_cats)
    purchased_brands = list(purchased_brands)
    purchased_cats.sort()
    purchased_brands.sort()

    # define wish_to_purchase_period
    purchased_items = WishItem.query.filter_by(user_id=current_user.id, unhooked=False, purchased=True).order_by(WishItem.purchase_date.desc().nullslast()).all()

    return render_template("purchased.html", user=current_user, last_updated=dir_last_updated(r'./website/static'),
                           purchased_cats=purchased_cats, purchased_brands=purchased_brands, purchased_items=purchased_items)  # return html when we got root


@views.route('/fetch-url-info', methods=['POST'])
@login_required
def fetch_url_info():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    try:
        item_data_dict = scrape_item(url)
        item_data_dict['success'] = True
        return jsonify(item_data_dict)
    except Exception as e:
        print(f"Error fetching URL info: {e}")
        return jsonify({'success': True, 'name': None, 'price': None,
                        'brand': None, 'description': None,
                        'currency': None, 'image_url': None})


@views.route('/remove-wishitem-image', methods=['POST'])
@login_required
def remove_wishitem_image():
    """Clear the image_url for a wish item belonging to the current user."""
    try:
        data = json.loads(request.data)
        wishItemId = data.get('wishItemId')
        if not wishItemId:
            return jsonify({'success': False, 'error': 'Missing wishItemId'}), 400

        wishitem = WishItem.query.get(wishItemId)
        if not wishitem or wishitem.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        wishitem.image_url = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing image for wish item {locals().get('wishItemId', None)}: {e}")
        return jsonify({'success': False, 'error': 'Server error'}), 500
