# How to Start the Server and Automatic Bot Creation

## Quick Start Guide

### 1. Start the Django Server

**Option A: Using run.py (Recommended)**
```bash
python run.py
```

**Option B: Using manage.py directly**
```bash
python manage.py runserver 0.0.0.0:3003
```

The server will start on port **3003** (as configured in your `.env`).

### 2. Expose Server Publicly (for Webhooks)

Since your `PUBLIC_URL` is set to `https://unimpeded-uncomical-nicol.ngrok-free.dev`, make sure ngrok is running:

```bash
ngrok http 3003 --domain=unimpeded-uncomical-nicol.ngrok-free.dev
```

Or if you need a new ngrok URL, update your `.env`:
```bash
PUBLIC_URL=https://your-new-ngrok-url.ngrok-free.dev
```

## Automatic Bot Creation Flow

### How It Works

1. **Connect Calendar**: User connects their Google Calendar or Microsoft Outlook via OAuth
2. **Events Sync**: When events are created/updated in the calendar:
   - Recall.ai sends a webhook to your server (`/webhooks/recall/calendar`)
   - Server syncs events from Recall.ai API
   - Events are saved to your Supabase database
3. **Automatic Bot Creation**: For each synced event:
   - ✅ Has a `meeting_url` (Google Meet, Zoom, Teams)
   - ✅ Has a `start_time` in the future
   - ✅ Doesn't already have a bot
   - **→ Bot is automatically created with `join_at` set to event start time**
4. **Bot Joins Automatically**: Recall.ai automatically joins the bot at the scheduled time

### Flow Diagram

```
User creates meeting in Google Calendar
         ↓
Recall.ai detects new event
         ↓
Recall.ai sends webhook → Your Server (/webhooks/recall/calendar)
         ↓
Server syncs events (sync_calendar_events)
         ↓
Event saved to database
         ↓
Check: Has meeting_url? Start time in future? No existing bot?
         ↓
YES → Create bot via Recall.ai API with join_at
         ↓
Bot scheduled to join at event start time
         ↓
Bot automatically joins meeting when it starts
```

## Manual Bot Creation (Optional)

If you want to manually create bots for existing events:

```bash
# Create bots for events starting in next 24 hours
python manage.py create_meeting_bots

# Create bots for next 48 hours
python manage.py create_meeting_bots --hours-ahead 48

# Dry run (see what would be created)
python manage.py create_meeting_bots --dry-run
```

## Testing the Flow

### 1. Start the Server

```bash
# Terminal 1: Start Django server
python run.py
```

### 2. Start Ngrok (if needed)

```bash
# Terminal 2: Start ngrok
ngrok http 3003 --domain=unimpeded-uncomical-nicol.ngrok-free.dev
```

### 3. Connect Calendar

1. Go to your app: `http://localhost:3003` (or your ngrok URL)
2. Sign in/Sign up
3. Connect your Google Calendar or Microsoft Outlook
4. Grant permissions

### 4. Create a Meeting

1. In your Google Calendar, create a new event
2. Add a Google Meet link (or Zoom/Teams link)
3. Set the meeting time to a future time
4. Save the event

### 5. Watch the Logs

You should see in your Django server console:

```
INFO: Received "calendar.sync_events" calendar webhook from Recall
INFO: Processing calendar.sync_events for calendar <id> with timestamp: ...
INFO: Fetched X events from Recall API
INFO: Created event <id> (<title>) for calendar <id>
INFO: ✓ Created bot <bot_id> for event <id> (will join at <time>)
```

### 6. Verify Bot Creation

Check your database or use the management command:

```bash
python manage.py create_meeting_bots --dry-run
```

## Environment Variables Check

Your `.env` file should have:

✅ **RECALL_API_KEY** - Set ✓  
✅ **RECALL_REGION** - Set to `us-west-2` ✓  
✅ **RECALL_API_HOST** - Set to `https://us-west-2.recall.ai` ✓  
✅ **PUBLIC_URL** - Set to your ngrok URL ✓  
✅ **Database credentials** - Set ✓  
✅ **OAuth credentials** - Set ✓  

## Troubleshooting

### Server won't start

1. **Check port is available**:
   ```bash
   netstat -ano | findstr :3003
   ```

2. **Check database connection**:
   ```bash
   python manage.py check
   ```

3. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

### Bots not being created

1. **Check event has meeting_url**:
   - Event must have a meeting link (Google Meet, Zoom, Teams)

2. **Check event start time**:
   - Event must be in the future (not past)

3. **Check logs**:
   - Look for error messages in Django console
   - Check for "Failed to create bot" warnings

4. **Check API credentials**:
   ```bash
   echo $RECALL_API_KEY
   echo $RECALL_REGION
   ```

### Webhooks not received

1. **Verify ngrok is running**:
   ```bash
   curl https://unimpeded-uncomical-nicol.ngrok-free.dev/webhooks/recall/calendar
   ```

2. **Check webhook URL in Recall.ai dashboard**:
   - Should be: `https://unimpeded-uncomical-nicol.ngrok-free.dev/webhooks/recall/calendar`

3. **Check server logs** for webhook requests

## Scheduled Bot Creation (Alternative)

If you prefer to create bots on a schedule instead of automatically during sync:

1. **Set up a cron job** (Linux/Mac):
   ```bash
   # Run every hour
   0 * * * * cd /path/to/recallai && python manage.py create_meeting_bots
   ```

2. **Or use Windows Task Scheduler**:
   - Create a task that runs: `python manage.py create_meeting_bots`
   - Set to repeat every hour

## Summary

✅ **Automatic**: Bots are created automatically when events are synced  
✅ **Scheduled**: Bots use `join_at` to join at event start time  
✅ **No Polling**: No need to check for upcoming meetings manually  
✅ **Seamless**: Works with your existing calendar sync flow  

Just start the server, connect your calendar, and create meetings with meeting links - bots will be created automatically!

