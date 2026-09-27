# GDPR Compliance Mapping (Phase 22)

**Compliance target: GDPR.** Named, not assumed — gap #2 in
`docs/V1_ARCHITECTURE.md`'s closing list was explicit: "'most secure
system' isn't a spec until you pick a target." The target follows from
who this platform actually serves: any customer, any region, including
the EU. GDPR is binding the moment EU personal data is processed,
regardless of company size or where the company itself is based — the
most stringent of the regimes that were on the table, and the one that
applies by default given that answer.

This document maps GDPR's actual articles to what this codebase provides,
what this phase newly closes, and what stays an organizational or legal
responsibility no amount of code can discharge. The same discipline
`docs/THREAT_MODEL.md` and `docs/V1_ARCHITECTURE.md` already established:
name a gap, never pad around it, never claim code solved a business or
legal question.

## Data subject rights (Chapter III)

| Article | Right | What this codebase provides |
|---|---|---|
| 15 | Right of access | `data_subject_rights.export_data_subject()` — every memory referencing a person, as portable JSON. |
| 17 | Right to erasure | `data_subject_rights.erase_data_subject()` — genuinely deletes, not `retention.py`'s `FORGOTTEN` marker (see below for why that distinction matters). |
| 20 | Data portability | Same export function; JSON round-trips through `MemoryObject.model_validate()`, the same shape `backup.py` already uses. |
| 16 | Right to rectification | `MemoryObject.new_version()` (Step 32) plus `mark_superseded()` (Step 35) — already real, from Phase 6, not new this phase. A correction is an Old→Correction→New chain, not an in-place mutation, which is a *stronger* guarantee than rectification requires (the old value stays auditable), not a gap. |
| 21 | Right to object | Not a distinct code mechanism — objecting to processing is answered by *not processing* (Article 17 erasure, or `PolicyEngine.can_use_for_reasoning` returning deny) once the objection is received. No new code needed beyond what Articles 15/17 already give a controller. |

**`data_subject_ids` is a new field, not automatic.** GDPR's rights
belong to a *person*, not a tenant or an agent — `owner_id` in this
codebase usually names the agent/system managing a memory, a different
question from whose personal data it contains. A caller creating a
memory about a real person has to actually set `data_subject_ids`;
nothing infers it from `content` (that would mean parsing free text for
PII, a real capability this phase does not build and does not claim to).
**This is the actual, honest gap**: a controller using this codebase
must populate `data_subject_ids` at write time for erasure/access
requests to find everything relevant later. Not doing so doesn't violate
anything this codebase enforces; it does mean an Article 17 request
against that data would miss memories that were never tagged.

**Why erasure genuinely deletes and retention doesn't.** Phase 21's
`sweep_expired_memories()` marks a tenant's aged-out memories
`FORGOTTEN` — never physically removed, per Step 35's "a memory never
silently disappears." Article 17 is GDPR's own deliberate exception to
that default: a specific person's data must actually be removable on
request. `erase_data_subject()` calls `StorageAdapter.delete()`
directly, not `new_version(lifecycle_state=FORGOTTEN)`. These are two
different operations answering two different questions, not one
mechanism with two settings.

## Lawful basis and consent (Articles 6-7)

No new field. `MemoryObject.tags` (Phase 21) is the existing, correct
extension point — a controller records a lawful basis (`"lawful_basis:
consent"`, `"lawful_basis:contract"`, etc.) as a tag at write time.
Building a second, GDPR-specific field alongside `tags` and
`privacy_categories` would be exactly the kind of proliferating,
barely-distinct mechanism this codebase's own discipline avoids — reuse
what already exists rather than adding a third way to tag a memory.

## Security of processing (Article 32)

Already real, from earlier phases, cited here rather than rebuilt:
tenant isolation enforced at both the application layer (`tenant_id`,
`can_access_tenant`, Step 81) and the database layer (Postgres
Row-Level Security, Step 82); `PrivacyLevel`/`PrivacyCategory`
classification (Step 83); `FernetEncryptor` (Step 85); `AuditLog`
(Step 84); non-optional `PolicyEngine` enforcement at the REST and MCP
boundaries (Steps 96/98, closing `THREAT_MODEL.md`'s own named gap).
Article 32 doesn't ask for anything this codebase doesn't already do;
it asks for evidence, which `GATES.md`'s 35 gates and 349 tests are.

## Data residency and international transfers (Articles 44-49)

**Newly closed, partially.** `TenantProfile.data_residency_region`
(Phase 22) lets a controller *record* that a tenant's data must stay
within a named region. It does **not enforce** it: which physical region
a `PostgresAdapter`'s database actually runs in is an infrastructure and
deployment decision — which host, which cloud region — not something
Python code running inside an already-provisioned database can control
or verify. This closes the "record the requirement" half of gap #7 in
`V1_ARCHITECTURE.md`'s list; the "enforce it" half remains a deployment
responsibility, named here rather than silently assumed solved.

## Records of processing (Article 30)

**Not closed, named honestly.** `AuditLog` (Step 84) records
who/what/when/why/source/result per operation — real, but it is an
operational log, not Article 30's structured register of processing
*activities* (categories of data, purposes, recipients, retention
periods, described at the organizational level). Building a real
Article 30 register is a different kind of artifact than this
codebase's own code and tests can produce on a controller's behalf; it
requires organizational input (who processes what, why) this codebase
has no way to know. `TenantProfile` (industry, retention, data
residency) is a real input to writing one, not a substitute for it.

## Breach notification (Articles 33-34)

**Not closed, named honestly.** The 72-hour notification requirement is
a *process*: detecting a breach, deciding it's notifiable, and telling
the supervisory authority (and affected people, if high-risk) inside a
deadline. `AuditLog.denials()` (Step 84) and per-request logging at the
API/MCP boundary (Step 96/98) are real forensic building blocks — they
are what an incident response process would query first. They are not
an incident response process: no code here decides "this is a breach,"
alerts anyone, or starts a clock. Building an actual anomaly-detection
and alerting system is a substantial, separate security engineering
project this phase does not attempt, rather than fake with a stub that
would give false confidence.

## Privacy by design and DPIAs (Articles 25, 35)

**Not closed, named honestly.** Article 25 ("privacy by design and by
default") is largely already true of this codebase's architecture — the
Core-vs-Adapter isolation, tenant walls checked before permission grants
(Step 81), `PrivacyLevel` defaulting to `INTERNAL` rather than `PUBLIC`
— but Article 25 as a *compliance control* is demonstrated by a Data
Protection Impact Assessment for a specific deployment, which needs
organizational input (what data, whose, why, what risk) no generic
codebase can supply for every possible deployment. `docs/THREAT_MODEL.md`
and this document are real inputs to writing one; neither is a DPIA
itself.

## What stays entirely organizational or legal

Named once, not repeated per section: a Data Protection Officer
appointment (if required — Article 37), Data Processing Agreements with
every subprocessor (a cloud host, Anthropic for the Claude adapter, any
other vendor in the stack), an EU representative (Article 27, if the
controller isn't established in the EU), and the actual breach
notification runbook (who calls whom, within the 72 hours). None of
these are code problems. Naming them here is what keeps this document
honest about the difference between "GDPR-aware architecture" and
"GDPR compliant deployment" — this codebase can be the former; only an
actual organization, with actual legal counsel, can make a specific
deployment the latter.
