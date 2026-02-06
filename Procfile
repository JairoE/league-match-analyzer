web: uvicorn --app-dir services/api main:app --host 0.0.0.0 --port $PORT
worker: cd services/api && arq app.services.background_jobs.WorkerSettings
