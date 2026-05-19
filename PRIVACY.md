# Privacy Policy

Unhooked is a self-hosted personal shopping tracker. This policy describes what data the app collects and how it is used.

## Data collected

- **Account information**: email address, hashed password, zip code
- **Wish list items**: product name, brand, price, category, URL, image, notes
- **Purchase and savings history**: dates, prices, wish periods
- **Gmail OAuth tokens**: access and refresh tokens used to read your Gmail inbox (only when you connect Gmail via Settings → Connectors)

## Gmail access

When you connect Gmail, the app requests **read-only** access to your inbox (`gmail.readonly` scope). It:

- Searches for order confirmation emails matching common subject patterns
- Reads the body of matched emails to extract order details (brand, items, price, date)
- Never sends, deletes, or modifies any emails
- Stores only the OAuth tokens needed to make API calls on your behalf — not the email content itself

## Third-party data sharing

**Anthropic (Claude API):** When you use the Gmail backfill feature, the subject line and first 3,000 characters of each matched order confirmation email are sent to Anthropic's API for structured data extraction. This may include item names, prices, and order numbers. Anthropic's data usage policy applies: [anthropic.com/privacy](https://www.anthropic.com/privacy).

No other email content is shared with third parties.

## Data storage

The default deployment uses two databases depending on environment:

- **Development** stores data in a local SQLite file (`instance/database_dev.db`) on the machine running the app.
- **Production** stores data in a managed Postgres instance on Supabase, accessed via a connection string in `.env` (`DATABASE_URL`). Supabase is a third-party provider; their data handling is governed by [supabase.com/privacy](https://supabase.com/privacy).

Gmail OAuth tokens are stored as plaintext in whichever database is active. Keep the database file (dev) and `DATABASE_URL` credentials (prod) secure and do not expose them publicly.

## Self-hosted disclaimer

This app is designed to be run locally or self-hosted. The operator of the instance is responsible for securing the server, database, and credentials. Anthropic API keys and Google OAuth credentials should be stored in `.env` and never committed to version control.
