# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 2.1.x | Yes |
| 2.0.x | Security fixes only |
| < 2.0 | No |

## Reporting a vulnerability

**Do not open a public issue for a security report.**

Use GitHub's private vulnerability reporting (Security → Report a vulnerability) on this repository, or email <hardikdanej11@gmail.com> with `SECURITY` in the subject line.

Please include what you were doing, what you observed, and a minimal reproduction if you have one. Expect an acknowledgement within 5 business days.

## Threat model

Smaraṇa is a specification for how an AI assistant sorts and persists project state. It ships no server, no network client, and no runtime dependencies. The realistic risks are about **what ends up written into `MEMORY.md`**, and they are worth stating plainly:

- **`MEMORY.md` is not a secret store.** It is designed to be uploaded to a Claude Project's Knowledge, pasted between sessions, and read by an assistant every session. Never let credentials, tokens, API keys, or personal data into it. The example file's Tier 3 rule about not logging raw tokens is there for a reason.
- **Memory is an injection surface.** Anything written into `MEMORY.md` is read back as trusted context in later sessions. If untrusted content — a scraped page, a third-party file, a pasted log — can reach Tier 2 or Tier 3 unchecked, it becomes a persistent instruction the assistant carries forward. Phase 2 Tier Resolution is a triage step, not a security boundary; treat the provenance of a fact as your responsibility, not the pipeline's.
- **MCP persistence writes to a real filesystem.** In `PERSISTENCE_MODE = MCP`, Phase 4 writes through whatever filesystem or memory server is connected. The path it writes to is only as constrained as that server's own configuration.

Reports that amount to "the reference implementation in `tests/` crashes on malformed input" are welcome as ordinary bugs, not vulnerabilities — that code is a test harness and is never in an execution path with untrusted input.
