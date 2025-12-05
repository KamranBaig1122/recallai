# Deployment Guide for recallaiserver.inviteellie.ai

This guide covers the deployment configuration for the production server at `https://recallaiserver.inviteellie.ai/`.

## Environment Variables

Set the following environment variables on your production server:

### Required Variables

```bash
# Server Configuration
PUBLIC_URL=https://recallaiserver.inviteellie.ai
FRONTEND_URL=https://inviteellie.ai  # Your frontend domain (adjust if different)
PORT=3003

# Django Configuration
SECRET=<your-django-secret-key>
NODE_ENV=production  # Set to 'production' to disable DEBUG mode
DEBUG=False  # Explicitly set to False for production

# Database (Supabase PostgreSQL)
SUPABASE_DB_URI=postgresql://user:password@host:port/dbname
# OR use individual variables:
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your_password
SUPABASE_DB_HOST=your-supabase-host.supabase.co
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres

# Recall.ai API
RECALL_API_KEY=your-recall-api-key
RECALL_API_HOST=https://api.recall.ai  # or your region-specific host

# OAuth (Google Calendar)
GOOGLE_CALENDAR_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET=your-google-client-secret

# OAuth (Microsoft Outlook)
MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID=your-microsoft-client-id
MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET=your-microsoft-client-secret

# AssemblyAI (Optional - for transcription)
USE_ASSEMBLY_AI=true
ASSEMBLY_AI_API_KEY=your-assemblyai-api-key

# Groq (for summary and action items generation)
GROQ_API_KEY=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

# Redis (Optional - for production WebSocket support)
REDIS_URL=redis://localhost:6379  # or your Redis server URL
```

## Webhook Configuration

### Recall.ai Dashboard Settings

1. **Calendar Webhooks:**
   - Go to: https://us-west-2.recall.ai/dashboard (or your region)
   - Set webhook URL: `https://recallaiserver.inviteellie.ai/webhooks/recall/calendar`

2. **Bot Webhooks:**
   - Bot webhooks are configured automatically when creating bots
   - Webhook URL: `https://recallaiserver.inviteellie.ai/wh`

3. **AssemblyAI Configuration:**
   - Go to: https://us-west-2.recall.ai/dashboard/transcription
   - Add your AssemblyAI API key in the dashboard
   - This is required for real-time transcription

### OAuth Redirect URIs

Update your OAuth applications with the production URLs:

**Google Calendar OAuth:**
- Authorized redirect URIs: `https://recallaiserver.inviteellie.ai/oauth-callback/google-calendar`

**Microsoft Outlook OAuth:**
- Redirect URIs: `https://recallaiserver.inviteellie.ai/oauth-callback/microsoft-outlook`

## Server Configuration

### Nginx Configuration (if using Nginx)

```nginx
server {
    listen 80;
    server_name recallaiserver.inviteellie.ai;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name recallaiserver.inviteellie.ai;

    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;

    # Proxy to Django/ASGI server
    location / {
        proxy_pass http://127.0.0.1:3003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_read_timeout 86400;
    }

    # Static files
    location /static/ {
        alias /path/to/recallai/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### Systemd Service (for running Django server)

Create `/etc/systemd/system/recallai.service`:

```ini
[Unit]
Description=Recall.ai Django Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/recallai
Environment="PATH=/path/to/recallai/venv/bin"
ExecStart=/path/to/recallai/venv/bin/python manage.py runserver 0.0.0.0:3003
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

For production with ASGI (Daphne/Uvicorn):

```ini
[Unit]
Description=Recall.ai ASGI Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/recallai
Environment="PATH=/path/to/recallai/venv/bin"
ExecStart=/path/to/recallai/venv/bin/daphne -b 0.0.0.0 -p 3003 recallai.asgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Database Migrations

Run migrations on production:

```bash
cd /path/to/recallai
source venv/bin/activate
python manage.py migrate
```

## Static Files

Collect static files:

```bash
python manage.py collectstatic --noinput
```

## Security Checklist

- [ ] Set `DEBUG=False` in production
- [ ] Set a strong `SECRET` key
- [ ] Use HTTPS (SSL/TLS certificates)
- [ ] Update `ALLOWED_HOSTS` in settings.py (already set to `['*']` for EC2)
- [ ] Update `CSRF_TRUSTED_ORIGINS` with production domain
- [ ] Secure database credentials
- [ ] Use environment variables for all secrets
- [ ] Enable firewall rules (only allow necessary ports)
- [ ] Set up SSL certificates (Let's Encrypt recommended)

## Testing Deployment

1. **Test webhook endpoint:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/webhooks/recall/calendar
   ```

2. **Test bot webhook:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/wh
   ```

3. **Test static files:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/static/ellie-logo.svg
   ```

4. **Test OAuth callback:**
   - Try connecting a calendar through the frontend
   - Verify redirect works: `https://recallaiserver.inviteellie.ai/oauth-callback/google-calendar`

## Monitoring

- Check server logs: `journalctl -u recallai -f`
- Monitor Django logs for errors
- Check webhook delivery in Recall.ai dashboard
- Monitor database connections (Supabase dashboard)

## Troubleshooting

### Webhooks not working
- Verify `PUBLIC_URL` is set correctly
- Check firewall allows incoming connections
- Verify SSL certificate is valid
- Check Recall.ai dashboard webhook configuration

### OAuth not working
- Verify redirect URIs match exactly in OAuth provider
- Check `PUBLIC_URL` environment variable
- Verify SSL certificate is valid (OAuth requires HTTPS)

### Database connection issues
- Verify `SUPABASE_DB_URI` or individual DB variables
- Check Supabase connection pooler settings
- Verify SSL mode is set to 'require'

### WebSocket not working
- Verify WebSocket upgrade headers in Nginx
- Check `proxy_read_timeout` is set high enough
- For production, consider using Redis channel layer instead of InMemoryChannelLayer

## Production Recommendations

1. **Use Redis for Channel Layers:**
   ```python
   CHANNEL_LAYERS = {
       'default': {
           'BACKEND': 'channels_redis.core.RedisChannelLayer',
           'CONFIG': {
               "hosts": [("localhost", 6379)],
           },
       },
   }
   ```

2. **Use Gunicorn/Uvicorn for ASGI:**
   - Install: `pip install uvicorn[standard]`
   - Run: `uvicorn recallai.asgi:application --host 0.0.0.0 --port 3003`

3. **Set up log rotation:**
   - Configure logrotate for Django logs
   - Monitor error logs regularly

4. **Backup database:**
   - Set up automated Supabase backups
   - Or configure PostgreSQL backups if using self-hosted DB

