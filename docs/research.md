# Reference research — 18 October 2026

These repositories were read as design references, not adopted as dependencies or run locally.
All three have MIT licenses; this project does not copy their source code. Their small commit
histories and portfolio descriptions do not establish production readiness.

| Reference | Useful idea | Decision for Multifuncbot |
| --- | --- | --- |
| [slakertop1/telegram-mini-app](https://github.com/slakertop1/telegram-mini-app) | Native Telegram theme, server-side catalogue totals, plain JS + FastAPI | Keep a small frontend; also enforce initData expiry and persist orders |
| [KirillHat/coffee-bot](https://github.com/KirillHat/coffee-bot) | Cart, checkout and order statuses shared by the bot and Mini App | Snapshot order lines before payment; never build a paid order from a mutable cart |
| [sonoyumi/booking-bot](https://github.com/sonoyumi/booking-bot) | Pure schedule service, UTC persistence, database constraints, persisted reminder flags | Scope slot uniqueness by tenant and specialist; fixed one-hour slots avoid overlap |

Source files inspected: Mini App `app/main.py`, `static/app.js`, `bot/bot.py`; coffee
`handlers/payments.py`, `handlers/webapp.py`, `keyboards/inline.py`; booking
`src/booking_bot/db.py`, `schedule.py`, `reminders.py`, and each repository's LICENSE.

## Official integration references

- [Telegram Mini Apps](https://core.telegram.org/bots/webapps): inline/menu launches use our
  HTTPS API and verified raw initData. `sendData` is specific to keyboard-button launches.
- [Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  HMAC, constant-time comparison, required positive integer user ID, auth_date age and future bounds.
  A one-hour authentication TTL is our policy, not a Telegram-mandated value.
- [Telegram Stars](https://core.telegram.org/bots/payments-stars): digital goods sold inside
  Telegram require Stars. The initial shop sells explicitly fictional physical stationery.
- [YooKassa testing](https://yookassa.ru/developers/payment-acceptance/testing-and-going-live/testing):
  test store before contract, no real charges, cards and YooMoney; do not promise sandbox SBP.
- [Robokassa testing](https://docs.robokassa.ru/ru/testing-mode): alternative test adapter later.

Pally/PayPalych official documentation was inaccessible to the research tool. Test access,
terms and capabilities remain unverified. No claim that it cannot be integrated is made.
