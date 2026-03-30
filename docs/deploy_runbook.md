# SwarmChain Production Deployment Runbook

## Prerequisites

- A domain name pointing to the droplet's IP (A record)
- An SSH key added to your DigitalOcean account

## 1. Create the Droplet

DigitalOcean console or CLI:

```
doctl compute droplet create swarmchain-prod \
  --region nyc1 \
  --size s-2vcpu-4gb \
  --image ubuntu-24-04-x64 \
  --ssh-keys <your-key-fingerprint> \
  --tag-names swarmchain
```

Wait for the droplet IP, then point your DNS A record to it.

## 2. SSH In

```bash
ssh root@<droplet-ip>
```

## 3. Run the Deploy Script

```bash
curl -O https://raw.githubusercontent.com/SudoSuOps/Swarn-chain/main/infra/deploy.sh
bash deploy.sh swarmchain.example.com
```

Replace `swarmchain.example.com` with your actual domain.

The script will:
1. Install Docker and dependencies
2. Clone the repository to `/opt/swarmchain`
3. Generate `.env.prod` with random Postgres password and API key
4. Build and start all containers
5. Obtain an SSL certificate via Let's Encrypt
6. Configure UFW firewall (SSH + HTTP + HTTPS only)
7. Set up automatic certificate renewal

**Save the API key printed at the end.** You need it for mining.

## 4. Verify Deployment

```bash
curl https://swarmchain.example.com/health
# Expected: {"status":"healthy","service":"swarmchain"}

curl https://swarmchain.example.com/metrics
# Expected: JSON with blocks, attempts, nodes, total_energy
```

## 5. Open the Dashboard

Navigate to `https://swarmchain.example.com/` in your browser.

## 6. Start Mining

From your local machine:

```bash
python mine_1000.py \
  --api-url https://swarmchain.example.com \
  --api-key <your-api-key>
```

The API key was printed during deployment. It is also stored in
`/opt/swarmchain/infra/.env.prod` on the server (the `SWARMCHAIN_API_KEY` line).

## 7. Monitor

```bash
# Live container logs
ssh root@<ip> "cd /opt/swarmchain && docker compose -f infra/docker-compose.prod.yml logs -f"

# Backend only
ssh root@<ip> "cd /opt/swarmchain && docker compose -f infra/docker-compose.prod.yml logs -f backend"

# Container status
ssh root@<ip> "cd /opt/swarmchain && docker compose -f infra/docker-compose.prod.yml ps"
```

## 8. Maintenance

### Backup Postgres

```bash
ssh root@<ip>
cd /opt/swarmchain
docker compose -f infra/docker-compose.prod.yml exec postgres \
  pg_dump -U swarmchain swarmchain > backup_$(date +%Y%m%d).sql
```

### Restore Postgres

```bash
cat backup_20260326.sql | docker compose -f infra/docker-compose.prod.yml exec -T postgres \
  psql -U swarmchain swarmchain
```

### Update Deployment

```bash
ssh root@<ip>
cd /opt/swarmchain
git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
```

### Certificate Renewal

Automatic via cron (daily at 3 AM). Manual renewal:

```bash
certbot renew
cd /opt/swarmchain
docker compose -f infra/docker-compose.prod.yml restart nginx
```

### Log Rotation

Docker handles log rotation by default. To configure explicit limits, add to
`/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
```

Then restart Docker: `systemctl restart docker`.

### View API Key

```bash
grep SWARMCHAIN_API_KEY /opt/swarmchain/infra/.env.prod
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `/health` returns unhealthy | `docker compose logs backend` -- look for DB connection errors |
| 502 Bad Gateway | `docker compose ps` -- is backend running? Check health with `docker compose logs backend` |
| SSL cert expired | `certbot renew && docker compose restart nginx` |
| Cannot connect | `ufw status` -- ensure 80/443 are allowed |
| High memory | `docker stats` -- consider upgrading droplet or reducing worker count in compose |
