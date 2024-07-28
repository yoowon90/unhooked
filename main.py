from website import create_app, Format # format_time, format_tag
import datetime

app = create_app()

# Register the function as a template filter
app.template_filter('format_time')(Format().format_time)
app.template_filter('format_tag')(Format().format_tag)
            
if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], port=app.config['FLASK_RUN_PORT']) 
