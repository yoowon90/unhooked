# Unhooked

A personal shopping tracker for curbing impulsive purchases.

## Features

- **Wish List** — add items you want to buy with price, brand, category, and a scraped image
- **Unhooked List** — items you decided not to buy; tracks money saved
- **Purchase List** — items you did buy; tracks spend with NYC tax logic
- **Reports** — spending and savings summaries with charts
- **URL extraction** — paste a product URL and have brand/price/image auto-filled (Zara, Reformation, Bloomingdale's, and more)
- **Gmail Backfill** — connect Gmail via OAuth to scan order confirmation emails and import missed purchases with a Tinder-style review UI
- **REST API** — full `/api/v1/` endpoints for all wishlist, auth, and reports operations
- **React Native mobile app** — Expo-based iOS/Android app in `mobile/` backed by the same Flask API

## Setup & Installation

```bash
git clone <repo-url>
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Required keys (see `.env.example` for full instructions):
- `SECRET_KEY`, `JWT_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `ANTHROPIC_API_KEY` — from console.anthropic.com → API Keys
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — from Google Cloud Console (see ROADMAP.md)

## Running The App

```bash
FLASK_ENV=production python main.py   # port 5000, database_prod.db
FLASK_ENV=development python main.py  # port 5001, database_dev.db
```

## Viewing The App

- Production: `http://127.0.0.1:5000`
- Development: `http://127.0.0.1:5001`

## Database

**Live databases are never committed to git** — they contain user data and OAuth tokens.

`instance/database_template.db` is the only database file tracked in git. It contains the full schema with no user data, serving as a reference for the table/column structure. **Do not modify it directly** — schema changes happen via Alembic migrations and the template is regenerated from the model.

When you first run the app, SQLAlchemy creates `database_dev.db` or `database_prod.db` automatically from the models. Apply migrations after:

```bash
FLASK_ENV=development flask --app main db upgrade -d migrations_dev
FLASK_ENV=production flask --app main db upgrade -d migrations_prod
```

## To run production code in background

```bash
sudo nohup FLASK_ENV=production python main.py > log.txt 2>&1
```

## Generate and Apply Migrations

```bash
# dev
FLASK_ENV=development flask --app main db migrate -d migrations_dev -m "description"
FLASK_ENV=development flask --app main db upgrade -d migrations_dev

# prod
FLASK_ENV=production flask --app main db migrate -d migrations_prod -m "description"
FLASK_ENV=production flask --app main db upgrade -d migrations_prod
```

## Gmail Backfill setup

See `ROADMAP.md` for full Google Cloud Console setup steps. Short version:
1. Create a project at console.cloud.google.com, enable Gmail API
2. Set up OAuth consent screen (External, add yourself as test user, scopes: `gmail.readonly`)
3. Create OAuth 2.0 credentials (Web app), add redirect URI `http://localhost:5001/connectors/gmail/callback` (and/or `:5000` for prod)
4. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`
5. Restart app → Settings → Connectors → Connect Gmail

## Privacy

See `PRIVACY.md` for data collection and third-party sharing details.
