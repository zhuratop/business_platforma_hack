# A0 — contracts

Authoritative DTO: `backend/app/domain/contracts.py`, frontend: `frontend/src/types.ts`.
All JSON responses: `{id, status, data}`; failures `{id:null,status:"error",error:{code,message,details}}`.
Authentication: opaque HttpOnly session cookie. Ownership checked for every object.

API prefix `/api`: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`;
`GET /bootstrap`; `GET /datasets`, `POST /datasets/register`, `POST /datasets/upload`, `GET /datasets/{id}`;
`GET/POST /scripts`, `POST /scripts/upload`, `POST /scripts/validate`;
`GET/POST /configs`; `GET/POST /runs`, `GET /runs/{id}`, `/events`, `/scripts/{snapshot_id}`;
`GET /runs/{id}/summary`, `/stats`, `/checks`; `POST /runs/{id}/checks`;
`POST /runs/{id}/pivot`, `/pivot/apps`; `GET /runs/{id}/apps/{app_id}`;
`GET /runs/{id}/report.html`.

Pivot uses only whitelisted dimensions, unique APP_ID and full fact memberships.
Signed cell tokens include run, dimensions and filters; details highlight matching PATH/ARRAY_KEY.
Check-only execution publishes a new atomic report version without modifying DuckDB.
Full procedures are snapshot into a new run. Python signatures follow tech_spec §3.

Pivot dimensions additionally include `ADJUSTED_BEFORE`, `ADJUSTED_AFTER`;
these are resolved per APP_ID/PATH/ARRAY_KEY from comparison_mart, including for old immutable marts.
`bootstrap.dimension_groups` and `dimension_labels` drive the grouped selectors.
Flags remain supported by the API for compatibility; the UI primarily offers them as filters.
When product/partner dimensions or filters are used, global facts are associated with distinct
APP_ID/product_id/partner_id triples across both slices. Product-scoped facts retain their original
product/partner and SOURCE. Both predicates must match the same association; cells, pagination and
attribute highlighting use the same relation and COUNT DISTINCT APP_ID.

Assignment-style report: `PivotRequest` optionally accepts `page` (1-based),
`page_size` (1..250 logical rows), `include_totals`. Paged responses contain
`pagination: {page,page_size,total_rows}`, complete `cells` for each row in the page,
`column_totals: PivotCell[]` and `grand_total: PivotCell`. Totals use the full filtered
relation, never a sum of page cells. Every total has a signed drill-down token.
More than 128 column combinations in a paged/totals request returns a validation error.
Requests without `page_size` retain the legacy 5000-cell limit.
`bootstrap.pivot_views` supplies SPR adapter-specific presets; no response-format paths
were added to the generic pivot/storage core.

Check rows additionally carry `threshold: {value,parameter,operator}` where value is a
ratio or null. New executions record the effective threshold with the result. Existing
rows are enriched using literal defaults from the executed snapshot and that execution's
parameter overrides, without executing Python in the API. Current edited scripts/configs
cannot change the threshold of an older report. Optional custom CHECK metadata:
`threshold={"parameter":"max_share","operator":">"}` refers to an effective parameter.
The original mandatory CHECK fields, including METRIC, remain unchanged.
The checks page displays METRIC and threshold × 100 with one decimal. LABEL and ARGUMENT
have text filters; SOURCE, RESULT and CONFIDENCE have exact dropdowns with an All option.
Numeric percent filters have separate inclusive lower/upper bounds; an empty bound is
unbounded, equal bounds select an exact displayed value. CNT/TOTAL and APP_IDS stay
unfiltered. Missing thresholds display a dash rather than zero; a separate checkbox
selects only rows with no threshold.

GET /api/runs/{id}/stats enriches family rows with `group_name` and `name_available`.
The SPR adapter resolves names from this run's normalized product trials, joining on
APP_ID, SOURCE and ARRAY_KEY. Multiple names are retained; absent names use an explicit
ID fallback. Numeric statistics and stored marts remain unchanged, including old runs.
The three probability/approval cards use the stored absolute `delta` and `ci`:
the UI and HTML multiply these ratios by 100 and label them `п.п.` (percentage
points). Each card also has `baseline: {before,after}` in ratio units, displayed
as percentages. Binary baselines divide approved counts by the paired n; target
score baselines average matched products within APP_ID before averaging applications.
No relative ratio or extra bootstrap is calculated at read time. Zero BEFORE is valid
for an absolute change; empty cohorts return null baselines. Original stored paired
statistics and CI, used by threshold logic, remain unchanged. Product-count
deltas retain products/application units. The `target_model_unchanged` stratum is
omitted from this presentation API and HTML; the visible target score is named
«Вероятность одобрения». Family tables label absolute differences and CI bounds
`п.п.` as well; BEFORE/AFTER approval rates remain percentages. CI confidence level
(e.g. 95%) stays a percentage, distinct from the interval bounds' units.
Median statistics remain in the API but are hidden on the page. Ordinary numbers use
at most four decimals; very small positive p-values use four significant digits in
scientific notation so they do not become zero.

GET /api/runs/{id}/report.html renders a self-contained HTML document from the owned
READY run's immutable mart and stored statistics. `?download=true` sets attachment
disposition. The current template also applies to existing runs without recomputation.
Sections: paired statistics, named product/partner families, comparability strata,
and the complete unfiltered `strategy` preset from `scripts/default_spr/pivot_views.py`.
Its cells and totals use COUNT DISTINCT APP_ID through the same pivot relation as the
interactive table; there is no 5000-cell/page cutoff. The report has embedded CSS,
section navigation and print styles. Readiness decisions, raw JSON dumps and CHECK
rows are omitted. Existing stored statistics/decision contracts remain unchanged.

Tables: SQLite users/sessions/datasets/scripts/configs/runs/run_events/check_executions;
DuckDB normalized_union/comparison_mart/app_segments/product_trials/offers/pivot_facts/fact_memberships.
Exact logical keys follow tech_spec §4, enforced by unique indexes.
