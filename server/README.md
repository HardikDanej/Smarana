# Smaraṇa Memory Server

A small remote memory server that gives Smaraṇa a real `MCP` persistence mode
instead of only the artifact (copy-paste) fallback, and a plain JSON REST
surface for any caller that isn't Claude and doesn't speak MCP at all: a
CRM webhook, an ERP script, a codebase with no LLM in front of it. Same six
tools either way — `read_file`, `write_file`, `list_files`, `list_projects`,
`search_memory`, `classify_fact` — over streamable HTTP for MCP clients
(matching the `mcp__filesystem__*` calls
[`workflows/mcp-handshake.md`](../workflows/mcp-handshake.md) already
expects) or plain `/projects/...` HTTP routes for everyone else. See
[REST: for callers with no MCP client](#rest-for-callers-with-no-mcp-client)
below.

`write_file` now enforces `memory-schema.json` and the 120-line/~800-token
hard cap server-side, via `engine.py`, for structured JSON writes to
`MEMORY.md` — a malformed state gets rejected outright, and a state over
the cap gets auto-consolidated before it's persisted. This is what actually
makes the tier structure real, for any caller, not just a Claude session
that happened to follow `SKILL.md`'s prose well. See
[Server-side enforcement on write](#server-side-enforcement-on-write).

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
python -c "import secrets; print(secrets.token_urlsafe(24))"   # paste into SMARANA_LOGIN_PASSWORD
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

- Set **both** `SMARANA_PUBLIC_HOST` and `SMARANA_LOGIN_PASSWORD` in `.env`
  to turn OAuth on. The server prints a warning and runs with **no auth at
  all** if either is missing — useful for quick local testing, not
  recommended once you're actually using this day to day.
- Registered clients and refresh tokens persist to `server/oauth_store.json`
  (gitignored) so a server restart doesn't force reconnecting the claude.ai
  Connector — as long as the tunnel URL hasn't also changed underneath it.
- If you think the password leaked, change `SMARANA_LOGIN_PASSWORD` and
  restart; existing tokens issued under the old password keep working
  until they expire (access tokens: 1 hour) since there's no per-password
  token revocation — delete `server/oauth_store.json` for an immediate
  hard reset of every registered client and token.

## 2. Run the server

```bash
../.venv/Scripts/python server.py
```

It binds to `127.0.0.1:8787` by default (override with `SMARANA_HOST` /
`SMARANA_PORT` in `.env`).

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

**Important — set `SMARANA_PUBLIC_HOST` after every tunnel (re)start.** The
SDK's DNS-rebinding protection rejects any request whose `Host` header isn't
on an allow-list, and by default that list only contains `localhost`. A
request arriving through the tunnel has the tunnel's hostname as its `Host`
header, so without this it gets rejected with `421 Misdirected Request` —
which is exactly the error claude.ai's connector dialog surfaces as
"Couldn't connect to the server." Copy the hostname (no `https://`, no
`/mcp`) from the tunnel's printed URL into `SMARANA_PUBLIC_HOST` in `.env`,
then restart `server.py`:

```
SMARANA_PUBLIC_HOST=random-words-here.trycloudflare.com
```

If you're using the free quick-tunnel form, this means restarting the
server every time you restart the tunnel, since the hostname changes each
time — and since OAuth's `issuer_url` is derived from `SMARANA_PUBLIC_HOST`,
you'll also need to reconnect the claude.ai Connector at the new URL
(dynamic client registration runs again automatically; you'll just need to
log in again with `SMARANA_LOGIN_PASSWORD` when prompted). A named tunnel
avoids all of this churn.

## 4. Add it as a Connector in claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://<your-tunnel-domain>/mcp`
3. Leave the "OAuth Client ID" / "OAuth Client Secret" advanced-settings
   fields **empty** — the server registers a client automatically via RFC
   7591 the first time you connect; you don't fill these in by hand.
4. Click Add, then Connect. claude.ai redirects to this server's `/login`
   page — enter `SMARANA_LOGIN_PASSWORD` there. On success it redirects back
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
| `write_file` | `project`, `content`, `filename` (default `MEMORY.md`) | Validates and persists (see below), then re-indexes the project's aged-out memory for `search_memory` |
| `list_files` | `project` | Filenames currently stored for that project |
| `list_projects` | — | Every project with at least one stored file |
| `search_memory` | `project`, `query`, `top_k` (default 5) | Semantic search over that project's superseded/deprecated Tier 2 ADRs and Compressed Changelog entries — the history a plain `read_file` can no longer surface in full |
| `classify_fact` | `project`, `candidate_text`, `existing_context` (default `""`) | Local Laya tier/contradiction/duplicate classification on a raw fact — no LLM required to call it. Same classifier `scripts/tier_screen.py` already gives Claude as an optional Phase 2 cross-check, exposed here as a first-class operation. Degrades to `{"error": ...}` if `laya` isn't installed; never raises |

Paths are confined to `server/data/<project>/` — traversal outside it
(`..`, absolute paths, nested slashes in `project`/`filename`) is rejected.

## Server-side enforcement on write

`write_file` behaves differently depending on the shape of `content`:

- **A JSON object matching `memory-schema.json`.** Validated against the
  schema and rejected with a one-line reason if it doesn't conform. If it's
  over the hard cap, `engine.consolidate` runs server-side first (the same
  dedup/collapse logic `workflows/consolidate-memory.md` specifies), and
  the *result* of that consolidation is what gets rendered to Markdown and
  persisted. This is the path that gets full enforcement, and the one a
  non-LLM caller should actually write through.
- **Anything else (pre-rendered Markdown, the original Claude-artifact
  behavior).** Checked against the hard cap by line/token count and
  rejected if over. `engine.py` has no Markdown parser back to
  schema-shaped state yet, so a rejected Markdown write can't be
  auto-consolidated the way a rejected JSON write can — pass structured
  JSON instead, or run `workflows/consolidate-memory.md` and retry.

Any filename other than `MEMORY.md` is stored as-is, unvalidated, exactly
as before this existed.

## REST: for callers with no MCP client

Every tool above also has a plain JSON HTTP route, for a CRM, an ERP, or
any script that can make an HTTP request but has no MCP client library and
no LLM reasoning over `SKILL.md`'s prose:

| Route | Method | Body / Query | Behavior |
|---|---|---|---|
| `/projects` | GET | — | Same as `list_projects` |
| `/projects/{project}/memory` | GET | `?filename=` (default `MEMORY.md`) | Same as `read_file` |
| `/projects/{project}/memory` | PUT | raw body = `content` | Same as `write_file`; `422` on rejection, with the reason in `{"error": "..."}` |
| `/projects/{project}/files` | GET | — | Same as `list_files` |
| `/projects/{project}/search` | GET | `?query=&top_k=` | Same as `search_memory` |
| `/projects/{project}/classify` | POST | `{"candidate_text": "...", "existing_context": "..."}` | Same as `classify_fact` |

**Auth.** If `SMARANA_PUBLIC_HOST`/`SMARANA_LOGIN_PASSWORD` are set, every
REST route requires `Authorization: Bearer <SMARANA_LOGIN_PASSWORD>` — the
same password already gating the OAuth login page, not a second scheme.
With no password configured, REST falls back to no auth, exactly like the
MCP tools already do.

```bash
curl -X PUT "https://<host>/projects/demo/memory" \
  -H "Authorization: Bearer $SMARANA_LOGIN_PASSWORD" \
  --data-binary @state.json

curl -X POST "https://<host>/projects/demo/classify" \
  -H "Authorization: Bearer $SMARANA_LOGIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"candidate_text": "Switched session storage to Postgres.", "existing_context": "[ADR-001] Session storage: Redis."}'
```

## Semantic search over aged-out memory

`write_file` triggers `memory_index.py` on every call: it pulls superseded/
deprecated Tier 2 ADR lines and every Compressed Changelog bullet out of the
written content — the parts `consolidate-memory.md` has already compressed
down to a couple of terse lines to stay under the 120-line cap — and
(re-)indexes them into a local [Chroma](https://www.trychroma.com/) vector
store at `server/data/<project>/vector_index/`. `search_memory` queries that
index by meaning, not exact keyword, so "why did we move off X" can find the
right superseded decision even if the current `MEMORY.md` only says
"Superseded: session-cookie auth (ADR-003)."

**Free by design.** Indexing uses Chroma's default local embedding model
(`all-MiniLM-L6-v2`, via `onnxruntime`) — no API key, no per-query cost. That
model (~80MB) downloads once from Hugging Face's CDN the first time
`write_file` indexes anything, cached under `~/.cache/chroma` afterward; every
call after that first download runs fully offline. If you'd rather pre-warm
this instead of hitting it on a real write, run the test suite once (below) —
it triggers the same download.

Live Tier 1/2/3 content in the current `MEMORY.md` is **not** indexed — a
plain `read_file` already surfaces it in full, and indexing it too would just
be redundant. `search_memory` only ever helps with history that's already
been compressed away.

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
succeed), and refresh-token exchange. Requires `SMARANA_PUBLIC_HOST` and
`SMARANA_LOGIN_PASSWORD` set and the server reachable at that public host
(i.e. the tunnel needs to be up — this test talks to the real public URL,
not localhost, since OAuth's redirect/issuer URLs are the public ones):

```bash
../.venv/Scripts/python test_oauth_flow.py
```

`test_memory_index.py` and `test_server.py` (run via `python -m unittest
test_server test_memory_index -v`) cover the indexing/search logic, including
a real round-trip against a live local Chroma store — the first run of these
downloads the embedding model, subsequent runs are fast (seconds, not
minutes).

## Known limitations

Read this before relying on the server, and especially before pointing
anyone else at it:

- **No process supervision.** `server.py` and the tunnel are both plain
  foreground processes you start by hand. No restart-on-crash, no
  auto-start on boot, no health check. A machine restart silently kills
  persistence until you notice and restart both.
- **The free quick-tunnel URL is not stable.** It changes on every
  `cloudflared` restart, which then requires updating `SMARANA_PUBLIC_HOST`
  and reconnecting the claude.ai Connector. A named Cloudflare Tunnel (needs
  a domain) avoids this.
- **`oauth_store.json` never expires or prunes entries on its own.**
  Registered clients and refresh tokens accumulate indefinitely. Rotating
  `SMARANA_LOGIN_PASSWORD` stops *new* logins, but access tokens already
  issued keep working until their natural 1-hour expiry, and existing
  refresh tokens keep minting new access tokens indefinitely since refresh
  itself doesn't re-check the password. Delete `server/oauth_store.json`
  (and restart the server) for an immediate, total reset of every
  registered client and token — the only way to force everyone to log in
  again right now.
- **Schema validation only covers structured JSON writes, not Markdown
  ones.** A JSON `content` gets full `memory-schema.json` validation and
  auto-consolidation on the server (see above). A pre-rendered Markdown
  `content` only gets the hard-cap check — `engine.py` can check its line
  count but can't yet parse it back into schema-shaped state to validate
  tier structure or auto-consolidate it. A misbehaving client sending
  Markdown could still write structurally invalid content, as long as it's
  under the line/token cap.
- **`classify_fact` needs `laya` installed to do anything.** Without it,
  every call returns a clean `{"error": ...}`, never a crash — but the
  endpoint exists and returns 200 either way, so a caller has to actually
  read the `error` field rather than assume a 200 means a real
  classification happened. See `scripts/README.md` for install and the
  honest 3-10s CPU latency and calibration caveats; nothing about running
  it from the server changes those numbers.
- **No rate limiting or size limits.** Nothing stops a buggy or malicious
  client with a valid token from writing arbitrarily large content or
  hammering the server with requests.
- **Single resource owner.** This is built for one person (whoever knows
  `SMARANA_LOGIN_PASSWORD`), not multi-tenant use — every registered OAuth
  client shares the same login and the same data root.
- **The search index never garbage-collects stale entries.** `write_file`
  upserts by an id derived from each line's exact text, so an edited or
  reworded line adds a new vector rather than replacing the old one — the
  old wording stays searchable forever alongside the new. Harmless for
  correctness (both will just show up as hits), but the index only ever
  grows, never shrinks.
- **First real write after a fresh install downloads ~80MB** (the local
  embedding model) before it returns. Expected and one-time, but worth
  knowing if a `write_file` call seems to hang the first time.
