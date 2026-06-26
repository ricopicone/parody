# Resuming task #297

**Task:** Equation numbers should be shown to the right of numbered equations

## Project memory
_Durable, shared context for this project. Read a full entry with `get_project_memory(name=…)`._

- **rtcbook-deploy-release-chain** (reference) — Shipping a parody/parody-web change to rtcbook.org is a 6-step cross-repo release chain (publish both packages to PyPI first); watch the PyPI simple-index propagation race on deploy
- **eq-def-infobox-crossref-anchoring** (architecture) — Task 306 DONE + SHIPPED + DEPLOYED: build-side anchoring of equation/definition/infobox cross-ref targets; rtc ed1+ed2 unresolved hashrefs 11 to 0; live on rtcbook.org
- **parody-web-reader-features** (architecture) — parody-web reader features added in #292: subject index page (+deep-link anchors), search inside, MathJax macros/packages
- **crossref-labels-follow-key-case** (decision) — Cross-ref label case follows the reference site for ALL ref kinds (figures, tables, eqs, sections, chapters, …); lookup case-insensitive; equations parenthesized
- **edition-urls-query-plus-printed-codes** (decision) — Editions addressed by ?ed=<id> query (not /editions/ path); printed short codes /q9 302-redirect to latest edition that has them
- **subfigure-web-rendering-and-fig-migration** (architecture) — Subfigure web rendering SHIPPED (parody-web 0.5.0 + filter.lua); rtc raw-LaTeX figure migration blocked on third-party rights decision
- **rtc-crossref-gap-diagnosis-and-fixes** (status) — rtcbook cross-ref audit (task #292): 307→223 unresolved fixed via build/render; remaining 223 are raw-LaTeX-migration content
- **editions-released-and-p2app-blocked** (status) — Editions fully SHIPPED incl. live on rtcbook.org: ed2 is an owner-only DRAFT (placeholder T2/D2) on production; public sees only ed1. parody 0.9.0 + parody-web 0.4.0 on PyPI.
- **draft-editions-and-ci-green** (architecture) — Draft editions shipped (parody 0.9.0 + parody-web 0.4.0): build an edition owner-only via draft:true, release live with publish_edition. Both repos' CI now green.
- **editions-p2-parody-web** (architecture) — P2 render core done in parody-web: multi-edition hosting (Book-per-edition), edition switcher (default latest), edition URL scheme, deploy.sh glob import
- **editions-p1-implementation** (architecture) — P1 done in parody: editions: schema + single-source overlay fork + one-artifact-per-edition build (concrete conventions)
- **parody-teal-summit-is-live-line** (decision) — SUPERSEDED 2026-06-22: dev consolidated onto main; main is now the live line (0.6.4, = PyPI). teal-summit no longer ahead.
- **table-caption-id-from-table-identifier** (gotcha) — pandoc 3.6.1 puts a table caption's trailing {#id} on the Table's identifier, not the caption text — print.lua must read el.identifier
- **rtcbook-web-rendering-backlog** (status) — rtcbook.org rendering fixes: done; architecture now clean (logic in parody/parody-web)
- **versioning-redesign-spec** (decision) — Agreed design for parody edition-aware versioning (T1/D1=ed1, T2/D2=ed2) + per-variant parts pages
- **rtcbook-web-aws-infra** (reference) — rtcbook.org EC2 deploy: LIVE over HTTPS; resource IDs + state (acct 226466052849, us-west-2)
- **repo-map-and-homes** (reference) — Where every parody-related repo lives on GitHub (all pushed as of 2026-06-20) — for resuming on any machine
- **rtc-meta-source-location** (reference) — The current rtc meta source is github.com/rtc-book/* (NOT the stale gitlab/ricolab clone at ~/real-time-computing); local working copies under ~/rtcbook
- **parody-book-host** (reference) — parody-web (github.com/ricopicone/parody-web; formerly parody-book-host): installable Django app rendering parody artifacts as book sites; book-agnostic, reused per book; public sees online-only, owner login sees full book; AWS/SSM deploy v
- **homepage-django-v2-textbook-import** (decision) — homepage importer consumes parody v2 textbook artifacts (rtc imported, gated as a restricted notebook); models/migration/importer + appendix-flag fix + restricted-notebook owner gating, all merged to main
- **rtcbook-partial-web-publication** (decision) — rtcbook.org publishes only the partial (online-only) rtc book; parody marks online_only + online_resources and emits a partial artifact via build --online-only; renderer is a dedicated Django book-host
- **pipeline-aware-transforms-and-partslist** (architecture) — Plugins can be pipeline-aware (content_transforms passes target); parts-list plugin generates the web hardware catalog from versions.yaml
- **plugin-hook-kinds-and-apocrypha** (architecture) — Plugins: two hook kinds (make_transform, make_artifact_hook). Artifact-hook plugins: apocrypha, book (bookmeta), videos — the full book-json trio
- **plugin-architecture-and-versioning** (architecture) — Plugins = content transforms activated by their parody.yaml config key; versioning plugin does named tracks (rtc ts/ds or single-track), inheritance-flattened versions DB, span substitution with warnings
- **latex-to-md-converter-exposure** (decision) — latex-to-md-filter.lua is unreliable and diverged per book; only rtc has heavy latex-only exposure (~16 prose + 12 exercises) — unify+test the converter before rtc, not before
- **latex-source-sections-policy** (decision) — Raw-LaTeX section sources are converted once at migration; markdown is the sole canonical source afterward — no .tex sections in parody
- **pandoc-walk-inlines-before-blocks** (decision) — In one pandoc Lua filter table, inline handlers run before block handlers — never register Image alongside Figure in the same walk
- **xsim-verbatim-and-filter-generated-figures** (decision) — Two meta-book migration gotchas: xsim can't collect verbatim (parody externalizes minted to \input side files), and latex-to-md-filter.lua generates figure dirs with fresh hashes per run
- **book-inventory-migration-order** (reference) — Canonical list of books/notes to migrate: 4 meta-based (math first, rtc last) + 3 non-meta sets with same effective structure
- **name-and-port-conventions** (convention) — Name "parody" (play on parity, PyPI-available); ported ancestor code stays near-verbatim until homepage migrates
- **pandoc-pin-golden-parity** (decision) — pandoc is pinned to 3.6.1 via pypandoc-binary==1.15; golden artifacts depend on it

---
_Manage your context as you work — `project_slug="parody"`, `task_id=297`:_
- **Briefing** — before you pause/wrap up, `write_task_briefing(…)`: a concise “where things stand / next steps” so the next session resumes cleanly.
- **Task** — `set_task_next_action`, `edit_task`, `set_task_block`/`clear_task_block`, `complete_task` (or the dashboard’s **Done**).
- **Project memory** — when you learn something durable & project-wide (a convention, decision, gotcha), `add_project_memory` / `update_project_memory` so every future session across the project inherits it.
