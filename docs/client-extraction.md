# Build a client bot from selected modules

For example, a booking-only studio bot:

```dotenv
ENABLED_MODULES=booking
DEFAULT_MODULE=booking
APP_MODE=business
ADMIN_IDS=123456789
STUDIO_CONTACT_URL=https://t.me/replace_with_studio_contact
REVIEW_DELAY_HOURS=2
ALLOW_BROWSER_DEMO=false
DATABASE_PATH=data/studio.sqlite3
BOT_TOKEN=replace-locally-with-a-new-bot-token
```

1. Copy the project into a new client workspace and create a separate bot identity and database.
2. Set the configuration above, using the real administrator's numeric Telegram ID.
3. Install the base project with `pip install -e .`. The `web` extra is unnecessary.
4. Edit the service names, prices, specialists and working hours in
   `modules/booking/service.py`, and studio wording in `modules/booking/feature.py`.
5. In this **new copy**, remove unwanted module folders and their module-specific tests.
   Keep shared core files. If shop is removed, `web.py`, the web script/package-data entry
   and `integrations/payments/` can also be removed.
6. Keep corresponding names out of `ENABLED_MODULES`; removing a feature folder while leaving it
   enabled is a configuration error. Run the remaining tests before delivery.
7. Ask the admin to start the bot, then verify booking approval, cancellation, notifications
   and reminders using a separate customer account. Verify review requests after the configured
   delay and that submitted ratings are visible in the business desk.

For shop-only delivery, use `ENABLED_MODULES=shop`, `DEFAULT_MODULE=shop`, install `.[web]`,
configure HTTPS, and keep the shop assets plus its payment adapter.
The demo provider remains a simulator even in business mode. A production payment integration
is a separate implementation and merchant-onboarding task.

All initial appointments use fixed one-hour slots. Variable service durations require interval
overlap checks in the same write transaction, rather than simply changing a label or price.
The working calendar is Monday–Saturday, six slots/day, with a one-hour lunch break.

## Preserve existing data

Changing enabled features or application mode does not erase records. Showcase data is partitioned
by visitor; business data uses a shared tenant. Old demo tenants remain stored but are not shown in
business mode. Start with a separate client database instead of reusing a portfolio/demo database.
Back up the SQLite file while the application is stopped before changing schema or cleaning data.

## Interface for another module

A feature exports `create(db, settings)` in its `feature.py`, and implements `name`, `title`,
`start`, `action` and `text`. It returns transport-neutral `Screen`/`Button` objects. The module
owns its SQL schema, service methods, bilingual copy and tests. Register its name explicitly in
`core/config.py`; the registry loads only configured names. Features must not import each other.
Set `menu_names=(ru, en)` for the local menu label. Use `scenario_exit_button` at introductions
and `home_button` inside flows. Retained notifications may expose only navigation actions
explicitly listed in `notice_actions`; these must check ownership and never apply a mutation.

By default the router clears a feature's unfinished conversation state when leaving it.
Set `retain_state_on_exit=True` only for persistent progress such as the guide. Confirmed
business records belong to feature tables and are never deleted by navigation.
