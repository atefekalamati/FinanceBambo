# BAMBO Finance Frontend Rules

## Git workflow

- The Frontend team works only on the `frontend` branch of `https://github.com/atefekalamati/FinanceBambo.git`.
- Do not commit to or rewrite Backend-owned branches.
- After a completed and verified Frontend change, commit it with a scoped message and push it to `origin/frontend`.

## Sources of truth

1. BAMBO Finance MVP PRD FA v1.1 (HTML/PDF)
2. BAMBO Finance Integration Kit v1.1.0 contracts
3. Version 1.0 sources only where version 1.1 is silent

When they conflict, the v1.1 PRD wins, then the v1.1 Integration Kit. `10_PRD_INPUT_SUMMARY_FA.md` is superseded and is never authoritative. Do not invent product behavior; mark missing behavior as undefined.

## Architecture

- Plain HTML, CSS, and vanilla JavaScript ES modules only.
- No build step, framework, TypeScript compilation, CDN, external chart library, or browser request to an external provider.
- Feature code belongs in `src/features/<feature>/`; cross-feature primitives in `src/shared/`; host/API integration in `src/core/` and `src/adapters/`.
- Features may depend on core, adapters, and shared, but not on another feature's internals.
- The host supplies validated context. Never implement BAMBO authentication or copy mock authentication into application code.

## Financial invariants

- Money, quantities, unit prices, and conversion factors are exact decimal strings at API boundaries. Never use floating point for financial calculations.
- Money and monetary unit prices are integer-IRR strings; reject every fractional form, including a zero fractional part.
- Price versions are strict append-only inserts. Same-effective-date corrections are allowed and the newest deterministic version wins; never update an older version or close it with `effectiveTo`.
- Never mutate original estimates, price history, confirmed invoices, or issued report snapshots.
- AI extraction has zero financial effect until explicit human confirmation.
- Purchased and executed/consumed quantities are different concepts.
- Never parse MPP in Finance; consume the read-only Progress Snapshot feed.
- Never derive organization/project scope from a request body.

## UI quality gates

- `lang="fa"`, `dir="rtl"`, CSS logical properties, visible focus, keyboard access, Persian labels, and accessible status/error text.
- Every page supports loading, empty, recoverable error, permission denied, and normal states.
- Confirmation, void, progress override, and report issuance require an explicit accessible modal.
- Reports print on A4; CSV is UTF-8 with BOM.
- Persian digits are display-only; API payloads use ASCII digits and ISO/UTC dates.
- Every user-facing date input uses the shared Jalali date picker and Iran timezone; convert to ASCII ISO only at the API/Adapter boundary.
- Client validation is not a security boundary. Surface server error codes, request IDs, warnings, conflicts, and field details.

## Responsive and CSS conventions

- Every new page and component must ship with its responsive behavior in the same task; responsive work is never deferred.
- Feature-specific responsive rules live in that feature's CSS file. Shared layout responsiveness lives only in the corresponding shared style file, and print rules live in print-specific files.
- Keep CSS readable and block-formatted: one declaration per line, consistent indentation, and one blank line between consecutive selectors/rules.
- Do not write compressed single-line CSS rules by hand.
- Organize long CSS files into clearly named comment sections following the structure used by the token files.
- Prefer existing BAMBO tokens over literals. New reusable values belong in the appropriate token section before use.

## Delivery tracking

- `docs/PROJECT_PROGRESS_FA.md` is the live source of truth for implementation status, priorities, estimates, dependencies, and next work.
- Update the progress document after every completed feature or material scope change.
- Work follows the documented P0 → P1 → P2 order unless the user explicitly changes priority.
- A feature is not complete until normal/loading/empty/error/denied states, permissions, validation, responsive behavior, accessibility, print where relevant, and tests are handled.
- Report progress by weighted product scope and acceptance gates, not by file count or visual completeness.
