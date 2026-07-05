from website import create_app, debug, Format # format_time, format_tag
from website.ledger import format_cents

app = create_app()

# integer cents -> "$1,234.56" (used by the purchased-list savings badges)
app.template_filter('format_cents')(format_cents)

# Register the function as a template filter
app.template_filter('format_time')(Format().format_time)
app.template_filter('format_tag')(Format().format_tag)
app.template_filter('format_description')(Format().format_description)
app.template_filter('format_last_purchase_date')(Format().format_last_purchase_date)
app.template_filter('format_last_purchase_date')(Format().format_last_purchase_date)
app.template_filter('format_money')(Format().format_money)
app.template_filter('format_report_date')(Format().format_report_date)
app.template_filter('format_datetime')(Format().format_datetime)
app.template_filter('debug')(debug)

            
if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], port=app.config['FLASK_RUN_PORT']) 
