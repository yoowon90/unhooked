# Unhooked

Designed to help myself control impulsive shopping

# Features

Requirements
- Enable page to add rows of items I would like to buy and their prices
- Enable a page to move those wanted items to a column of items I eventually gave up
- Calculate how much money I potentially saved by not buying
- Enable a calendar to track how much i can buy in a certain period
- Enable functionality to move money I saved by giving up to my Savings account


# Below are instructions related to Flask application

## Setup & Installation

Make sure you have the latest version of Python installed.

```bash
git clone <repo-url>
```

```bash
pip install -r requirements.txt
```

## Running The App

For `production`:
```bash
FLASK_ENV=production python main.py
```

For `development`:
```bash
FLASK_ENV=development python main.py
```
## Viewing The App

For `production`: Go to `http://127.0.0.1:5000`

For `development`: Go to `http://127.0.0.1:5001`

## To run production code in background

`# sudo nohup FLASK_ENV=production python main.py > log.txt 2>&1`

## To initialize migrations

For `production`: `FLASK_ENV=production flask db init --directory=migrations_prod --multidb`

For `development`: `FLASK_ENV=development flask db init --directory=migrations_dev`


## Generate and Apply Migrations
For `production`:
```bash
export FLASK_APP=website
FLASK_ENV=production flask db migrate -m "Description of changes" --directory=migrations_prod
FLASK_ENV=production flask db upgrade --directory=migrations_prod
```

For `development`:
```bash
export FLASK_APP=website
FLASK_ENV=development flask db migrate -m "Description of changes" --directory=migrations_dev
FLASK_ENV=development flask db upgrade --directory=migrations_dev
```

