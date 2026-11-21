# Render always-on deployment

## Repository audit

- The root [`Dockerfile`](../Dockerfile) builds the React frontend and serves its assets, the Django API, and
  configured media from one Gunicorn web process. There is no separate frontend service or Render Blueprint
  (`render.yaml`) in this repository.
- The Render instance plan, attached database/Key Value services, health-check setting, and actual live start/build
  commands are configured in the Render Dashboard and cannot be confirmed from this checkout. The Web Service
  running the root Dockerfile is the service whose Free plan can cause the reported 15-minute cold start.
- Gunicorn is configured as one worker with eight threads in the root image. Runtime memory and CPU graphs are
  account-side; inspect Render Metrics after the upgrade before selecting a larger instance.
- Celery and Celery Beat are configured in Django, but the root Dockerfile starts only the web process. Background
  work on the current single-service deployment therefore depends on the separately configured scheduled tick
  described in `UPGRADE_GUIDE.md`; this repository does not declare a Render worker or cron service.
- The existing `/api/health/` checks database and cache connectivity and can return 503 when a dependency is down.
  The new `/health/` endpoint is a minimal process liveness check and performs no database/cache I/O. Production
  HTTPS redirection explicitly exempts this path so an internal HTTP probe can reach it.

## Always-on requirement and cost

Render documents that Free Web Services spin down after 15 minutes without inbound traffic, while paid compute
does not spin down. Its current compute pricing lists the smallest paid Web Service size at **$7/month with 512 MB
RAM**, and the next size at **$25/month with 2 GB RAM**. These are compute charges only; workspace, database,
Key Value, storage, and bandwidth can add costs. Start with the smallest paid size only if the live service's memory
metrics support it, then increase it if metrics show memory pressure or restarts. Pricing may change; recheck the
[Render pricing page](https://render.com/pricing) before confirming a plan change.

## Dashboard steps

1. In the Render Dashboard, open the TURFBARI Web Service that builds from this repository's root `Dockerfile`.
2. Confirm it is the combined frontend/API service. Do not change the database or Key Value plans as part of this
   web-service upgrade.
3. Open **Settings** and change the Web Service compute plan from **Free** to the smallest suitable paid compute
   plan. Review the current monthly estimate and service metrics before confirming.
4. Set the service health-check path to **`/health/`**. This checks process liveness; it is not an availability
   keep-alive and does not prevent Free-tier spin-down.
5. Save the plan and health-check changes, wait for Render to finish restarting/deploying, and confirm the service
   reports **Live** and the health check passes.
6. Verify the public homepage, a public turf page, authentication, and an owner/admin dashboard. Check logs and
   metrics for startup errors and memory pressure.

The repository can deploy the liveness endpoint automatically, but changing the Render plan is an account-side,
billable action. No paid plan is considered active until it is selected and verified in the Render Dashboard.
