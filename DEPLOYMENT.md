# Deployment Guide (Story 8.3)

**Issue:** #37  
**Status:** ✅ COMPLETE

## Quick Deployment

Run the deployment script:
```bash
./deploy.sh
```

This will:
1. Check Python version (3.11+ required)
2. Create virtual environment
3. Install dependencies
4. Initialize database
5. Run tests
6. Create deployment info file

## Manual Deployment

### Prerequisites

- Python 3.11+
- PostgreSQL database
- YNAB API token
- (Optional) HashiCorp Vault

### Steps

1. **Clone Repository**
```bash
git clone https://github.com/cryptobirr/agent-ynab.git
cd agent-ynab
```

2. **Create Virtual Environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure Environment**

Option A: Using Vault (Recommended)
```bash
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='your-vault-token'

# Store secrets in Vault
vault kv put secret/ynab/credentials api_token=YOUR_YNAB_TOKEN
vault kv put secret/postgres/agent-ynab \
  host=localhost \
  port=5432 \
  database=agent_ynab \
  username=your_user \
  password=your_password
```

Option B: Using .env File
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. **Initialize Database**
```bash
python tools/ynab/transaction_tagger/atoms/db_init.py
```

6. **Run Tests**
```bash
pytest
```

7. **Start Application**
```bash
python main.py
```

## Production Deployment

### Using Systemd (Linux)

Create `/etc/systemd/system/ynab-tagger.service`:
```ini
[Unit]
Description=YNAB Transaction Tagger
After=network.target postgresql.service

[Service]
Type=simple
User=ynab
WorkingDirectory=/opt/agent-ynab
Environment="PATH=/opt/agent-ynab/.venv/bin"
Environment="VAULT_ADDR=http://127.0.0.1:8200"
Environment="VAULT_TOKEN=your-token"
ExecStart=/opt/agent-ynab/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable ynab-tagger
sudo systemctl start ynab-tagger
sudo systemctl status ynab-tagger
```

### Using Docker

Build image:
```bash
docker build -t ynab-tagger .
```

Run container:
```bash
docker run -d \
  --name ynab-tagger \
  -p 5000:5000 \
  -e VAULT_ADDR=http://vault:8200 \
  -e VAULT_TOKEN=your-token \
  ynab-tagger
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name ynab.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Enable HTTPS with Certbot:
```bash
sudo certbot --nginx -d ynab.yourdomain.com
```

## Security Checklist

- [ ] Use Vault for secrets (not .env in production)
- [ ] Enable HTTPS/TLS
- [ ] Restrict database access
- [ ] Use firewall rules
- [ ] Enable logging and monitoring
- [ ] Regular security updates
- [ ] Backup database regularly

## Monitoring

### Health Check
```bash
curl http://localhost:5000/
```

### Logs
```bash
# Systemd
sudo journalctl -u ynab-tagger -f

# Docker
docker logs -f ynab-tagger
```

### Database
```bash
psql -U postgres -d agent_ynab -c "SELECT COUNT(*) FROM transactions;"
```

## Backup

Backup database:
```bash
pg_dump agent_ynab > backup_$(date +%Y%m%d).sql
```

Restore database:
```bash
psql agent_ynab < backup_20250101.sql
```

## Troubleshooting

### Port Already in Use
```bash
lsof -ti:5000 | xargs kill -9
```

### Database Connection Failed
- Check PostgreSQL is running
- Verify credentials in Vault/.env
- Check firewall rules

### Import Errors
```bash
pip install -r requirements.txt --force-reinstall
```

## Rollback

```bash
git checkout previous-tag
./deploy.sh
sudo systemctl restart ynab-tagger
```

## Updates

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --upgrade
pytest  # Verify tests pass
sudo systemctl restart ynab-tagger
```
