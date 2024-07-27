from website import create_app, format_time
import datetime

app = create_app()

# Register the function as a template filter
app.template_filter('format_time')(format_time)
            
if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], port=app.config['FLASK_RUN_PORT']) 
