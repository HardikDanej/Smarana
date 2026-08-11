# Smṛti Memory Server

A small remote MCP server that gives Smṛti a real `MCP` persistence mode
instead of only the artifact (copy-paste) fallback. It exposes four tools —
`read_file`, `write_file`, `list_files`, `list_projects` — over streamable
HTTP, matching the `mcp__filesystem__*` calls that
[`workflows/mcp-handshake.md`](../workflows/mcp-handshake.md) already
expects.

Each Claude Project you connect this to passes its own `project` name on
every call, so one running server safely holds memory for many Projects —
`server/data/<project>/MEMORY.md` on disk, isolated per project.

## Why a tunnel, not just localhost

claude.ai's Connectors feature (Settings → Connectors, Pro/Max/Team/Enterprise
plans only) requires an HTTPS URL it can reach over the internet. A server
bound to `127.0.0.1` on your machine is invisible to it. A tunnel gives your
local server a temporary public HTTPS URL without you having to host it
anywhere. This also means, in effect, only Connector-eligible (Pro+) accounts
can ever reach the server through claude.ai — the platform's own paywall is
the gate.

**This only works while your machine and the tunnel are both running.** If
you close the laptop, claude.ai will get a connection error until you start
both again.

## 1. One-time setup

```bash
cd server
python -m venv ../.venv        # if you don't already have the project's .venv
../.venv/Scripts/pip install -r requirements.txt   # Windows
# ../.venv/bin/pip install -r requirements.txt     # macOS/Linux

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(24))"   # paste into SMRITI_LOGIN_PASSWORD
```

**Auth: real OAuth, with a fallback.** claude.ai's Custom Connector dialog
only supports OAuth or no auth — it doesn't offer a field for a static
bearer token, so an earlier version of this server that required one
couldn't be connected at all ("Couldn't register with Authorization:
Bearer ...'s sign-in service"). This version implements a minimal but real
OAuth 2.1 authorization server (`oauth_provider.py`): dynamic client
registration (RFC 7591), PKCE (RFC 7636), and a password-gated `/login`
page — so the claude.ai Connector flow ends at an actual credential check,
not just possession of the tunnel URL.

- Set **both** `SMRITI_PUBLIC_HOST` and `SMRITI_LOGIN_PASSWORD` in `.env`
  to turn OAuth on. The server prints a warning and runs with **no auth at
  all** if either is missing — useful for quick local testing, not
  recommended once you're actually using this day to day.
- Registered clients and refresh tokens persist to `server/oauth_store.json`
  (gitignored) so a server restart doesn't force reconnecting the claude.ai
  Connector — as long as the tunnel URL hasn't also changed underneath it.
- If you think the password leaked, change `SMRITI_LOGIN_PASSWORD` and
  restart; existing tokens issued under the old password keep working
  until they expire (access tokens: 1 hour) since there's no per-password
  token revocation — delete `server/oauth_store.json` for an immediate
  hard reset of every registered client and token.

## 2. Run the server

```bash
../.venv/Scripts/python server.py
```

It binds to `127.0.0.1:8787` by default (override with `SMRITI_HOST` /
`SMRITI_PORT` in `.env`).

## 3. Expose it with a tunnel

Using [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
(no account needed for a quick/ephemeral tunnel):

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

It prints a random `https://<something>.trycloudflare.com` URL. That URL
changes every time you restart the tunnel — fine for personal testing, but if
you want a stable URL, use a named Cloudflare Tunnel (needs a free Cloudflare
account + a domain) instead of the quick-tunnel form.

ngrok (`ngrok http 8787`) works the same way if you'd rather use that.

**Important — set `SMRITI_PUBLIC_HOST` after every tunnel (re)start.** The
SDK's DNS-rebinding protection rejects any request whose `Host` header isn't
on an allow-list, and by default that list only contains `localhost`. A
request arriving through the tunnel has the tunnel's hostname as its `Host`
header, so without this it gets rejected with `421 Misdirected Request` —
which is exactly the error claude.ai's connector dialog surfaces as
"Couldn't connect to the server." Copy the hostname (no `https://`, no
`/mcp`) from the tunnel's printed URL into `SMRITI_PUBLIC_HOST` in `.env`,
then restart `server.py`:

```
SMRITI_PUBLIC_HOST=random-words-here.trycloudflare.com
```

If you're using the free quick-tunnel form, this means restarting the
server every time you restart the tunnel, since the hostname changes each
time — and since OAuth's `issuer_url` is derived from `SMRITI_PUBLIC_HOST`,
you'll also need to reconnect the claude.ai Connector at the new URL
(dynamic client registration runs again automatically; you'll just need to
log in again with `SMRITI_LOGIN_PASSWORD` when prompted). A named tunnel
avoids all of this churn.

## 4. Add it as a Connector in claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://<your-tunnel-domain>/mcp`
3. Leave the "OAuth Client ID" / "OAuth Client Secret" advanced-settings
   fields **empty** — the server registers a client automatically via RFC
   7591 the first time you connect; you don't fill these in by hand.
4. Click Add, then Connect. claude.ai redirects to this server's `/login`
   page — enter `SMRITI_LOGIN_PASSWORD` there. On success it redirects back
   to claude.ai with the connection established.
5. Enable the connector for the specific Project(s) that should use it.

If both env vars are unset, skip straight to step 4 — there's no login
page to hit, and the connector connects immediately with no auth at all.

Once connected, `workflows/mcp-handshake.md`'s Phase-1 probe will detect the
`mcp__filesystem__*`-shaped tools and switch that Project to `MCP` mode
automatically — no more copy-pasting `MEMORY.md` back into Knowledge.

## Tool reference

| Tool | Args | Behavior |
|---|---|---|
| `read_file` | `project`, `filename` (default `MEMORY.md`) | Returns file contents, or `""` if it doesn't exist yet |
| `write_file` | `project`, `content`, `filename` (default `MEMORY.md`) | Overwrites the file |
| `list_files` | `project` | Filenames currently stored for that project |
| `list_projects` | — | Every project with at least one stored file |

Paths are confined to `server/data/<project>/` — traversal outside it
(`..`, absolute paths, nested slashes in `project`/`filename`) is rejected.

## Testing without claude.ai

`test_client.py` is a standalone smoke test — start the server, then in a
second terminal:

```bash
../.venv/Scripts/python test_client.py
```

It calls all four tools against a scratch `smoke-test` project and prints
the results.

`test_oauth_flow.py` exercises the full OAuth path end to end — metadata
discovery, dynamic client registration, `/authorize` → `/login`, a wrong
password (must be rejected), the correct password, code exchange, a tool
call without a token (must be rejected), a tool call with the token (must
succeed), and refresh-token exchange. Requires `SMRITI_PUBLIC_HOST` and
`SMRITI_LOGIN_PASSWORD` set and the server reachable at that public host
(i.e. the tunnel needs to be up — this test talks to the real public URL,
not localhost, since OAuth's redirect/issuer URLs are the public ones):

```bash
../.venv/Scripts/python test_oauth_flow.py
```

## Known limitations

Read this before relying on the server, and especially before pointing
anyone else at it:

- **No process supervision.** `server.py` and the tunnel are both plain
  foreground processes you start by hand. No restart-on-crash, no
  auto-start on boot, no health check. A machine restart silently kills
  persistence until you notice and restart both.
- **The free quick-tunnel URL is not stable.** It changes on every
  `cloudflared` restart, which then requires updating `SMRITI_PUBLIC_HOST`
  and reconnecting the claude.ai Connector. A named Cloudflare Tunnel (needs
  a domain) avoids this.
- **`oauth_store.json` never expires or prunes entries on its own.**
  Registered clients and refresh tokens accumulate indefinitely. Rotating
  `SMRITI_LOGIN_PASSWORD` stops *new* logins, but access tokens already
  issued keep working until their natural 1-hour expiry, and existing
  refresh tokens keep minting new access tokens indefinitely since refresh
  itself doesn't re-check the password. Delete `server/oauth_store.json`
  (and restart the server) for an immediate, total reset of every
  registered client and token — the only way to force everyone to log in
  again right now.
- **No server-side schema validation on write.** `write_file` stores
  whatever content it's given; `memory-schema.json` conformance is enforced
  by Claude following `mcp-handshake.md`'s instructions during a chat, not
  by this server. A misbehaving client could write invalid `MEMORY.md`
  content and the server won't stop it.
- **No rate limiting or size limits.** Nothing stops a buggy or malicious
  client with a valid token from writing arbitrarily large content or
  hammering the server with requests.
- **Single resource owner.** This is built for one person (whoever knows
  `SMRITI_LOGIN_PASSWORD`), not multi-tenant use — every registered OAuth
  client shares the same login and the same data root.
