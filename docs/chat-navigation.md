# Chat navigation

## Display and storage

The private chat has one active text screen. Button clicks, commands and text replies normally
edit that message instead of sending another. `telegram_ui` conversation state stores its ID,
keyboard revision, allowed actions and the latest PDF ID. It survives a process restart.
The router stores a transport-neutral screen snapshot separately; a snapshot never contains
a document delivery action, so recovering the screen does not resend a file.

Each callback contains an opaque revision and a button index. The server resolves the actual
action from SQLite and checks the user, chat and message ID. It invalidates the revision before
calling a feature, so a queued second click cannot repeat a mutation, even if rendering fails.
Updates use python-telegram-bot's default sequential processing; run a single polling process.
This is a UI guard in addition to service authorization and checkout idempotency.

## Returning and editing

| Current view | Back target |
| --- | --- |
| Scenario menu | Root; `/back` stays at the menu |
| Scenario introduction | Scenario menu, or configured client default |
| Booking form | Previous choice; changing a service/specialist invalidates dependent choices |
| Lead form / checkout | Previous field with its saved answer and a Keep button |
| First form field | Scenario introduction, or cart for checkout |
| Review | Last field or appointment time |
| Lists | Scenario introduction |
| Order detail | Customer orders, or admin orders when opened by an admin |
| Guide completion | Last guide step |
| Guide contact | Guide introduction |
| Language / validation error | Saved previous view, without replaying its action |

`Screen.back` declares the target, and the router adds a button above the global home link.
`/back` uses the same target. `Screen.refresh` is a safe view-rendering action used to regenerate
the current section after a language change. Never put creation, payment, status changes or
other mutations in `refresh`. Form cursors are separate from answers, so returning to a field
does not delete it. Menu exits discard unfinished forms; persistent records and carts remain.

## Cleanup and exceptions

- Text replies and commands are deleted only after rendering succeeds. If rendering fails,
  the user's input remains available. Unsupported user attachments are retained.
- PDFs stay separate from the text screen. The latest checklist is reused on repeat requests.
  If it was deleted, the bot sends it again; switching PDF language replaces the tracked attachment.
- Reminders and business notifications remain separate. Their IDs are recorded separately;
  the next navigation screen is sent below them, and the previous navigation screen is retired.
- A missing/uneditable screen gets a replacement. A timeout, rate limit or unexpected API error
  does not trigger a fallback send, since the original edit may have succeeded.
- If an old screen cannot be deleted, the bot attempts to remove its keyboard. Callback validation
  still prevents its previous actions from executing. Old pre-update buttons expire too.
- Old chat history whose IDs were never tracked is not enumerated or bulk-deleted. Telegram
  [limits message deletion](https://core.telegram.org/bots/api#deletemessage), including the usual
  48-hour window; inability to delete a message does not block the next screen.

The implementation uses [editMessageText](https://core.telegram.org/bots/api#editmessagetext)
for ordinary transitions. Telegram has no transaction combining a business operation, message
delivery and the local state commit. A crash between delivery and saving its ID may leave an
extra message; there is no exactly-once delivery claim. Domain records remain server-authorized.

Tests simulate Telegram errors and updates without using a real token. They cover restart,
stale/double clicks, callback consumption before a timeout, PDF reuse/recovery, safe input cleanup,
form backtracking, language changes and client-default navigation.
