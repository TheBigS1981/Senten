# Deployment Guide for Senten

This guide describes how to deploy Senten on a server with Docker.
The Docker image is automatically built via GitHub Actions and stored in the GitHub Container Registry.

---

## Prerequisites

### On the server:
- Docker installed
- Docker Compose installed
- Access to the GitHub repository (for private container images)

### Required information:
- GitHub Personal Access Token (PAT) with `read:packages` permission

---

## Step 1: Create Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select the following permissions:
   - `read:packages` - Download packages from GitHub Package Registry
4. Copy the token and store it securely

---

## Step 2: Prepare Server

### 2.1 Log in to GitHub Container Registry

```bash
# Log in with PAT
echo YOUR_TOKEN | docker login ghcr.io -u TheBigS1981 --password-stdin
```

### 2.2 Create directory

```bash
mkdir senten && cd senten
mkdir data
```

---

## Step 3: Create Configuration

### 3.1 docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
services:
  senten:
    image: ghcr.io/thebigs1981/senten:latest
    container_name: senten
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
EOF
```

### 3.2 Environment variables (.env)

```bash
cat > .env << 'EOF'
# DeepL API Key (optional - without key, app runs in mock mode)
DEEPL_API_KEY=your-deepl-api-key

# Secret key for sessions (please change!)
SECRET_KEY=$(openssl rand -hex 32)

# Monthly character limit (optional)
MONTHLY_CHAR_LIMIT=500000

# Authentication (optional)
# AUTH_USERNAME=admin
# AUTH_PASSWORD=secure-password

# CORS origins (optional, comma-separated)
# ALLOWED_ORIGINS=https://example.com
EOF
```

**IMPORTANT:** Adjust the values in `.env`!

---

## Step 4: Start Application

```bash
# Pull image
docker compose pull

# Start container
docker compose up -d

# Check logs
docker compose logs -f

# Health check
curl http://localhost:8000/health
```

---

## Useful Commands

```bash
# Stop container
docker compose pull && docker compose up -d

# Display logs
docker compose logs -f

# Check status
docker compose ps

# Enter container (debug)
docker compose exec senten sh
```

---

## With Reverse Proxy (HTTPS)

### Caddy (recommended)

**Caddyfile:**
```
senten.example.com {
    reverse_proxy localhost:8000
}
```

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name senten.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Updates

```bash
# Pull latest image
docker compose pull

# Restart container
docker compose up -d

# Clean up old images
docker image prune -f
```

---

## Backup

```bash
# Backup database
tar -czf senten-backup-$(date +%Y%m%d).tar.gz data/
```

---

## Troubleshooting

### Image cannot be pulled
```bash
# Log in again
echo YOUR_TOKEN | docker login ghcr.io -u TheBigS1981 --password-stdin
```

### Container does not start
```bash
# Check logs
docker compose logs senten

# Container status
docker compose ps
```

### Health check fails
```bash
# Test manually
docker compose exec senten curl -f http://localhost:8000/health
```

---

## Configure Authentication

### Option 1: Anonymous (no auth)
Leave `AUTH_USERNAME` and `AUTH_PASSWORD` empty.

### Option 2: HTTP Basic Auth
```env
AUTH_USERNAME=admin
AUTH_PASSWORD=your-secure-password
```

### Option 3: OIDC
```env
OIDC_DISCOVERY_URL=https://auth.example.com/application/o/senten/.well-known/openid-configuration
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
```

---

## Done!

The application is running at: `http://your-server-ip:8000`
