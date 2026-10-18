# Implementation stages

1. Done: project skeleton, configuration, database, registry and CI.
2. Done: scenario navigation and bilingual Stepwise with persistent progress and PDFs.
3. Done: studio booking and lead collection, customer/demo admin views and reminders.
4. Done: cart, idempotent checkout, demo payment states and order history.
5. Done: shop API, verified Mini App identity, bilingual catalogue and persistent notifications.
6. Done: local browser walkthrough, packaging, client extraction guide and GitHub publication.
7. Done: one edited chat screen, local scenario menus and stateful Back navigation.
8. Done: readable studio dates, reversible lead statuses with reasons/history/customer updates,
   two-hour post-visit reviews and an immediate sample review for showcase visitors.

The owner created a Telegram bot and configured BOT_TOKEN locally. Next: choose HTTPS hosting
for the Mini App, configure MINI_APP_URL, then verify its flows inside Telegram. A temporary
tunnel is suitable for an initial check; a stable server is suitable for portfolio visitors.
No hosting was provisioned by the code or its offline tests.

Later extensions: support tickets, CRM adapters, YooKassa test-store integration,
Telegram Stars for digital goods and production hosting. These are not included as working features.

The first release demonstrates physical stationery products and studio appointments.
The payment simulator is labelled throughout and cannot charge a user.
