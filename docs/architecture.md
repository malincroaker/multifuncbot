# Architecture

## Boundaries

One Python application, explicit feature registration, SQLite, and an optional FastAPI process.
The Telegram transport renders feature screens; business services do not import Telegram.
`telegram_ui.py` owns editing, callback revisions and input cleanup. Feature screens declare
an optional `back` action and a safe `refresh` action; the router renders Back consistently
and saves a view snapshot without replaying business mutations. See [chat navigation](chat-navigation.md).
Feature modules own schemas, flows, copy and tests. Modules never import each other.
The shop owns its API and Mini App assets. Installing the bot does not require the web extra.

`ENABLED_MODULES` controls imports and schema initialization. `DEFAULT_MODULE` skips the
portfolio menu for a client bot. Remove an unused module, its tests and its configuration
entry together. Existing database tables are deliberately retained; disabling a feature is not deletion.

## Isolation

`showcase` mode partitions business data by visitor: everyone can try their own demo admin panel.
`business` mode shares appointment slots and limits administration to `ADMIN_IDS`.
Conversation state is scoped to user and private chat, with a separate namespace per feature.
Language, drafts and completed records persist in SQLite. Switching scenarios clears the
active unfinished conversation but does not delete confirmed records or guide progress.

## Shop trust boundary

The server owns product prices, totals, cart quantities, order state and payment results.
Telegram Mini App authentication verifies the HMAC and age of `initData` on the server.
The browser preview uses a separate random, expiring HttpOnly session, never a submitted user ID.
Cross-origin mutations are rejected. No production payment adapter is enabled in the first release.

## Technology choices

- Keep python-telegram-bot from Stepwise for continuity, using polling and explicit routing.
- SQLite transactions protect slots and checkout; money is stored as integer kopecks.
- Plain HTML/CSS/JavaScript keeps the Mini App easy to extract without a frontend build system.
- FastAPI is an optional web extra, used only for the shop.
- pytest focuses on isolation, booking conflicts, order state and authentication boundaries.

Stepwise remains an independent repository; this project reuses the owner's bilingual guide
and PDF materials without modifying or publishing changes to the original project.
