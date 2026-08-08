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
```

**No token/password gate.** claude.ai's Custom Connector dialog only
supports OAuth or no auth — it doesn't offer a field for a static bearer
token, so an earlier version of this server that required one couldn't be
connected at all ("Couldn't register with Authorization: Bearer ...'s
sign-in service"). Instead, the tunnel URL itself is the secret: anyone who
has it can read/write your memory files, so never share it, and if you
think it leaked, just restart the tunnel — that mints a fresh random URL
and the old one stops working.

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
time. A named tunnel avoids that churn.

## 4. Add it as a Connector in claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://<your-tunnel-domain>/mcp`
3. Leave authentication unset/none — don't fill in an OAuth Client ID field
   if the dialog shows one; this server doesn't implement OAuth.
4. Enable the connector for the specific Project(s) that should use it.

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
