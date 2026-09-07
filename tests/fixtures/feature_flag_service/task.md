I'm building a feature flag service using Bun, Hono, TypeScript, and
better-sqlite3. It needs boolean flags and percentage-based rollouts, scoped per
environment (dev, staging, production). Requirements:

- CRUD endpoints for managing flags and their per-environment configurations.
- An evaluation endpoint taking a flag key, environment, and user ID, returning
  whether the flag is on for that user. Percentage rollouts must be sticky: the
  same user ID always gets the same result for the same flag at the same rollout
  percentage, with no per-user state stored in the database.
- Increasing a rollout from 20% to 40% must keep the original 20% enabled.
- An in-memory cache for flag configs on the evaluation path, with invalidation
  when a flag changes.
- An audit log recording every flag change (who, what, when, before/after).
- API key authentication for the management endpoints, with keys stored hashed.
