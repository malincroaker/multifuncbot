# Multifuncbot

English | [Русский](README.ru.md)

A modular Telegram portfolio bot: visitors choose a scenario and try a complete customer workflow.
Select the same modules to build a standalone client bot. Russian and English interfaces are included.

![Shop Mini App](docs/images/shop-desktop.png)

## Scenarios

| Module | Customer flow | Administration |
| --- | --- | --- |
| `guide` | Three-step Stepwise guide, saved progress, bilingual PDF checklist | Configurable admin contact |
| `booking` | Service, specialist, date, free slot, confirmation and cancellation | Approve/reject, shared calendar in business mode, reminders |
| `leads` | Request, name, contact, review and submission | New → in progress → complete |
| `shop` | Chat catalogue or Mini App, persistent cart, checkout and order history | Order details and notifications in business mode |

The Mini App includes search, category filters, product details, quantity controls, pickup or
delivery and simulated payment success/failure/cancellation. Chat and Mini App use the same
cart and order services. Prices and totals come from the server; checkout retries are idempotent.

**No real money is collected.** Businesses, products and prices are fictional demonstration data.
The payment simulator cannot charge cards. YooKassa, Robokassa and Stars are research/planned
integrations, not working payment providers in this release.

## Quick start

Python 3.11+ is required. Run commands from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[web,dev]'
Copy-Item .env.example .env
```

If `.env` already exists, preserve its settings instead of overwriting it.
Create a **new** bot using `@BotFather` and put its token in the local `.env` as `BOT_TOKEN`.
Do not reuse the token of an independently running Stepwise bot. `.env` is ignored by Git.

Run the Telegram bot:

```powershell
.\.venv\Scripts\multifuncbot.exe
```

For the optional Mini App, start a second terminal:

```powershell
.\.venv\Scripts\multifuncbot-web.exe
```

Open [localhost:8000](http://127.0.0.1:8000) to try the browser demo. A bot token is not needed
for this separate preview. Stop each process with Ctrl+C.

On Linux/macOS, use `python3 -m venv .venv`, `.venv/bin/python`, `.venv/bin/multifuncbot` and
`.venv/bin/multifuncbot-web`; create `.env` with `cp .env.example .env`.

## Connect the Mini App to Telegram

1. Serve the web application at a public **HTTPS** address. Localhost is for browser preview.
2. Set `MINI_APP_URL=https://your-domain.example/` and the same `BOT_TOKEN` and
   `DATABASE_PATH` for the bot and web processes. Restart both.
3. In a private chat, open Shop → Open Mini App. The inline Web App button is provided by the bot.
4. Optionally configure a main/menu Mini App in `@BotFather`. This app uses its HTTP API,
   not the keyboard-only `sendData` submission method.

Telegram identity is verified on the server. Sessions older than one hour require reopening
the Mini App. The anonymous browser preview has its own expiring HttpOnly session and cannot
read Telegram users' orders. The app does not accept a submitted user ID or product price.

No hosting account, public HTTPS endpoint or Telegram bot identity has been provisioned by this repository.
For a local demonstration you can use the chat catalogue without configuring a Mini App URL.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `ENABLED_MODULES` | `guide,booking,leads,shop` | Only these features are imported and initialized |
| `DEFAULT_MODULE` | empty | Open one feature directly instead of the portfolio menu |
| `DEFAULT_LANGUAGE` | `ru` | Before the user chooses Russian or English |
| `APP_MODE` | `showcase` | Isolated demo workspaces; every visitor can inspect their own demo admin view |
| `ADMIN_IDS` | empty | Comma-separated Telegram user IDs for business-mode administration |
| `TIMEZONE` | `Europe/Moscow` | Studio schedule; stored appointment times are UTC |
| `DATABASE_PATH` | `data/multifuncbot.sqlite3` | Shared persistent SQLite file |
| `MINI_APP_URL` | empty | HTTPS URL enabling the Mini App button |
| `ALLOW_BROWSER_DEMO` | `true` | Browser preview, available only in showcase mode |
| `ADMIN_CONTACT_URL` | empty | Optional `https://t.me/username` contact in the guide |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Web bind address; use a reverse proxy for public hosting |
| `PAYMENT_PROVIDER` | `demo` | Only the explicit simulator is supported |

`APP_MODE=business` shares appointment slots and restricts admin actions to `ADMIN_IDS`.
Admins must first start the bot in a private chat before it can send them notifications.
Business mode still uses demo products and simulated payments; it is not a production-payment switch.

## Commands and persistence

- `/start`, `/menu`, `/cancel`, `/help`: open the scenario menu, or the configured default scenario.
- `/language`: change language while keeping the current draft or guide step.
- Leaving a scenario discards its unfinished form. Guide progress and confirmed records remain.
- SQLite stores language, progress, bookings, leads, carts, orders and notification delivery state.
- Appointment reminders run once per minute for confirmed appointments starting within an hour.
  The bot must be running. Delivery is retried on failure; a crash between sending and saving
  the delivery flag can cause a duplicate reminder.
- Business notifications use a persisted outbox, polled every 15 seconds with up to five attempts.
  Only one bot process should consume updates and notifications.

## Structure and client reuse

```text
src/multifuncbot/
  app.py                     Telegram transport
  web.py                     Optional web server
  core/                      Configuration, storage, routing, authentication, notifications
  modules/
    guide/                   Content and PDFs
    booking/                 Schedule service and chat flow
    leads/                   Lead service and chat flow
    shop/                    Catalogue, orders, chat flow, HTTP API and Mini App assets
  integrations/payments/      Explicit demo payment provider
tests/                       Domain, isolation, auth, HTTP and extraction checks
```

Start with the [client extraction guide](docs/client-extraction.md).
Disabling/removing a module never automatically deletes its existing database tables or history.
The original Stepwise repository is maintained separately.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
node --check src/multifuncbot/modules/shop/static/app.js
```

Node is only needed for the optional JavaScript syntax check, not for running the shop.
`requirements-dev.lock` records the tested dependency versions. To reproduce them, install
`-r requirements-dev.lock`, then install the project with `pip install --no-deps -e .`.
GitHub Actions checks Python 3.11 and 3.13. Tests use temporary databases and fake Telegram credentials.

[Architecture](docs/architecture.md) · [Research and inspiration](docs/research.md) ·
[Verification evidence and limits](docs/verification.md) · [Roadmap](docs/roadmap.md)
