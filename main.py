from website import create_app
import datetime

app = create_app()

@app.template_filter('format_time')
def format_time(timedelta: datetime.timedelta):
    if timedelta.days > 0:
        leftover_seconds = timedelta - datetime.timedelta(days=timedelta.days)
        leftover_hours = leftover_seconds // 3600
        return f"{timedelta.days} days ago"
    
    elif timedelta.seconds > 3600:
        return f"{timedelta.seconds // 3600} hrs ago"
    else: 
        return f"{timedelta.seconds} secs ago"
            
if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], port=app.config['FLASK_RUN_PORT']) 
