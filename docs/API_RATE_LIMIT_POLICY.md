# API rate-limit and suspension safeguards

Last updated: 2026-08-24

## Current state

- API-Football requests are disabled while the API-Football account is suspended.
- The active workflow uses football-data.org through `FOOTBALL_DATA_TOKEN`.
- No GitHub Actions workflow reads or sends `API_FOOTBALL_KEY`.

## Safeguards

1. Every provider request passes through one centralized limiter.
2. Requests are spaced by at least 6.2 seconds. This is at most about 9.67 requests per minute, below a 10 requests/minute free-plan limit.
3. HTTP 429 responses honor the provider's `Retry-After` header. If it is absent or invalid, the workflow waits 60 seconds before retrying.
4. A repository-wide GitHub Actions concurrency group queues scheduled, manual, branch, and main runs. Provider workflows cannot run concurrently.
5. A request has a 45-second timeout and at most three attempts.

## API-Football reactivation

API-Football must not be re-enabled until support confirms that the account is active. If it is restored later, its requests must use the same centralized limiter and must not bypass the repository-wide workflow queue.
