# Deployment Guide

Deploy your Viridis agent to multiple environments from a single codebase.

## Quick Start

All deployment targets import from `src/core.py`. Your business logic is once; deploy everywhere.

### 1. FastAPI / Docker (Recommended for MVP)

```bash
# Install and run locally
make install
make dev

# In another terminal, test
curl http://localhost:8080/health

# Or build and run Docker
make docker-build
make docker-run
```

**Best for:** Rapid prototyping, internal tools, staged deployments

---

## Deployment Targets

### A. FastAPI + Docker (Cloud Run, ECS, Kubernetes)

**Files:**
- `adapters/fastapi_server.py` - HTTP endpoints
- `Dockerfile` - Multi-stage build
- `requirements.txt` - Python dependencies

**Deploy to Google Cloud Run:**

```bash
# Build and push
docker build -t gcr.io/YOUR_PROJECT/agent:latest .
docker push gcr.io/YOUR_PROJECT/agent:latest

# Deploy
gcloud run deploy agent \
  --image gcr.io/YOUR_PROJECT/agent:latest \
  --platform managed \
  --region us-central1 \
  --set-env-vars AGENT_NAME=agent,LOG_LEVEL=INFO \
  --allow-unauthenticated
```

**Deploy to AWS ECS:**

```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
docker build -t YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/agent:latest .
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/agent:latest

# Use in ECS task definition
```

**Deploy to Kubernetes:**

```bash
# Create Docker image in cluster registry
# Then apply deployment:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent
  template:
    metadata:
      labels:
        app: agent
    spec:
      containers:
      - name: agent
        image: agent:latest
        ports:
        - containerPort: 8080
        env:
        - name: AGENT_NAME
          value: "agent"
        - name: LOG_LEVEL
          value: "INFO"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: agent-service
spec:
  type: LoadBalancer
  selector:
    app: agent
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

---

### B. Cloudflare Workers

**Files:**
- `adapters/cloudflare_worker.js` - Worker entry point
- `wrangler.toml` - Cloudflare config

**Setup:**

```bash
# Install Wrangler
npm install -g @cloudflare/wrangler

# Update wrangler.toml with your account ID
# Get it from: https://dash.cloudflare.com/

# Login
wrangler login

# Deploy
wrangler publish
```

**Pattern for calling Python core logic:**

```javascript
// In cloudflare_worker.js, if your core is exposed via Cloud Function:

async function callCoreService(env, operation, payload = null) {
  const response = await fetch(env.CORE_SERVICE_URL + "/" + operation, {
    method: payload ? "POST" : "GET",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${env.CORE_API_KEY}`
    },
    body: payload ? JSON.stringify(payload) : null
  });
  return response.json();
}

// Or rewrite core logic in JavaScript
```

**Recommended: Use FastAPI + Cloud Run as the core, call from Workers:**

1. Deploy FastAPI service to Cloud Run
2. Cloudflare Worker calls Cloud Run HTTP endpoint
3. Worker provides caching/DDoS protection, Cloud Run runs core logic

---

### C. MCP Server (Claude Code, Other LLMs)

**Files:**
- `adapters/mcp_server.py` - MCP protocol implementation

**Run locally:**

```bash
python adapters/mcp_server.py
```

**Use in Claude Code:**

1. Open Claude Code
2. Go to Settings → MCP Servers
3. Add server:
   ```json
   {
     "mcpServers": {
       "my-agent": {
         "command": "python",
         "args": ["/path/to/adapters/mcp_server.py"]
       }
     }
   }
   ```
4. Restart Claude Code
5. Now you can use the agent in chat

**Deploy MCP Server to production:**

```bash
# Option 1: Run on a VM/server
python adapters/mcp_server.py &

# Option 2: Docker container (add to Dockerfile)
CMD ["python", "adapters/mcp_server.py"]
```

---

### D. Claude Code Skill

**Files:**
- `adapters/claude_skill.md` - SKILL.md manifest
- `src/core.py` - Core logic

**Create skill package:**

```bash
mkdir my-agent.skill
cp adapters/claude_skill.md my-agent.skill/SKILL.md
cp src/core.py my-agent.skill/
cp requirements.txt my-agent.skill/
zip -r my-agent.skill.zip my-agent.skill/
```

**Use in Claude Code:**

```
/import ./my-agent.skill.zip
```

Then in a code cell:

```python
from my_agent_skill import process

result = await process({"input": "data"})
```

---

## Environment-Specific Deployment

### Development

```bash
# Terminal 1: Start FastAPI with auto-reload
make dev

# Terminal 2: Test endpoints
curl -X POST http://localhost:8080/process -H "Content-Type: application/json" -d '{"test": "data"}'
```

### Staging

```bash
# Build Docker image
docker build -t agent:staging .

# Run with staging config
docker run -e AGENT_NAME=agent-staging -e LOG_LEVEL=DEBUG -p 8080:8080 agent:staging

# Deploy to staging environment
gcloud run deploy agent-staging --image agent:staging --region us-central1
```

### Production

```bash
# Increment version in agent.yaml
# Update CHANGELOG

# Build Docker image with version tag
docker build -t agent:0.2.0 .

# Push to registry
docker push agent:0.2.0

# Deploy to production with health checks, monitoring, alerts
gcloud run deploy agent \
  --image agent:0.2.0 \
  --min-instances 1 \
  --max-instances 10 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars AGENT_NAME=agent,LOG_LEVEL=INFO
```

---

## Monitoring & Observability

### Health Checks

Every deployment target exposes `/health`:

```bash
curl http://agent-host:8080/health
# Returns: {"status": "ok", "agent": "agent", "version": "0.1.0", "checks": {...}}
```

Set up monitoring:

```bash
# Google Cloud Monitoring
# Add Cloud Run health check:
# Path: /health
# Interval: 30s
# Timeout: 10s
```

### Logging

FastAPI adapter logs to stdout. Cloudflare Workers logs go to Tail. MCP logs to stderr.

```bash
# View FastAPI logs (local)
make dev  # Logs appear in terminal

# View Docker logs
docker logs <container_id> -f

# View Cloud Run logs
gcloud run logs read agent --limit 100

# View Cloudflare Worker logs
wrangler tail
```

### Metrics

Track in your core logic:

```python
import time
import logging

logger = logging.getLogger(__name__)

async def process(self, input_data: dict) -> dict:
    start = time.time()
    try:
        result = await self._do_work(input_data)
        duration = time.time() - start
        logger.info(f"processed in {duration:.2f}s", extra={
            "duration_ms": duration * 1000,
            "status": "ok"
        })
        return self._wrap_result(data=result)
    except Exception as e:
        duration = time.time() - start
        logger.error(f"failed after {duration:.2f}s: {e}", extra={
            "duration_ms": duration * 1000,
            "status": "error"
        })
        raise
```

---

## Secrets Management

Never hardcode secrets. Use environment variables:

```bash
# Local development
cp .env.example .env
# Edit .env with real values
# (Never commit .env)

# Docker
docker run -e API_KEY=secret-value ...

# Cloud Run
gcloud run deploy agent \
  --set-env-vars API_KEY=secret-value

# Or use Google Secret Manager
gcloud secrets create api-key --data-file=-
gcloud run deploy agent \
  --set-env-vars API_KEY=sm://api-key
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy Agent

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/

      - name: Build Docker image
        run: docker build -t agent:latest .

      - name: Push to registry
        run: |
          docker tag agent:latest gcr.io/${{ secrets.GCP_PROJECT }}/agent:latest
          docker push gcr.io/${{ secrets.GCP_PROJECT }}/agent:latest

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy agent \
            --image gcr.io/${{ secrets.GCP_PROJECT }}/agent:latest \
            --region us-central1 \
            --set-env-vars AGENT_NAME=agent,LOG_LEVEL=INFO
```

---

## Rollback Procedure

If a deployment fails:

```bash
# Cloud Run: Automatic traffic split
gcloud run deploy agent \
  --image gcr.io/PROJECT/agent:PREVIOUS_VERSION \
  --traffic PREVIOUS_VERSION=100

# Docker: Restart with previous image
docker run agent:PREVIOUS_VERSION

# Update version in agent.yaml and re-deploy after fix
```

---

## Performance Optimization

### FastAPI / Docker

```python
# In adapters/fastapi_server.py

# Use async endpoints (already done)
# Add caching for expensive operations
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_function(param):
    return result

# Add database connection pooling if needed
from sqlalchemy.pool import QueuePool
# Configure pool size, overflow, timeout
```

### Cloudflare Workers

```javascript
// Cache responses
const cache = caches.default;

// Use worker environments
```

---

## Security Checklist

- [ ] No secrets in code (all env-var based)
- [ ] All endpoints have input validation
- [ ] Error messages don't leak implementation details
- [ ] CORS configured appropriately (restrict in production)
- [ ] HTTPS enforced in production
- [ ] Rate limiting implemented (if public)
- [ ] Authentication/authorization if needed
- [ ] Regular security updates to dependencies

---

## Support & Troubleshooting

### Common Issues

**Agent won't start**
```bash
# Check logs
docker logs <container_id>
# Or locally
make dev
```

**Health check failing**
```bash
curl http://localhost:8080/health
# Check response and logs
```

**Slow responses**
```bash
# Check logs for processing time
# Add monitoring/metrics
# Profile with Python profiler
```

**Out of memory**
```bash
# Check Docker memory limit
docker run -m 512m ...

# Or increase container memory
gcloud run deploy agent --memory 1Gi
```

---

## Next Steps

1. Copy this template to your agent directory
2. Implement your core logic in `src/core.py`
3. Run `make test` to verify
4. Deploy to FastAPI locally with `make dev`
5. Once stable, deploy to Docker and cloud platform
6. Add monitoring and alerting
7. Set up CI/CD pipeline

---

See README.md for architecture overview and EXAMPLE.md for a concrete implementation.
