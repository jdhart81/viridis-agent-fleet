# ProtoGen Repository Configuration Documentation

## Table of Contents
1. [Repository Structure](#repository-structure)
2. [Development Environment Setup](#development-environment-setup)
3. [Configuration Files](#configuration-files)
4. [Environment Variables](#environment-variables)
5. [Build Configuration](#build-configuration)
6. [Docker Configuration](#docker-configuration)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Development Workflow](#development-workflow)
9. [Testing Configuration](#testing-configuration)
10. [Deployment Configuration](#deployment-configuration)

## Repository Structure

```
protogen/
├── .github/                    # GitHub specific files
│   ├── workflows/             # GitHub Actions workflows
│   │   ├── ci.yml
│   │   ├── deploy-staging.yml
│   │   └── deploy-production.yml
│   └── CODEOWNERS
├── apps/                      # Application packages
│   ├── web/                   # SaaS web application
│   │   ├── src/
│   │   ├── public/
│   │   ├── package.json
│   │   └── tsconfig.json
│   ├── api/                   # Core API service
│   │   ├── src/
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── agent/                 # AI Agent service
│   │   ├── src/
│   │   ├── models/
│   │   └── Dockerfile
│   └── mcp-server/           # MCP server implementation
│       ├── src/
│       └── package.json
├── packages/                  # Shared packages
│   ├── ui-components/        # Shared React components
│   ├── core/                 # Core business logic
│   ├── types/                # TypeScript type definitions
│   └── utils/                # Shared utilities
├── infrastructure/           # Infrastructure as Code
│   ├── terraform/           # Terraform configurations
│   ├── kubernetes/          # K8s manifests
│   └── scripts/             # Deployment scripts
├── docs/                     # Documentation
│   ├── api/                 # API documentation
│   ├── architecture/        # Architecture diagrams
│   └── guides/              # User guides
├── tests/                    # Integration tests
│   ├── e2e/                 # End-to-end tests
│   └── load/                # Load testing scripts
├── .env.example             # Example environment variables
├── .gitignore              # Git ignore rules
├── docker-compose.yml      # Local development setup
├── lerna.json              # Monorepo configuration
├── package.json            # Root package.json
├── README.md               # Project README
└── CONTRIBUTING.md         # Contribution guidelines
```

## Development Environment Setup

### Prerequisites

```yaml
required_software:
  - node: ">=18.0.0"
  - python: ">=3.11"
  - docker: ">=24.0.0"
  - docker-compose: ">=2.20.0"
  - terraform: ">=1.5.0"
  - kubectl: ">=1.28.0"
  - postgresql: ">=15.0"
  - redis: ">=7.0"
```

### Initial Setup

```bash
# Clone repository
git clone https://github.com/protogen-ai/protogen.git
cd protogen

# Install dependencies
npm install
npm run bootstrap

# Setup Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r apps/api/requirements.txt
pip install -r apps/agent/requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your configuration

# Start development services
docker-compose up -d

# Run database migrations
npm run db:migrate

# Start development servers
npm run dev
```

## Configuration Files

### 1. `.env.example` - Environment Template

```bash
# Application
NODE_ENV=development
APP_NAME=ProtoGen
APP_URL=http://localhost:3000
API_URL=http://localhost:8000

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/protogen
DATABASE_SSL=false
DATABASE_POOL_SIZE=20

# Redis
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=
REDIS_TLS=false

# Authentication
JWT_SECRET=your-super-secret-jwt-key-change-in-production
JWT_EXPIRY=7d
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=
OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=

# AI Services
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
REPLICATE_API_KEY=
HUGGING_FACE_TOKEN=

# AWS Services
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET_DESIGNS=protogen-designs
S3_BUCKET_ASSETS=protogen-assets

# Stripe Payment
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email Service
SENDGRID_API_KEY=
EMAIL_FROM=noreply@protogen.ai
EMAIL_REPLY_TO=support@protogen.ai

# Monitoring
SENTRY_DSN=
DATADOG_API_KEY=
PROMETHEUS_ENABLED=true

# Feature Flags
FEATURE_AI_OPTIMIZATION=true
FEATURE_BLOCKCHAIN_TRACKING=false
FEATURE_AR_PREVIEW=false

# Rate Limiting
RATE_LIMIT_WINDOW=60000
RATE_LIMIT_MAX_REQUESTS=100

# External APIs
CAD_CONVERSION_API_KEY=
SIMULATION_API_KEY=
SHIPPING_API_KEY=
```

### 2. `package.json` - Root Package Configuration

```json
{
  "name": "@protogen/monorepo",
  "version": "1.0.0",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "dev": "lerna run dev --parallel",
    "build": "lerna run build",
    "test": "lerna run test",
    "test:e2e": "jest --config=tests/e2e/jest.config.js",
    "lint": "eslint . --ext .ts,.tsx,.js,.jsx",
    "format": "prettier --write \"**/*.{ts,tsx,js,jsx,json,md}\"",
    "bootstrap": "lerna bootstrap",
    "clean": "lerna clean --yes && rm -rf node_modules",
    "db:migrate": "cd apps/api && alembic upgrade head",
    "db:seed": "cd apps/api && python scripts/seed.py",
    "docker:build": "docker-compose build",
    "docker:up": "docker-compose up -d",
    "docker:down": "docker-compose down",
    "deploy:staging": "npm run build && npm run deploy:staging:k8s",
    "deploy:production": "npm run build && npm run deploy:production:k8s"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "eslint": "^8.50.0",
    "eslint-config-prettier": "^9.0.0",
    "husky": "^8.0.0",
    "jest": "^29.0.0",
    "lerna": "^7.0.0",
    "lint-staged": "^14.0.0",
    "prettier": "^3.0.0",
    "typescript": "^5.2.0"
  },
  "husky": {
    "hooks": {
      "pre-commit": "lint-staged",
      "pre-push": "npm test"
    }
  },
  "lint-staged": {
    "*.{ts,tsx,js,jsx}": [
      "eslint --fix",
      "prettier --write"
    ],
    "*.{json,md}": [
      "prettier --write"
    ]
  }
}
```

### 3. `docker-compose.yml` - Local Development

```yaml
version: '3.9'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: protogen
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build:
      context: ./apps/api
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:password@postgres:5432/protogen
      REDIS_URL: redis://redis:6379
    volumes:
      - ./apps/api:/app
      - api_venv:/app/venv
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn main:app --reload --host 0.0.0.0 --port 8000

  agent:
    build:
      context: ./apps/agent
      dockerfile: Dockerfile.dev
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql://postgres:password@postgres:5432/protogen
      REDIS_URL: redis://redis:6379
    volumes:
      - ./apps/agent:/app
      - agent_venv:/app/venv
    depends_on:
      - api

  web:
    build:
      context: ./apps/web
      dockerfile: Dockerfile.dev
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    volumes:
      - ./apps/web:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      - api

  celery:
    build:
      context: ./apps/api
      dockerfile: Dockerfile.dev
    environment:
      DATABASE_URL: postgresql://postgres:password@postgres:5432/protogen
      REDIS_URL: redis://redis:6379
    volumes:
      - ./apps/api:/app
    depends_on:
      - postgres
      - redis
    command: celery -A tasks worker --loglevel=info

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

volumes:
  postgres_data:
  redis_data:
  api_venv:
  agent_venv:
  minio_data:
```

### 4. `lerna.json` - Monorepo Configuration

```json
{
  "version": "1.0.0",
  "npmClient": "npm",
  "command": {
    "bootstrap": {
      "hoist": true
    },
    "version": {
      "conventionalCommits": true,
      "message": "chore(release): publish %v"
    },
    "publish": {
      "registry": "https://npm.pkg.github.com"
    }
  },
  "packages": [
    "apps/*",
    "packages/*"
  ]
}
```

### 5. `.eslintrc.js` - ESLint Configuration

```javascript
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'react-hooks', 'prettier'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'prettier'
  ],
  env: {
    browser: true,
    node: true,
    es2022: true
  },
  settings: {
    react: {
      version: 'detect'
    }
  },
  rules: {
    'prettier/prettier': 'error',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off'
  },
  ignorePatterns: ['dist', 'build', 'node_modules', '.next']
};
```

### 6. `tsconfig.base.json` - TypeScript Base Configuration

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022", "DOM"],
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "moduleResolution": "node",
    "allowJs": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "baseUrl": ".",
    "paths": {
      "@protogen/*": ["packages/*/src"]
    }
  },
  "exclude": ["node_modules", "dist", "build"]
}
```

## Build Configuration

### Web Application (Next.js)

```javascript
// apps/web/next.config.js
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    domains: ['protogen-assets.s3.amazonaws.com'],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.API_URL,
    NEXT_PUBLIC_STRIPE_KEY: process.env.STRIPE_PUBLISHABLE_KEY,
  },
  webpack: (config) => {
    config.experiments = {
      ...config.experiments,
      topLevelAwait: true,
    };
    return config;
  },
};

module.exports = nextConfig;
```

### API Service (FastAPI)

```python
# apps/api/config.py
from pydantic import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "ProtoGen API"
    debug: bool = False
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 168
    
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "us-east-1"
    s3_bucket_designs: str
    
    stripe_secret_key: str
    stripe_webhook_secret: str
    
    cors_origins: list[str] = ["http://localhost:3000"]
    
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings():
    return Settings()
```

## Docker Configuration

### Production Dockerfile (API)

```dockerfile
# apps/api/Dockerfile
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Run as non-root user
RUN useradd -m -u 1000 protogen && chown -R protogen:protogen /app
USER protogen

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18.x, 20.x]
        python-version: [3.11, 3.12]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: ${{ matrix.node-version }}
        cache: 'npm'
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        npm ci
        npm run bootstrap
        pip install -r apps/api/requirements.txt
        pip install -r apps/agent/requirements.txt
    
    - name: Run linting
      run: |
        npm run lint
        cd apps/api && flake8 .
    
    - name: Run tests
      run: |
        npm test
        cd apps/api && pytest
    
    - name: Build applications
      run: npm run build

  docker:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Docker Buildx
      uses: docker/setup-buildx-action@v2
    
    - name: Login to GitHub Container Registry
      uses: docker/login-action@v2
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    
    - name: Build and push API image
      uses: docker/build-push-action@v4
      with:
        context: ./apps/api
        push: true
        tags: |
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:latest
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
    
    - name: Build and push Web image
      uses: docker/build-push-action@v4
      with:
        context: ./apps/web
        push: true
        tags: |
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:latest
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:${{ github.sha }}

  deploy:
    needs: docker
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v2
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1
    
    - name: Update kubeconfig
      run: |
        aws eks update-kubeconfig --name protogen-cluster --region us-east-1
    
    - name: Deploy to Kubernetes
      run: |
        kubectl set image deployment/api api=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:${{ github.sha }} -n production
        kubectl set image deployment/web web=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:${{ github.sha }} -n production
        kubectl rollout status deployment/api -n production
        kubectl rollout status deployment/web -n production
```

## Development Workflow

### Branch Strategy

```yaml
branches:
  main:
    - Production-ready code
    - Protected branch
    - Requires PR reviews
  
  develop:
    - Integration branch
    - Latest development changes
    - Auto-deploys to staging
  
  feature/*:
    - Feature development
    - Branches from develop
    - Merges back to develop
  
  hotfix/*:
    - Emergency fixes
    - Branches from main
    - Merges to main and develop
```

### Commit Convention

```bash
# Format: <type>(<scope>): <subject>

# Types:
feat     # New feature
fix      # Bug fix
docs     # Documentation
style    # Code style
refactor # Code refactoring
test     # Tests
chore    # Maintenance

# Examples:
feat(api): add material recommendation endpoint
fix(web): resolve responsive layout issue
docs(readme): update installation instructions
```

## Testing Configuration

### Jest Configuration (Frontend)

```javascript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/tests/setup.ts'],
  testPathIgnorePatterns: ['/node_modules/', '/.next/'],
  transform: {
    '^.+\\.(ts|tsx)$': ['@swc/jest'],
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
  },
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.tsx',
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
};
```

### Pytest Configuration (Backend)

```ini
# pytest.ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --verbose
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
    -p no:warnings
```

## Deployment Configuration

### Kubernetes Deployment

```yaml
# infrastructure/kubernetes/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: ghcr.io/protogen-ai/protogen/api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: protogen-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: protogen-secrets
              key: redis-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Terraform Configuration

```hcl
# infrastructure/terraform/main.tf
terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }
  
  backend "s3" {
    bucket = "protogen-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
  }
}

module "eks" {
  source = "./modules/eks"
  
  cluster_name    = "protogen-cluster"
  cluster_version = "1.28"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  
  node_groups = {
    main = {
      desired_capacity = 3
      max_capacity     = 10
      min_capacity     = 2
      
      instance_types = ["t3.large"]
    }
  }
}

module "rds" {
  source = "./modules/rds"
  
  identifier = "protogen-db"
  
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = "db.t3.medium"
  
  allocated_storage = 100
  storage_encrypted = true
  
  database_name = "protogen"
  username      = "protogen"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.database_subnets
}
```

## Security Configuration

### Security Headers

```javascript
// apps/web/middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const response = NextResponse.next();
  
  // Security headers
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-XSS-Protection', '1; mode=block');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set(
    'Content-Security-Policy',
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';"
  );
  response.headers.set(
    'Permissions-Policy',
    'camera=(), microphone=(), geolocation=()'
  );
  
  return response;
}

export const config = {
  matcher: '/((?!api|_next/static|_next/image|favicon.ico).*)',
};
```

## Monitoring Configuration

### Prometheus Metrics

```python
# apps/api/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
request_count = Counter(
    'protogen_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'protogen_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

# Business metrics
active_projects = Gauge(
    'protogen_active_projects',
    'Number of active projects'
)

manufacturing_orders = Counter(
    'protogen_manufacturing_orders_total',
    'Total manufacturing orders',
    ['status', 'process']
)

# AI metrics
ai_requests = Counter(
    'protogen_ai_requests_total',
    'Total AI service requests',
    ['service', 'model']
)

ai_tokens_used = Counter(
    'protogen_ai_tokens_total',
    'Total AI tokens consumed',
    ['service', 'model']
)
```

## Contributing Guidelines

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.