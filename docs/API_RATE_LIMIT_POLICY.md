# API rate-limit and suspension safeguards

Last updated: 2026-08-24

## Current state

- API-Football requests are enabled again after the account suspension was lifted.
- The active workflow can use API-Football through `API_FOOTBALL_KEY`.
- The active workflow can also use football-data.org through `FOOTBALL_DATA_TOKEN`.

## Safeguards

1. Every provider request passes through one centralized limiter.
2. Requests are spaced by at least 10 seconds. This is at most 6 requests per minute, safely below a 10 requests/minute free-plan limit.
3. HTTP 429 responses honor the provider's `Retry-After` header. If it is absent or invalid, the workflow waits 60 seconds before retrying.
4. A repository-wide GitHub Actions concurrency group queues scheduled, manual, branch, and main runs. Provider workflows cannot run concurrently.
5. A request has a 45-second timeout and at most three attempts.
6. API-Football response headers are checked for the daily remaining quota. If the remaining daily quota falls to 10 or lower, the run stops sending new API-Football requests.
7. If API-Football blocks a future `date` fixture query on the Free plan, the workflow falls back to the older `league + season` fixture lookup. If the current season is also restricted, the newest season explicitly offered in the provider error is used only as a labelled historical baseline.

## API-Football reactivation

API-Football is re-enabled only through the shared provider limiter and the repository-wide workflow queue. If suspension or 429 errors return, remove or rotate `API_FOOTBALL_KEY` and let the workflow fall back to the remaining provider data.
