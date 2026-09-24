# Invoice AI — Hardening & Handoff

**Date:** 2026-09-24
**Starting commit:** `7f853211` (Merge remote-tracking branch 'origin/master')
**Ending commit:** none — nothing was committed. The project workflow requires an explicit
instruction to commit, and none was given for this task. The changes sit in the working
tree, listed below.

No secret value appears anywhere in this report.

---

## 1. Files changed

| File | Change |
|---|---|
| `backend/devhost/environment.py` | `export_env_file()` became an allowlist; added `extraction_environment_names()` |
| `backend/extraction/adapters.py` | added `_currency_without_evidence()` and wired it into `_as_contract` |
| `backend/tests/test_extraction_configuration.py` | allowlist regression tests; `MANAGED` derived from the allowlist |
| `backend/tests/test_currency_evidence.py` | **new** — 13 tests for the currency rule |
| `.env` (untracked) | rotated password; removed one stray credential-shaped line |

No migration. No frontend file. No change to `contracts/openapi.json` (`--check`: current,
86 paths). No change to the Invoice AI architecture.

---

## 2. Database credential rotation — **DONE**

| | |
|---|---|
| Role | `bambo_finance_app` |
| Host | `127.0.0.1:5432` (local development server) |
| Database | `bambo_canonical_test` |
| Configured in | `.env` → `FINANCE_DEV_DSN` (untracked), plus the session scratch DSN file |

Established before touching anything: the role exists **only** on the local server (0
matching roles on the production-like host `192.168.100.200`), it owns **0 tables**, and
`bambo_canonical_test` is explicitly outside the repository's own
`PROTECTED_DATABASES = {"bambo", "bambo_canonical_local"}`. So this is a development
credential and rotating it cannot affect production.

A 48-character URL-safe password was generated with `secrets.token_urlsafe`, applied with
`ALTER ROLE`, and written to `.env` and the scratch DSN. It was never printed, never put in
source, and `.env` is git-ignored. Role attributes were captured before and after and are
identical — only the secret changed.

- new credential: **works** (verified by connecting, and by running the backup with it)
- old credential: **still accepted locally — see below**

### The finding that matters more than the rotation

The local server authenticates loopback connections with `trust`:

```
line 115  host  all  all  127.0.0.1  trust           ← no password is checked, any role
line 117  host  all  all  ::1        trust
line 123  host  bambo_canonical_test  all  192.168.100.0  scram-sha-256
```

Verified directly: a deliberately wrong password and an **empty** password are both
accepted from `127.0.0.1`.

So rotation **did** close the network path — line 123 enforces `scram-sha-256`, and the
leaked password was the only thing protecting that route. It **cannot** close the loopback
path, because no credential is verified there at all. Anyone who can reach
`127.0.0.1:5432` on this machine already has unauthenticated access to every database and
every role, including `postgres`.

**This is not fixed and was not attempted.** The remedy is changing lines 115/117 to
`scram-sha-256` and reloading, which is a server-configuration change affecting every
other client on the machine — other git worktrees, pgAdmin, the devhost, any tooling that
has no stored password. That belongs to whoever owns this workstation, not to this task.

---

## 3. Secret audit — **DONE**

4,714 files scanned (tracked and untracked; `.git`, virtualenvs and `node_modules`
excluded).

| File | Secret type | State | Action |
|---|---|---|---|
| `.env` | AvalAI key, DSNs | untracked | KEEP LOCAL — `.gitignore:2` covers it; verified not tracked |
| `.env.example` | DSN shape | TRACKED | NO ACTION — password is the literal `CHANGE_ME` |
| `backend/devhost/README_FA.md` | DSN shape | TRACKED | NO ACTION — `user:pass@` placeholder |
| `backend/docs/DATABASE_SCHEMA_OVERVIEW_FA.md` | DSN shape | TRACKED | NO ACTION — `USER:PASSWORD@HOST:PORT` |
| `backend/docs/PRODUCTION_ENVIRONMENT_FA.md` | DSN shape | TRACKED | NO ACTION — `<owner_role>:<password>@<host>` |
| `backend/tests/test_devhost_connection.py` | DSN shape | TRACKED | NO ACTION — fixture placeholder, host `db.internal` |
| `backend/tests/test_mpp_files.py` | DSN shape | TRACKED | NO ACTION — `user:password@db` |
| `backend/tests/test_runtime_database_lock.py` | DSN shape | TRACKED | NO ACTION — `{host}:{port}` template |
| `delivery/INSTALL_UPGRADE_ROLLBACK_FA.md` | DSN shape | TRACKED | NO ACTION — `<owner>:<pass>@<host>` |
| `.run/43127-*.out.log` | DSN with a password | untracked | git-ignored; now stale after rotation. **Recommend deleting.** |

**No real secret exists in any tracked file.** Every tracked hit is a documented
placeholder, confirmed by inspecting the value shape without printing it.

Two further findings:

1. **A stray credential fragment was sitting in `.env`** — a bare 14-character line with no
   `=`, which is a substring of the **postgres superuser** password. `load_env_file` skips
   lines without `=`, so nothing ever read it, but it was a credential loose in a config
   file. **Removed.** The superuser password itself also lives in the session scratch file
   and should be considered for rotation by the owner of this machine; this task did not
   rotate it (unrelated credential).

2. Benchmark reports and test outputs were included in the scan. None contains a credential.

---

## 4. Environment hardening — **DONE**

The previous phase's `export_env_file()` exported the **whole** `.env` into `os.environ`.
That put `FINANCE_MIGRATION_DSN` — the owner role permitted to run DDL — into the process
environment of a host whose application role deliberately cannot, and into every subprocess
that host spawns, to solve a problem only the AI settings had.

It is now an allowlist, and the allowlist is **derived from the providers' own
declarations** (`PROVIDER_SETTINGS`, `KEY_NAMES`, `MODEL_NAMES`, `BASE_URL_NAMES`) rather
than hand-written, so it cannot go stale when a provider gains a setting.

Exported (13 names): `AVALAI_API_KEY`, `AVALAI_BASE_URL`, `AVALAI_MODEL`,
`AVALAI_STT_MODEL`, `AVALAI_VISION_MODEL`, `FINANCE_AI_API_KEY`, `FINANCE_AI_BASE_URL`,
`FINANCE_AI_EXTRACTION_ENABLED`, `FINANCE_AI_MODEL`, `FINANCE_AI_PROVIDER`,
`FINANCE_AI_VISION_MODEL`, `FINANCE_STT_MODEL`, `FINANCE_STT_PROVIDER`.

Withheld: `FINANCE_DEV_DSN`, `FINANCE_MIGRATION_DSN`, `APP_ENV`, `DEBUG`,
`FRONTEND_ORIGIN`, and any line whose name is not a valid identifier. The database settings
still resolve, because `database_url()` and `migration_url()` read the file through
`setting()` and never needed `os.environ`.

A deliberate export still wins over the file. The host prints the **names** it picked up
and never a value. Verified live: the running host reports 9 names from `.env`, no DSN
among them, with speech and AI both configured.

---

## 5. Currency inference fix — **DONE**

`gemini-2.5-flash-lite` answered `currency: TOMAN` on `page2.jpg`, which prints neither
`تومان` nor `ریال`. It arrived at confidence 0.855 — above the review threshold — so nobody
would have been asked, and the two candidate answers are a factor of ten apart.

The fix is deterministic, not a prompt. `find_currency` already decides the question from
the text and is what the deterministic parser uses; it is now the evidence test for the
model's answer:

- source states a currency word → the model's currency stands
- source states none → **no currency is recorded**, and a `currencyWarnings` field says why
- nothing is converted: `تومان` → `IRT` and `ریال` → `IRR` stay distinct, and neither is
  rewritten into the other. Normalisation stays downstream where the unit is known.

Verified on the real pipeline, both directions:

| Page | States a currency word | Result |
|---|---|---|
| `page2.jpg` | no | **no currency field** + `currency-unevidenced` warning ✔ matches ground truth |
| `page3.jpg` | yes (`ريال`) | `currency: IRR` kept ✔ |

Monetary accuracy is unchanged by the guard: page2 still reads **9 of 9** line totals
exactly, with `invoiceNumber` and `totalAmount` correctly withheld.

---

## 6. Path regression — all three **PASS**

| Path | Result |
|---|---|
| **Manual** | `POST /invoices` → `PATCH` to `awaitingConfirmation` → confirm → invoice **006** confirmed |
| **Image** | `page2.jpg` → draft v22, 9/9 totals exact, currency correctly absent |
| **Voice** | `voice1.wav` → draft via `avalai-speech`, transcript preserved, spoken 107,786,000 kept |

### Review · edit · reject · retry · confirm

- **edit** — `PATCH /extractions/{id}`: v22 → v23, Persian intact, still `awaitingReview`,
  effect 0
- **reject** — draft → `rejected`, effect 0, `confirmed_by`/`confirmed_at` null, project
  totals unchanged
- **retry** — new draft id and version on both image and voice; history preserved
- **confirm** — invoice **007** created, project total moved by exactly +7,777,000
- **duplicate confirmation** — confirming the identical body twice returned the **same**
  invoice 007 with HTTP 200 and the totals did not move. Separately, an attachment that
  already produced a confirmed invoice refuses a second one (`file is already linked`,
  enforced with `FOR UPDATE` inside the transaction)

---

## 7. Financial safety — **PASS**

Across the whole table, straight from the database:

```
drafts with non-zero financial_effect_irr      0   (must be 0)
accepted        n=4    confirmed_by=4   confirmed_at=4
awaitingReview  n=56   confirmed_by=0   confirmed_at=0
rejected        n=2    confirmed_by=0   confirmed_at=0
unaccepted drafts carrying a confirmer         0   (must be 0)
attachments linked to a non-confirmed invoice  0   (must be 0)
alembic revision                            0037   (unchanged)
```

No rejected draft changed any financial total.

---

## 8. Provenance — **PASS**

`rawText`, `voiceTranscript`, `source`, `speechProvider` and `extractionSource` are listed
in `PROVENANCE_KEYS` and refused by the edit endpoint. Verified live: an attempt to edit
`rawText` returned **422** naming the field; after an accepted edit to `supplierName`, every
provenance field's `extractedValue` was byte-identical to before, the correction landed in
`confirmedValue`, and `editedByUser` was set.

---

## 9. Models — unchanged, configuration-driven

```
STT     groq.whisper-large-v3-turbo    FINANCE_STT_MODEL
VISION  gemini-2.5-flash-lite          FINANCE_AI_VISION_MODEL / AVALAI_VISION_MODEL
TEXT    gpt-4o-mini                    FINANCE_AI_MODEL / AVALAI_MODEL
```

A test parses `adapters.py` and asserts no model name appears as a string constant outside
docstrings, so the adapter cannot acquire a hard-coded model.

---

## 10. Tests

```
baseline (start of task)   2422 passed, 0 failures
final                      2444 passed, 4645 subtests, 0 failures
```

+22 tests: 13 for the currency rule, 9 for the export allowlist. No existing test was
weakened; one (`MANAGED`) was corrected to derive from the allowlist after it leaked state
between cases.

---

## 11. Backups

| | Pre-rotation | Post-rotation |
|---|---|---|
| Path | `C:\BAMBO_BACKUPS\bambo_canonical_test_20260924_024307.dump` | `C:\BAMBO_BACKUPS\bambo_canonical_test_20260924_030240.dump` |
| Size | 6,149,459 bytes | 6,152,641 bytes |
| SHA256 | `330001b9cdb0b52a06944d51b0afee708d96fbc2643e9009d098bff4ac9cde47` | `0f5c6bc41e02ab3be1ec3c554ad2557b56cd42bb6d1d476ff75ee8c709bbb5fb` |
| Validation | `pg_restore --list` exit 0, 724 entries, 84 table-data entries | same |

Both taken with the repository's own `scripts.ops.backup_canonical_test`, which matches
`pg_dump` to the server major version and refuses a suspiciously small archive. The
post-rotation backup also proves the new credential works for the backup tooling.

---

## 12. Known remaining issues

1. **Loopback `trust` authentication (highest priority).** Lines 115/117 of the local
   `pg_hba.conf` accept any password from `127.0.0.1`/`::1` for every role including
   `postgres`. Password rotation cannot compensate. Needs `scram-sha-256` + reload, by the
   owner of this workstation.
2. **The postgres superuser password** is stored in a session scratch file and a fragment of
   it was loose in `.env` (now removed). Consider rotating it; this task did not, being an
   unrelated credential.
3. **`.run/*.log`** contain a DSN with the now-rotated password. Git-ignored, but worth
   deleting.
4. **`FINANCE_DEV_DSN` in `.env` names port 55432**, which is closed; the working server is
   on 5432. Pre-existing, left alone deliberately — the devhost is launched with an explicit
   `--dsn`. Worth correcting separately.
5. **Image + Voice fusion** remains unimplemented, as instructed.

---

## 13. Production readiness

**NOT PRODUCTION READY**, for one reason that is not about this code: the database this was
verified against authenticates loopback connections with `trust`. Item 1 above must be
closed before any claim about production security.

The application-level work of this task is complete and verified: the credential is
rotated, no real secret is in tracked source, the environment export no longer hands the
owner credential to subprocesses, currency can no longer be guessed, and all three invoice
paths plus review/edit/reject/retry/confirm behave correctly with the financial invariant
intact.

---

# Addendum — 2026-09-24: PostgreSQL loopback authentication

Item 1 above ("loopback `trust`") was worked on. It is **partly closed**, and the part that
remains open is documented here rather than left implied.

## The instance

| | |
|---|---|
| Service | `postgresql-x64-16` (16 and 17 and 18 all run here; only 16 was touched) |
| Version | PostgreSQL 16.15 |
| Port | 5432 |
| Data directory | `C:/Program Files/PostgreSQL/16/data` |
| hba file | `C:/Program Files/PostgreSQL/16/data/pg_hba.conf` |
| Login roles present | `postgres`, `bambo_finance_app` — and no others |

`bambo_canonical_test` is on this instance. Both roles hold a SCRAM verifier.

## What was changed

Two rules were **added** above the existing loopback rules. Nothing was modified, removed
or reordered:

```
host    all    bambo_finance_app   127.0.0.1/32   scram-sha-256      (new)
host    all    bambo_finance_app   ::1/128        scram-sha-256      (new)
host    all    all                 127.0.0.1/32   trust              (unchanged)
host    all    all                 ::1/128        trust              (unchanged)
```

PostgreSQL takes the first match, so the application role now needs its password on
loopback and every other rule behaves exactly as before. `pg_hba_file_rules` reports 0
parse errors. Reload was by `pg_reload_conf()`; the service was never stopped or restarted.

Backup: `C:\BAMBO_BACKUPS\pg_hba.conf.16.pre_scram_20260924_031000.bak`
(sha256 `9E2E05122DA82C0417E40824A3E61E5797A07D4FBBF4E82935978BCE1ABD28D8`).

## Why `postgres` was left on trust

The first attempt replaced `trust` with `scram-sha-256` on both loopback rules. The server
applied the new rules immediately and the next connection as `postgres` was refused:
**password authentication failed**. The value this workstation kept for that role had only
ever been accepted *because* of trust and had never been verified against it.

So the real `postgres` password is unknown here. Forcing SCRAM for all roles would lock the
workstation owner out of their own superuser, which the brief explicitly forbids. The change
rolled itself back automatically, and the narrower rule above was applied instead.

## What this does and does not achieve

**Closed:** the BAMBO application credential can no longer be bypassed. A wrong password and
an empty password are both rejected for `bambo_finance_app` on loopback; the rotated one is
accepted.

**Still open:** anyone with local access to this machine can still connect as `postgres`
without a password. The instance is therefore still fully reachable by a local actor, and
this is a workstation posture issue, not an application one.

To close it, the owner must set a known password for `postgres`
(`ALTER ROLE postgres PASSWORD '…'` while trust is still in effect), confirm it
authenticates, and only then change the two remaining `trust` rules to `scram-sha-256`.
That sequence is safe precisely because trust is still there while it is done. It was not
performed here because it changes the workstation owner's own admin access.

## Verification after the change

- application role: correct password accepted · wrong rejected · empty rejected
- devhost restarts, connects, and serves; STT and Vision configuration unchanged
- a live voice extraction still runs
- financial invariants unchanged: 0 drafts with non-zero effect; 4 accepted all with
  `confirmed_by`/`confirmed_at`; 56 awaiting and 2 rejected with neither; 0 attachments
  with more than one accepted draft
- full suite: 2444 passed, 4645 subtests, 0 failures — identical to baseline
- final backup: `bambo_canonical_test_20260924_032245.dump`,
  sha256 `5d7718d8dcd88dbb97902c9c69b6422e0c28faf03071f5e5ac4eac0d2fd99e76`, validated

Two stale log files carrying a DSN with the pre-rotation password were removed; both were
untracked and git-ignored. `.env` now has no malformed or duplicated entries. No repository
file was changed by this task.

---

# Addendum 2 — 2026-09-24: loopback `trust` fully removed

The item left open in Addendum 1 is now **closed**. No rule on this instance uses `trust`.

## What was done, in the order that makes it safe

1. `pg_hba.conf` backed up to
   `C:\BAMBO_BACKUPS\pg_hba.conf.16.pre_superuser_scram_20260924_033000.bak`,
   verified byte-identical to the live file.
2. **While trust was still active**, a 48-character URL-safe password was generated and
   applied to `postgres` with `ALTER ROLE`, under `password_encryption = scram-sha-256`.
3. **The password was proven without a connection.** Under trust, connecting proves
   nothing — any password is accepted, which is exactly how the previous attempt went
   wrong. So the stored SCRAM verifier was read from `pg_authid` and the same derivation
   (PBKDF2-HMAC-SHA256 → ClientKey → StoredKey, and ServerKey) was recomputed here from the
   new password. Both keys matched, which settles the question independently of the
   authentication rules.
4. Only then were the two remaining rules changed from `trust` to `scram-sha-256`.
5. Reloaded with `pg_reload_conf()`. The service was never stopped or restarted.

## Where the password lives

`%APPDATA%\postgresql\pgpass.conf` — the standard libpq credential file, outside the
repository and outside git. Every PostgreSQL client tool reads it automatically, so the
workstation owner's existing tooling keeps working without typing anything; this was
verified by connecting as `postgres` with no password supplied.

The value appears in no tracked file, no git diff, no log and not in this report.

## Effective rules

```
local  all                   all                 scram-sha-256
host   all                   bambo_finance_app   127.0.0.1/32      scram-sha-256
host   all                   bambo_finance_app   ::1/128           scram-sha-256
host   all                   all                 127.0.0.1/32      scram-sha-256   (was trust)
host   all                   all                 ::1/128           scram-sha-256   (was trust)
local  replication           all                 scram-sha-256
host   replication           all                 127.0.0.1/32      scram-sha-256
host   replication           all                 ::1/128           scram-sha-256
host   bambo_canonical_test  all                 192.168.100.0/24  scram-sha-256
```

Rules using `trust`: **0**. Parse errors: **0**. The two `bambo_finance_app` rules from
Addendum 1 are now redundant but were left in place rather than removed, because removing
a rule is a larger change than this task needed.

## Verification

| Check | Result |
|---|---|
| `postgres` correct password | PASS (accepted) |
| `postgres` wrong password | PASS (rejected) |
| `postgres` empty password | PASS (rejected) |
| `postgres` via credential file, nothing typed | PASS |
| `bambo_finance_app` existing password | PASS (accepted) |
| devhost restart + database connection | PASS |
| `/healthz/live`, `/healthz/finance` | 200 |
| `/extractions`, `/invoices`, `/resources`, `/material-prices/current`, `/summary` | 200 |
| Financial invariants | 0 drafts with non-zero effect; 4 accepted all with confirmer; 56 awaiting and 2 rejected with none |
| Full suite | 2444 passed, 4645 subtests, 0 failures |
| Final backup | `bambo_canonical_test_20260924_034242.dump`, sha256 `08563a7221e5880d2912ce1f3b6fa6f003eef0644e1434b1fdb516d53d9f3fe8`, `pg_restore --list` OK |

Negative tests were run with `PGPASSFILE` pointed at a non-existent path, so the credential
file could not rescue a wrong or empty password.

No repository file was changed by this task. No migration, no frontend, no model change.
