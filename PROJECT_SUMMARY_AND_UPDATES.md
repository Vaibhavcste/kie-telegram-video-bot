# Architecture and hardening summary

## Product boundary

Telegram presents a white-label **Team Video Studio**. Users control only duration, format, and quality. The application selects a compatible rendering route internally for text-to-video or photo animation. Billing, account balance, provider identity, model identifiers, upstream task IDs, signed media URLs, and raw upstream errors are not part of the user interface.

## Runtime flow

1. A fail-closed allowlist authenticates the Telegram user.
2. Input length, file size, and callback values are validated.
3. A bounded in-process job gate prevents duplicate or excessive concurrent work.
4. The router selects text-to-video or photo-animation infrastructure.
5. A provider adapter submits one paid job without unsafe automatic POST retries.
6. Status checks use bounded retries and backoff.
7. The result is downloaded with a byte limit, delivered to Telegram, and deleted locally.
8. A provider-neutral event is recorded in atomic local JSON storage.

## Current production boundary

This implementation is hardened for a small internal team running one bot process. A reseller platform should next introduce PostgreSQL, a durable queue/worker, recovery of in-flight jobs, tenant-level entitlements and quotas, audited admin APIs, object storage, metrics/alerts, terms and abuse controls, and a provider-routing policy isolated behind a stable internal interface.

## Security operations

- Secrets must be supplied through environment variables; there are no source-code defaults.
- Empty `ALLOWED_USER_IDS` blocks startup and access.
- `ADMIN_USER_IDS` must also be present in `ALLOWED_USER_IDS`.
- Telegram cannot mutate deployment allowlists.
- Rotate any token or key previously committed, documented, pasted in chat, or printed in logs. Removing a value from the latest commit does not erase Git history.
