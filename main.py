from website import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)  # automatically rerun webserver after change. set to False when in production
