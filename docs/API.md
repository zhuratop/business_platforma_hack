# A0 — contracts

`DELETE /api/scripts/{id}` удаляет из рабочих списков проверку владельца и атомарно убирает её ID из всех его конфигураций. Файлы, снимки кода, созданные прогоны и их результаты сохраняются. Удалённую проверку нельзя изменять, валидировать или включать в новую конфигурацию; другие типы процедур этим маршрутом не удаляются. Сохранение конфигурации заранее отклоняет повторяющиеся статические CHECK.id вместо ошибки в фоне.

Текущий HTML-экспорт `/api/runs/{id}/report.html?download=true`: полный прогон, дерево всех атрибутов из normalized_union с уникальными APP_ID и все сохранённые строки автопроверок. Включены пороги и METRIC в процентах с одним знаком, результат, уверенность и ограниченный список APP_IDS с предупреждением. Дерево раскрывается автономно; статистические карточки и прежний пресет стратегии удалены из файла. В интерфейсе кнопка скачивания доступна только на страницах сводной таблицы и автопроверок. Доступ к API по-прежнему требует владельца READY-прогона; данные старых прогонов не перестраиваются.

Дополнение входных форматов: `/datasets/register` и `/datasets/upload` принимают JSON/XML/CSV в каталогах срезов (один файл на APP_ID). Схема `manifest.json` прежняя; расширения пары могут различаться. У датасета добавлено поле `formats`. В `/scripts` и `/scripts/upload?kind=reader` разрешён тип `reader`, точка входа `read_input(raw,filename,app_id,source,params)->dict`. В `/configs` добавлен `stages.reader`; старые конфигурации получают стандартный читатель. `/scripts/validate` принимает необязательный `dataset_id` владельца и проверяет читатель на его первой паре. В состоянии прогона добавлены `saved_pairs`, `normalized_rows`, `saved_at` — счётчики зафиксированных полных пар. Размер порции: `params.processing.batch_pairs`, 1–500, по умолчанию 25. См. [INPUT_FORMATS.md](INPUT_FORMATS.md).

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

Staged runs: `POST /runs` and saved configs accept `stop_after` (default REPORTING).
Values in order: READING, NORMALIZING, COMPARING, FACTS, CHECKS, STATS, REPORTING.
A successful partial execution has status PAUSED. Public runs include `completed_stage`,
`stop_after`, `checkpoints` (stage, label, completed_at, seconds, counts; no filesystem paths).
`POST /runs/{id}/resume {stop_after: ...}` atomically queues a PAUSED/FAILED owned run,
returning 409 if already active or the target is not after the completed stage.
It retains the original procedure/config snapshots and reuses completed artifacts.
`GET /runs/{id}/preview?table=raw_inputs&limit=10` reads the latest immutable completed
checkpoint, not the scratch file. Tables are allowlisted by completed stage; result:
`{stage,table,tables,total,rows}`. CHECKS/STATS also expose `checks`/`stats` preview tables.
Other owners receive 404. Reporting/pivot remain gated by READY. Bootstrap includes
`pipeline_stages` (id,label). The supervisor defaults to two concurrent task processes,
bounded by --workers/SPR_WORKERS; SQLite claims are atomic across users.

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
For these three cards no relative ratio or extra bootstrap is calculated at read time. Zero BEFORE is valid
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

`/stats` also includes `bureau_scores.score_equ` and `bureau_scores.score_okb`.
Each contains `before`/`after` objects `{mean,n,approved_total,missing}` for the
approved population of that slice, plus `delta` (difference of those population
means). The populations differ: this delta is descriptive, with no paired CI.
`paired` contains `{n,approved_both_total,missing,before,after,delta,ci,information}`
on fixed APP_IDs approved in both slices with valid scores in both. Its CI uses
the existing paired percentile bootstrap with run alpha/repeats/seed. Raw numeric
finite values are read only from root characteristics.score_equ/score_okb in the
immutable normalized union; missing/null/bool/string values are not converted to
zero. Units are bureau-score points, never percent or percentage points. Each
APP_ID contributes once, independently of number of products. HTML uses the same data.

The bureau cards now hide `paired` details and show `t_test` instead. This object
contains `method,n_before,n_after,n_common,statistic,df,p,p_adjusted,alpha,status,
reason,significant`. The two-sided unequal-variance partially overlapping samples
t-test accounts for shared APP_IDs (Derrick–Toher–White 2017, equations 4–6:
https://www.tqmp.org/RegularArticles/vol13-2/p120/p120.pdf). Full overlap uses the
paired t statistic; no overlap reduces to Welch. Zero variance, insufficient data
or unestimable overlap correlation return unavailable/null, never NaN/Infinity.
Holm controls the declared family of two bureau tests; significance uses p_adjusted
and the run alpha. The original means/delta and stored statistics are unchanged.
Historical paired API fields remain for compatibility but are omitted from UI/HTML.

GET /api/runs/{id}/report.html renders a self-contained HTML document from the owned
READY run's immutable mart and stored statistics. `?download=true` sets attachment
disposition. The current template also applies to existing runs without recomputation.
Sections: paired statistics, named product/partner families, comparability strata,
and the complete unfiltered `strategy` preset from `scripts/default_spr/pivot_views.py`.
Its cells and totals use COUNT DISTINCT APP_ID through the same pivot relation as the
interactive table; there is no 5000-cell/page cutoff. The report has embedded CSS,
section navigation and print styles. Readiness decisions, raw JSON dumps and CHECK
rows are omitted. Existing stored statistics/decision contracts remain unchanged.

GET /api/runs/{id}/stats/charts is an owner-only READY-run read endpoint. It returns
`total_apps`, `transitions[{before,after,count,share}]`, `approvals{lost,gained,net}`,
and `probability{n,total_apps,no_matched_score,invalid_score,mean_before,mean_after,bins}`.
Each bin contains `lower,upper,before,after,before_share,after_share`. Ratios use 0–1
units. Decision cells count distinct APP_ID. Probability bins use identical paired
APP_ID cohorts: average matched products inside each application first; matching
requires product ID, model name and APPROVAL_PROBABILITY type. Bin edges are common
0,.1,...,1; intervals include the lower edge, only the last includes the upper edge.
Nonfinite/out-of-range paired probabilities exclude the application, explicitly
counted in invalid_score. A zero denominator yields null shares/means. No mart or
CHECK is modified. Group charts reuse existing paired family statistics from /stats.

The statistics UI and HTML now display only `families.products`, labelled
«Продукт (компания)». There is one group chart and one group table; no partner toggle
or second table. `families.partners` remains in the API for compatibility. Product
cohorts and their Holm correction are unchanged; families are not merged or summed.

Dataset registration/upload reuses an existing active dataset with the same owner and full
SHA-256 checksum, regardless of submitted display name. Lookup and insert occur in
one BEGIN IMMEDIATE transaction, so concurrent imports cannot add duplicates. A
redundant newly copied snapshot is removed; published snapshots are preserved.
GET /api/datasets and bootstrap.datasets return one representative per owner/checksum
(newest created, then ID); deduplication happens before pagination. Historical IDs
remain readable by their owner and usable by existing runs. Same names with different
checksums remain separate; equal checksums belonging to other users are not reused.

DELETE /api/datasets/{id} is owner-only (foreign/missing IDs return 404) and marks
all active owner/checksum copies DELETED with deleted_at in one transaction.
Returns `{deleted:true,hidden_snapshots:n}`. Lists/bootstrap and registration exclude
DELETED snapshots. Existing/queued runs retain their dataset records and files;
POST /runs with a deleted dataset returns 409. Reimport creates a new active ID.
Deletion is idempotent; replaying deletion of an old ID cannot delete a new import.
UI confirmation explains removal from the list and retention of existing runs.

Current script lists (/scripts and bootstrap.scripts) additionally expose
`display_name` and `description` for checks. CHECK id/label are read with ast.parse,
never exec. Generic template names receive a semantic label and identical template
copies receive stable ordinal suffixes. The configuration UI uses these fields;
stored names, IDs, params, code and historical run snapshots stay unchanged.

Check scripts also expose a statically extracted `check_id` for configuration UI:
an unchecked copy is disabled while another selected script has the same CHECK.id.

The custom `my_changes` template now accepts `max_share` (default .30, explicitly a
demonstration tolerance). A nonempty dataset passes iff its unrounded fraction of
unique changed APP_ID is <= max_share. Results retain the actual count/share and
explicit threshold metadata; empty datasets fail with LOW confidence. The five
provided CHECK files and their verdict logic are unchanged.

The separate synthetic demonstration endpoint/view/artifact have been removed.
Current real-run config overrides for alice: ar_drop_by_product.max_drop_rel=.30,
attribute_new_loss.min_share=.10, my_changes.max_share=.30. The attribute parameter
is a reporting relevance cutoff, not a fake PASS override: signals below 10% are
omitted by the unchanged supplied implementation, signals above remain FAIL.
Checks without a PASS/FAIL threshold retain their original verdicts. Configuration
overrides are snapshot-versioned when checks are re-executed, not applied retroactively.

The default normalize/compare/facts files now contain their complete executable
implementations and local helpers, using standard-library imports only. They no
longer delegate algorithms to backend imports or MartAPI.default_facts. The facts
procedure still receives MartAPI as its declared input and uses its DuckDB connection
for the fully visible aggregation SQL. File lists/validation/snapshots read the same
complete source. Copying a file into the editor therefore requires no hidden module
dependency. Existing historical snapshots are not rewritten; universal core APIs
remain available and compatibility is covered by real-pair contract tests.

Tables: SQLite users/sessions/datasets/scripts/configs/runs/run_events/check_executions;
DuckDB normalized_union/comparison_mart/app_segments/product_trials/offers/pivot_facts/fact_memberships.
Exact logical keys follow tech_spec §4, enforced by unique indexes.

POST /api/runs/{id}/pivot/tree (owner-only, READY) accepts TreeRequest:
`path` (prefix/attribute), `stage: path|keys|values`, optional `array_key`,
`filters` (only SOURCE / DIFF_FLAG), `page>=1`, `page_size<=100` (default 50).
Returns lazy child nodes with typed values, full array keys, signed count cells,
scope totals and pagination. Counts use distinct APP_ID over normalized_union joined
to comparison_mart; sources/types/buckets remain separate, raw DIFF_FLAG is preserved.
Folder scopes include all descendants; scalar values at mixed scalar/object paths
are exposed alongside child fields. No raw-response reread or mart mutation occurs.
Existing /pivot/apps and application highlighting accept signed `__tree` scopes;
they reuse the identical predicates (prefix/exact path, full array key, kind, bucket,
source and diff). The UI preset id is attributes_tree; normal pivot requests and
the compact strategy are unchanged.

PivotRequest additionally accepts `collapse_unchanged: true` with columns
`[DIFF_FLAG,SOURCE]` and `include_totals: true`. Standard cells/totals remain unchanged.
Extra `unchanged_cells`, `row_totals` and `unchanged_total` use COUNT DISTINCT APP_ID
on scoped memberships, not sums of source cells; each carries a matching cell_token.
Row extras cover the current logical page, global totals cover the entire filter.
The strategy preset uses `[PATH,VALUE_ADJUSTED]`, supplies readable `attributes`
metadata, and selects decisions, refusal reasons/codes, approval score/model/cutoff.
The UI collapses unchanged sources, shows changed BEFORE then AFTER, and adds a
nonadditive unique row total. Generic/custom layouts retain the original rendering.
HTML follows the same aggregation without pagination.
