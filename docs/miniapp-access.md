# Opening the shop Mini App

The catalogue, cart and checkout already exist. An empty `MINI_APP_URL` means the bot shows
an explanatory entry rather than silently hiding the Mini App. The actual Web App button
appears once a public HTTPS URL is configured. The chat catalogue remains available.

## Choose an access method

| Method | What runs | Good for | Tradeoff |
| --- | --- | --- | --- |
| Local browser | The web process on your computer | Development, checking layout and checkout | Does not open as a production Telegram Mini App |
| Temporary HTTPS tunnel | Local web process plus a tunnel client | First check inside Telegram, a scheduled demonstration | Computer must stay on; URL can change; testing service has no uptime guarantee |
| Permanent server | Bot and web processes hosted continuously | Portfolio visitors and customer demos at any time | Hosting account, deployment and ongoing hosting cost |

A temporary tunnel exposes the local web application to people who know its URL. The shop
uses Telegram initData verification; the optional browser preview gives each visitor separate
demo data. A tunnel does not make the computer or local processes run continuously.

For example, [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
provide a temporary URL without a domain/account, and stop when the tunnel client stops.
Their hostname changes on restart. This is an example for evaluation, not a configured
service or a promise about availability from a particular network.

## Local preview

From the project root, in a second PowerShell terminal:

```powershell
.\.venv\Scripts\multifuncbot-web.exe
```

Open http://127.0.0.1:8000 in a browser. This command reads the project's `.env` and shared
database. A development preview started manually with different `Settings` or an isolated
database is not the server to expose for Telegram integration.

## First Telegram check, after choosing a tunnel

1. Start the web process above. If using Cloudflare, install its official tunnel client first.
2. Start the chosen tunnel for `http://127.0.0.1:8000`. With cloudflared, the command is
   `cloudflared tunnel --url http://127.0.0.1:8000`.
3. Put the generated HTTPS URL into the local `.env` as `MINI_APP_URL`.
4. Restart the bot and web processes. Both must read the same `BOT_TOKEN` and `DATABASE_PATH`.
   The web server also reads `MINI_APP_URL` to recognize HTTPS when a tunnel forwards plain HTTP.
5. Open Shop → Open Mini App in a private Telegram chat. Check cart sharing and checkout.
6. Keep the bot, web process and tunnel running for the duration of the check. If the URL changes,
   update `.env` and restart the bot again.

## Alternative: localhost.run on Windows

If Cloudflare cannot connect from the current network, [localhost.run](https://localhost.run/docs/)
can create a temporary HTTPS tunnel using Windows OpenSSH. In a separate PowerShell window,
while the local web server is running:

```powershell
ssh -T -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -R 80:127.0.0.1:8000 nokey@localhost.run
```

The first connection asks to remember the SSH host key. The service then prints an HTTPS
address (currently a free subdomain under `lhr.life`). Copy the address into the local `.env`:

```dotenv
MINI_APP_URL=https://the-address-printed-by-the-tunnel
```

Replace any existing `MINI_APP_URL` line instead of adding a second one. Keep `BOT_TOKEN`
unchanged and do not put it in a URL or send it to the tunnel provider. Restart the bot and
web server, then open `/start` → Shop → Open Mini App in a private Telegram chat. An already
displayed shop menu must be opened again to receive the new button address. BotFather
configuration is not needed for this inline button.

Keep the SSH window open. Ctrl+C stops the tunnel. Its free address can change after a
reconnection or after a few hours; update `.env` and restart both processes when that happens.
The temporary URL exposes the shop website; it does not expose the project folder or `.env`.
Opening the URL directly in a browser uses a separate demo identity. Open it through the
bot's Mini App button to share the Telegram user's cart and orders.

The application does not automatically start a tunnel or provision a hosting account.
For a permanent deployment, use a stable HTTPS address and run the bot and web process with
process supervision, a shared database location and database backups. The server must retain
the SQLite file across restarts/deployments. The current physical-product shop uses demo payments.

[Telegram Mini Apps documentation](https://core.telegram.org/bots/webapps)
