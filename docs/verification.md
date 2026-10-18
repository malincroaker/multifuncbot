# Verification — 18 October 2026

## Verified locally

- 49 pytest cases on Python 3.13: booking conflicts under concurrent requests, tenant/user
  isolation, ownership and admin checks, persistent guide progress, form review, idempotent
  checkout, frozen order totals, payment transitions, Telegram HMAC age/signature validation,
  browser sessions, CSRF rejection, outbox persistence and Telegram transport rendering with mocks.
- Physical module extraction: a temporary copy containing only the guide and shared core runs
  without the booking/leads/shop folders and without importing FastAPI.
- Ruff checks and JavaScript syntax check pass; pip reports no broken requirements.
- A wheel builds successfully and contains both PDFs plus all nine Mini App assets.
- The original owner's Stepwise PDFs and committed PDF blobs have identical SHA-256 digests.
- Browser walkthrough: catalogue → cart → delivery → order → simulated payment failure →
  simulated success → persisted order in English order history. Search also verified in English.
- Screenshots inspected at a 390 px mobile viewport and a 1280 px desktop viewport. Catalogue
  images load; desktop grid has three columns and no horizontal overflow.

GitHub Actions also verified the implementation on Python 3.11 and 3.13.
Current checks are visible in the repository's Actions tab; do not treat this note as a live CI monitor.

## Limits

- A new BOT_TOKEN has not been supplied: no claim of a live Telegram/BotFather test or real
  delivery of bot messages, PDFs, admin notifications or reminders is made.
- No public HTTPS hosting has been configured; the shop is verified as a local browser app,
  not as a live Telegram WebView. Telegram integration uses the documented signed-initData flow.
- No payment-provider account/keys are configured. No money moves; all payment states are simulated.
- Support tickets, CRM, variable-duration services, refunds, inventory management and production
  payment adapters are future features.
- Reminders and notification delivery can repeat if a process crashes after sending but before
  recording delivery. The outbox retries five times; it does not claim exactly-once delivery.
- Starlette currently emits a deprecation warning for its httpx-backed TestClient. Tests pass;
  the installed python-telegram-bot still uses httpx. This is dependency migration work, not a failure.

Demo artwork is original SVG illustration created for this project. Reference projects were read
for architecture ideas; their source code was not copied or executed.
