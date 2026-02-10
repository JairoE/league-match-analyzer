# Railway Deployment Guide

This project requires **two separate services** on Railway to work properly:

## Services Required

### 1. API Service (web)
- **Name**: `league-api`
- **Start Command**: Defined in `Procfile` as `web`
- **Purpose**: Serves the FastAPI REST API

### 2. Worker Service (background jobs)
- **Name**: `league-worker`
- **Start Command**: Defined in `Procfile` as `worker`
- **Purpose**: Runs ARQ background worker for:
  - Scheduled cron jobs (syncing user matches every 6 hours)
  - On-demand job processing (fetch_user_matches_job, fetch_match_details_job)

## Setup Steps

### 1. Add Railway Plugins
In your Railway project:
- Add **PostgreSQL** plugin (generates `DATABASE_URL`)
- Add **Redis** plugin (generates `REDIS_URL`)

### 2. Create API Service
1. Create new service from your GitHub repo
2. **Root Directory**: `/` (project root)
3. **Build Command**: Auto-detected by nixpacks
4. **Start Command**: `uvicorn --app-dir services/api main:app --host 0.0.0.0 --port $PORT`
   - Or select "web" from Procfile
5. **Environment Variables**:
   - `DATABASE_URL` - Reference from PostgreSQL plugin
   - `REDIS_URL` - Reference from Redis plugin
   - `RIOT_API_KEY` - Your Riot API key
   - `CORS_ALLOW_ORIGINS` - Your frontend URL (e.g., https://yourapp.vercel.app)
   - `LOG_LEVEL` - `INFO`
   - `SERVICE_NAME` - `league-api`

### 3. Create Worker Service
1. Create **another** service from the **same** GitHub repo
2. **Root Directory**: `/` (same as API)
3. **Start Command**: `cd services/api && arq app.services.background_jobs.WorkerSettings`
   - Or select "worker" from Procfile
4. **Environment Variables** (same as API):
   - `DATABASE_URL` - Reference from PostgreSQL plugin (shared)
   - `REDIS_URL` - Reference from Redis plugin (shared)
   - `RIOT_API_KEY` - Your Riot API key
   - `LOG_LEVEL` - `INFO`
   - `SERVICE_NAME` - `league-worker`

### 4. Run Migrations
After both services are deployed:
```bash
# SSH into the API service and run:
cd services/api && alembic upgrade head
```

Or use Railway's "Run a Command" feature.

## Important Notes

- **Both services MUST share the same PostgreSQL and Redis instances**
- The worker service has **no exposed port** - it only processes background jobs
- The cron job runs every 6 hours at: 00:00, 06:00, 12:00, 18:00 UTC
- If the worker service is down, cron jobs and background processing will not work
- Monitor worker logs to ensure jobs are running correctly

## Deployment Flow

```
GitHub Push → Railway Deploy
    ↓
    ├─→ API Service (web process)
    │   └─→ Serves HTTP requests on $PORT
    │
    └─→ Worker Service (worker process)
        └─→ Processes background jobs from Redis queue
```

Both services connect to the same:
- PostgreSQL database
- Redis instance

## Verifying Deployment

1. **API Health**: Visit `https://your-api.railway.app/` (should return 200)
2. **Worker Health**: Check Railway logs for `arq_startup` message
3. **Redis Connection**: Verify `arq:queue:health-check` key exists in Redis
4. **Cron Jobs**: Check logs every 6 hours for `sync_all_users_matches` execution

## Troubleshooting

- **Cron not running**: Ensure worker service is deployed and running
- **Jobs not processing**: Check `REDIS_URL` is the same for both services
- **Database errors**: Ensure migrations have been run
- **API can't connect to DB**: Check `DATABASE_URL` is set correctly
