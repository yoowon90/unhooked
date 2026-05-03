# Unhooked — Roadmap

## Current state (self-hosted, fork-to-use)

Anyone who wants to use this app forks the repo and runs it locally. Each user:
- Generates their own `SECRET_KEY` / `JWT_SECRET_KEY`
- Gets their own `ANTHROPIC_API_KEY`
- Creates their own Google Cloud project and OAuth credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`)
- Adds a Google redirect URI pointing to their own localhost

This works fine for personal use. The Google Cloud setup is a one-time ~5 minute task documented in `CLAUDE.md` and in the app's Settings page.

---

## Phase 1 — Centralized OAuth app (medium term)

**Goal:** Users who fork the repo don't need to create their own Google Cloud project. Instead, one Google Cloud project is registered for the whole app and shared credentials live in `.env`.

**What changes:**
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` become a single pair set up by the repo maintainer once
- Remove `google_client_id` / `google_client_secret` columns from the `User` model
- Remove the credentials form from `Settings → Connectors`
- The Gmail connection UX becomes purely: click **Connect Gmail** → browser opens Google login → approve → done (identical to how Claude Code's MCP connectors work)

**Constraint:** Google requires OAuth apps that access sensitive scopes (like `gmail.readonly`) to go through a verification process if they have more than 100 users. Below 100, the app can stay in "testing" mode — users just need to be added as test users in the Google Cloud Console.

---

## Phase 2 — Hosted multi-user web app (long term)

**Goal:** No forking required. Users visit a URL, create an account, and use the app like any SaaS product.

**What this requires:**

### Authentication overhaul
- Replace or wrap Flask-Login with a proper hosted auth system (e.g. Auth0, Clerk, or self-managed)
- Users sign up with email/password or "Sign in with Google"
- JWT tokens issued per-session, stored securely (HttpOnly cookies or SecureStore on mobile)

### Secrets management
- `ANTHROPIC_API_KEY` and `GOOGLE_CLIENT_ID/SECRET` stored as encrypted environment secrets on the hosting platform (e.g. Railway, Render, Fly.io, AWS) — never in `.env` files committed to git
- Per-user Gmail tokens (`gmail_access_token`, `gmail_refresh_token`) encrypted at rest in the database, not stored as plaintext

### Gmail OAuth UX (what it will look like)
The experience the user described — click "Connect Gmail", a browser window opens to Google, you log in, and you're done — **is already how our OAuth flow works**. The only current friction is the Google credentials form, which goes away in Phase 1. Once centralized credentials are in place, the UX is:
1. Go to Settings → Connectors
2. Click **Connect Gmail**
3. Google login page opens in browser
4. User approves "read Gmail" permission
5. Redirected back to the app — connected

This is standard OAuth and is exactly how Notion, Linear, Slack and every other app handles third-party integrations.

### Infrastructure
- Move from SQLite to PostgreSQL for multi-user concurrency
- Add a proper WSGI server (Gunicorn) behind a reverse proxy (nginx or Caddy)
- Rate limiting on the `/backfill/scan` endpoint (Gmail API calls are expensive per-user)
- Background job queue (Celery or RQ) for long-running Gmail scans instead of blocking HTTP requests

### Per-user billing / quota (optional)
- Track Anthropic API usage per user
- Optionally require users to bring their own `ANTHROPIC_API_KEY` or charge per scan

---

## Google Cloud OAuth setup (for Phase 1 / current self-hosted)

Steps to create the Google Cloud project and OAuth credentials:

1. Go to **console.cloud.google.com** and sign in.
2. Create a new project (e.g. "Unhooked").
3. **APIs & Services → Library** → search **Gmail API** → Enable.
4. **APIs & Services → OAuth consent screen**:
   - User Type: External
   - App name: Unhooked, support email: your email
   - Scopes: add `gmail.readonly`
   - Test users: add your Gmail address (stays in testing mode, no Google verification needed)
5. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**:
   - Application type: Web application
   - Authorized redirect URIs:
     - `http://localhost:5001/connectors/gmail/callback` (dev)
     - `http://localhost:5000/connectors/gmail/callback` (local prod)
     - Your public domain if hosted (e.g. `https://unhooked.yourdomain.com/connectors/gmail/callback`)
6. Copy **Client ID** and **Client Secret** into `.env`.
