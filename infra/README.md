# /infra

Local runtime. Docker Compose only - no cloud, no paid services.

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | postgres, redis, api, worker, web |
| `.env.example` | safe placeholder env (copy to `.env`) |
| `postgres/init/01_bootstrap.sql` | one-time DB defaults (UTC). Schema is Alembic's. |
| `scripts/simulate_signal.py` | posts a versioned sample webhook to the api |

## Clean start

**Unix / macOS**

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
```

**Windows (PowerShell)**

```powershell
Copy-Item infra\.env.example infra\.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
```

Wait for health, then:

```bash
curl -fsS localhost:8000/health         # api
curl -fsS localhost:8100/health         # worker
curl -fsS localhost:3000/login          # web
python infra/scripts/simulate_signal.py # fire one mock signal
```

Open http://localhost:3000 .

## Full reset

```bash
docker compose -f infra/docker-compose.yml down -v
```
