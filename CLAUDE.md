# Unhooked — Project Guide

## What this is
A Flask web app for tracking personal online shopping habits. Users maintain a wishlist, mark items as purchased or "unhooked" (decided not to buy), and view spending/savings reports.

## Databases

- **Prod** runs on Supabase Postgres. Connection string lives in `.env` as `DATABASE_URL`. Backups are handled automatically by Supabase (daily snapshots on the free tier).
- **Dev** still uses local SQLite (`instance/database_dev.db`). Back up before risky git ops with `bash scripts/backup_db.sh`.
- The free Supabase project pauses after ~1 week of inactivity — the next request after a pause has a few seconds of cold-start delay.

## DB backup (dev only) — ask first

**Before starting the dev app**, ask the user: "Do you want to back up the dev database before starting?"
If yes, run:
```bash
bash scripts/backup_db.sh
```
Timestamped copies land in `backups/` (gitignored). Prod no longer needs this — Supabase handles it.

## How to run

```bash
FLASK_ENV=production python main.py   # port 5000, Supabase Postgres via DATABASE_URL
FLASK_ENV=development python main.py  # port 5001, database_dev.db (SQLite)
```

Environment variables are loaded from `.env` (never committed). Required keys: `SECRET_KEY`, `JWT_SECRET_KEY`, `FLASK_ENV`, `DATABASE_URL` (prod only).

## Project structure

```
main.py                  # entry point, registers Jinja template filters
config.py                # Config / ProductionConfig / DevelopmentConfig
website/
  __init__.py            # app factory, db + jwt init, blueprint registration
  models.py              # SQLAlchemy models: User, WishItem, Note
  views.py               # HTML routes: wishlist, unhooked-list, purchased-list
  auth.py                # HTML routes: login, logout, sign-up (Flask-Login)
  reports.py             # HTML routes: home dashboard, matplotlib pie charts
  url_extraction.py      # BeautifulSoup scrapers, one method per retailer
  api.py                 # (in progress) REST API under /api/v1/
  static/                # index.js, pattern images
  templates/             # Jinja2 HTML templates
instance/
  database_prod.db       # legacy SQLite, kept as a local snapshot only; prod now lives on Supabase
  database_dev.db        # dev SQLite
migrations_prod/         # Alembic migrations for prod db (Supabase Postgres)
migrations_dev/          # Alembic migrations for dev db (SQLite)
scripts/
  migrate_sqlite_to_postgres.py  # one-shot import used during the initial migration; safe to leave in tree
```

## Database migrations

```bash
# dev (SQLite)
FLASK_ENV=development flask --app main db migrate -m "description" --directory migrations_dev
FLASK_ENV=development flask --app main db upgrade --directory migrations_dev

# prod (Supabase Postgres — requires DATABASE_URL in .env)
FLASK_ENV=production flask --app main db migrate -m "description" --directory migrations_prod
FLASK_ENV=production flask --app main db upgrade --directory migrations_prod
```

Prod was stamped at the head revision (`g0a1b2c3d4e5`) right after the Postgres cutover, so new migrations layer cleanly on top.

## Key domain concepts

- **WishItem**: core model. Has three states: wishlist (unhooked=False, purchased=False), purchased (purchased=True), unhooked (unhooked=True). `wish_period` tracks how long an item sat on the wishlist before a decision.
- **Unhooked**: the app's name for "decided not to buy." Tracked with `unhooked_date`.
- **Tax logic**: NYC zipcodes get 8.75% tax unless item is under $110 (NYC clothing exemption). Stored as `price` (pre-tax), `taxed_price`, `total_price` (taxed + delivery).
- **URL extraction**: `url_extraction.py` has per-brand BeautifulSoup scrapers. Supported brands are in the `BRANDS` list at the top of that file. Falls back to `google_search_image_fallback` for images. Adding a new brand = add to `BRANDS` + add an `extract_<brandname>()` method.
- **Shopping Habits Score**: 0-100 metric on `/home` reflecting purchase impulsiveness vs. unhook patience over a rolling 90-day window. Criteria, formula, and tier thresholds are documented in `docs/shopping_habits_score.md`; tweak constants via `SCORE_WEIGHTS` / `SCORE_TIERS` at the top of `website/reports.py`.

## Auth
- Web: Flask-Login (session cookies). Existing HTML routes use `@login_required`.
- API: JWT via `flask-jwt-extended`. API routes use `@jwt_required()`. Both systems coexist.

## REST API (in progress)
All endpoints under `/api/v1/`. See the to-do list below for what's built vs pending.

Built (all in `website/api.py`):
- `POST /api/v1/auth/login` — `{email, password}` → `{token, user}`
- `POST /api/v1/auth/signup` — `{email, first_name, password, zipcode}` → `{token, user}`
- `GET  /api/v1/auth/me` — current user profile
- `GET  /api/v1/wishitems` — filterable: `?status=wishlist|purchased|unhooked`, `?category=`, `?brand=`
- `POST /api/v1/wishitems` — `{name, brand, category, link, price, delivery_fee?, tag?, description?, image_url?}`
- `GET  /api/v1/wishitems/:id`
- `PATCH /api/v1/wishitems/:id` — any subset of item fields; price recalculates tax automatically
- `DELETE /api/v1/wishitems/:id`
- `POST /api/v1/wishitems/:id/status` — `{status: "wishlist"|"purchased"|"unhooked"}`
- `POST /api/v1/wishitems/:id/favorite` — toggles favorited
- `DELETE /api/v1/wishitems/:id/image`
- `POST /api/v1/extract` — `{url}` → scraped item fields (wraps `url_extraction.py`)
- `GET  /api/v1/reports/summary` — spenditure + saves dicts keyed by date
- `POST /api/v1/reports/generate` — `{start_date, end_date}` → totals + count breakdowns by category/brand

Note: reports/generate returns structured count data (not matplotlib PNGs) so the iOS app can render its own charts.

## iOS / mobile plans

Target: React Native app (via Expo) backed by the same Flask REST API.

**Why React Native over Swift:**
- Claude Code can fully participate in the build/test loop (no Xcode required for most work)
- Expo allows testing on a real phone via QR code scan during development
- JavaScript/TypeScript is more approachable than Swift
- Can share API client and business logic across platforms

**React Native vs React:**
- React = web only (browser). Responsive layouts work on both laptop and phone browser — useful for a PWA but not a native app.
- React Native = compiles to real iOS/Android native components. Does not run in a browser (unless you add React Native Web, which is optional).
- Expo wraps React Native to remove most Xcode/Android Studio friction.

**Mobile app location:** `mobile/` subdirectory. Uses Expo Router (file-based routing).

```
mobile/
  app/
    _layout.tsx          # root — checks auth, redirects to (auth) or (tabs)
    (auth)/
      login.tsx
      signup.tsx
    (tabs)/
      index.tsx          # wishlist tab
      purchased.tsx
      unhooked.tsx
  context/auth.tsx       # AuthProvider + useAuth hook
  services/api.ts        # typed API client for all /api/v1/ endpoints
```

**To run the mobile app:**
```bash
cd mobile
npm start              # opens Expo dev tools
# Press 'i' for iOS simulator, or scan QR code with Expo Go on your phone
```

**Important for physical device testing:** `localhost` won't work on a phone.
Change `BASE_URL` in `services/api.ts` to your Mac's local IP (find it with `ifconfig | grep "inet "`).
Example: `http://192.168.1.42:5001/api/v1`

**Suggested iOS build order (after REST API is complete):**
1. Auth screen → `POST /api/v1/auth/login`, store token in Expo SecureStore
2. Wishlist screen → `GET /api/v1/wishitems?status=wishlist`
3. Add item screen → `POST /api/v1/extract` (URL paste to prefill) → `POST /api/v1/wishitems`
4. Item detail / status toggle → `POST /api/v1/wishitems/:id/status`
5. Reports screen → `GET /api/v1/reports/summary`

**Note:** Multi-user hosting on the web side should be solved before building iOS, since the iOS app depends on the same backend being stable and publicly accessible.
