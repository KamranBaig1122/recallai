# Deployment Checklist for recallaiserver.inviteellie.ai

## ✅ Pre-Deployment Checklist

### 1. Environment Variables
Set these on your production server:

```bash
# Core Configuration
PUBLIC_URL=https://recallaiserver.inviteellie.ai
FRONTEND_URL=https://inviteellie.ai  # Adjust if your frontend is on a different domain
PORT=3003
NODE_ENV=production
DEBUG=False
SECRET=<generate-a-strong-secret-key>

# Database (Supabase)
SUPABASE_DB_URI=postgresql://...  # OR use individual variables below
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your_password
SUPABASE_DB_HOST=your-host.supabase.co
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres

# Recall.ai
RECALL_API_KEY=your-recall-api-key
RECALL_API_HOST=https://api.recall.ai  # or region-specific

# OAuth
GOOGLE_CALENDAR_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET=your-google-client-secret
MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID=your-microsoft-client-id
MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET=your-microsoft-client-secret

# Transcription Services
USE_ASSEMBLY_AI=true
ASSEMBLY_AI_API_KEY=your-assemblyai-api-key
GROQ_API_KEY=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

# Redis (Optional - for production WebSocket support)
REDIS_URL=redis://localhost:6379
```

### 2. Update OAuth Redirect URIs

**Google Calendar:**
- Go to: https://console.cloud.google.com/apis/credentials
- Update authorized redirect URI: `https://recallaiserver.inviteellie.ai/oauth-callback/google-calendar`

**Microsoft Outlook:**
- Go to: https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps
- Update redirect URI: `https://recallaiserver.inviteellie.ai/oauth-callback/microsoft-outlook`

### 3. Update Recall.ai Dashboard

**Calendar Webhooks:**
- URL: `https://recallaiserver.inviteellie.ai/webhooks/recall/calendar`
- Go to: https://us-west-2.recall.ai/dashboard (or your region)

**AssemblyAI Configuration:**
- Go to: https://us-west-2.recall.ai/dashboard/transcription
- Add your AssemblyAI API key

### 4. SSL/HTTPS Configuration
- ✅ Domain is configured: `recallaiserver.inviteellie.ai`
- ✅ SSL certificate is installed
- ✅ Nginx/Apache is configured to proxy to port 3003
- ✅ WebSocket support is enabled in proxy configuration

### 5. Database
- [ ] Run migrations: `python manage.py migrate`
- [ ] Verify database connection works
- [ ] Test with a sample query

### 6. Static Files
- [ ] Run: `python manage.py collectstatic --noinput`
- [ ] Verify static files are accessible: `https://recallaiserver.inviteellie.ai/static/ellie-logo.svg`

### 7. Code Updates
- ✅ `settings.py` updated with production domain in `CSRF_TRUSTED_ORIGINS`
- ✅ All webhook URLs use `PUBLIC_URL` environment variable
- ✅ No hardcoded localhost URLs (except as fallbacks)

## 🧪 Post-Deployment Testing

### Test Endpoints

1. **Health Check:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/
   ```

2. **Webhook Endpoint:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/webhooks/recall/calendar
   ```

3. **Bot Webhook:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/wh
   ```

4. **Static Files:**
   ```bash
   curl https://recallaiserver.inviteellie.ai/static/ellie-logo.svg
   ```

5. **OAuth Callback (should redirect):**
   ```bash
   curl -I https://recallaiserver.inviteellie.ai/oauth-callback/google-calendar
   ```

### Test Full Flow

1. **Connect Calendar:**
   - Go to frontend integrations page
   - Connect Google Calendar or Outlook
   - Verify OAuth redirect works

2. **Create Test Meeting:**
   - Create a test meeting in your calendar
   - Verify webhook is received
   - Check bot is created automatically

3. **Test Transcription:**
   - Join the meeting
   - Speak during meeting
   - Verify real-time transcripts appear
   - End meeting
   - Verify summary and action items are generated

## 🔧 Production Optimizations

### Recommended: Use Redis for Channel Layers

Update `settings.py`:

```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(os.getenv('REDIS_HOST', 'localhost'), int(os.getenv('REDIS_PORT', 6379)))],
        },
    },
}
```

Install: `pip install channels-redis`

### Recommended: Use Production ASGI Server

Instead of `runserver`, use:
- **Uvicorn:** `uvicorn recallai.asgi:application --host 0.0.0.0 --port 3003`
- **Daphne:** `daphne -b 0.0.0.0 -p 3003 recallai.asgi:application`

### Recommended: Set up Logging

Add to `settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/recallai/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

## 📝 Notes

- The code already uses environment variables for all configuration
- `PUBLIC_URL` is used throughout for webhooks and OAuth callbacks
- `CSRF_TRUSTED_ORIGINS` includes the production domain
- All localhost references are fallbacks only
- WebSocket URLs are automatically generated from `PUBLIC_URL`

## 🚨 Important Reminders

1. **Never commit `.env` file** - Keep all secrets in environment variables
2. **Set `DEBUG=False`** in production
3. **Use strong `SECRET` key** - Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
4. **Enable HTTPS** - OAuth and webhooks require HTTPS
5. **Monitor logs** - Set up log monitoring for errors
6. **Backup database** - Configure automated backups

