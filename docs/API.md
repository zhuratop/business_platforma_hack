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

Tables: SQLite users/sessions/datasets/scripts/configs/runs/run_events/check_executions;
DuckDB normalized_union/comparison_mart/app_segments/product_trials/offers/pivot_facts/fact_memberships.
Exact logical keys follow tech_spec §4, enforced by unique indexes.
