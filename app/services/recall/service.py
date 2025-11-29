from .api_client import get_client


class RecallService:
    def __init__(self):
        self.client = get_client()
    
    def create_calendar(self, data):
        return self.client.request(
            path='/api/v2/calendars/',
            method='POST',
            data=data
        )
    
    def get_calendar(self, calendar_id):
        return self.client.request(
            path=f'/api/v2/calendars/{calendar_id}/',
            method='GET'
        )
    
    def update_calendar(self, calendar_id, data):
        return self.client.request(
            path=f'/api/v2/calendars/{calendar_id}/',
            method='PATCH',
            data=data
        )
    
    def delete_calendar(self, calendar_id):
        return self.client.request(
            path=f'/api/v2/calendars/{calendar_id}/',
            method='DELETE'
        )
    
    def fetch_calendar_events(self, calendar_id, last_updated_timestamp=None):
        """
        Fetch calendar events from Recall API with pagination.
        Similar to calendar-integration-demo/v2-demo/services/recall/index.js fetchCalendarEvents
        """
        events = []
        
        # Build query params
        query_params = {
            'calendar_id': calendar_id,
        }
        # Only add timestamp filter if provided
        if last_updated_timestamp:
            query_params['updated_at__gte'] = last_updated_timestamp
        
        page_url = self.client.build_url('/api/v2/calendar-events/', query_params)
        
        print(f'INFO: Fetching calendar events for calendar_id={calendar_id}, timestamp={last_updated_timestamp}')
        
        while True:
            try:
                response = self.client.request(url=page_url, method='GET')
                if not response:
                    break
                    
                results = response.get('results', [])
                if results:
                    events.extend(results)
                    print(f'INFO: Fetched {len(results)} events (total so far: {len(events)})')
                else:
                    print(f'INFO: No events in this page')
                
                next_url = response.get('next')
                if not next_url:
                    break
                
                # Fix http:// to https:// if needed (like JS project)
                if 'https:' not in next_url and 'https:' in page_url:
                    next_url = next_url.replace('http:', 'https:')
                
                page_url = next_url
            except Exception as e:
                print(f'ERROR: Failed to fetch events page: {e}')
                import traceback
                traceback.print_exc()
                break
        
        print(f'INFO: Total events fetched: {len(events)}')
        return events
    
    def add_bot_to_calendar_event(self, event_id, deduplication_key, bot_config):
        return self.client.request(
            path=f'/api/v2/calendar-events/{event_id}/bot/',
            method='POST',
            data={
                'deduplication_key': deduplication_key,
                'bot_config': bot_config,
            }
        )
    
    def remove_bot_from_calendar_event(self, event_id):
        return self.client.request(
            path=f'/api/v2/calendar-events/{event_id}/bot/',
            method='DELETE'
        )
    
    def create_bot(self, meeting_url, bot_name="Meeting Notetaker", join_at=None, 
                   platform=None, meeting_password=None, recording_config=None, region=None):
        """
        Create a bot using Recall.ai API v1
        
        Args:
            meeting_url: Full meeting URL (Zoom/Google Meet/Teams)
            bot_name: Bot display name
            join_at: ISO 8601 datetime string for scheduled join (optional)
            platform: Platform name (auto-detected if None)
            meeting_password: Meeting password if required
            recording_config: Recording configuration dict
            region: API region (us-east-1, us-west-2, eu-central-1, ap-northeast-1)
            
        Returns:
            Bot data including bot_id
        """
        # Determine API host based on region
        import os
        from django.conf import settings
        
        if region:
            api_host = f"https://{region}.recall.ai"
        else:
            # Try to get region from environment or use default
            recall_region = os.getenv('RECALL_REGION', 'us-west-2')
            api_host = f"https://{recall_region}.recall.ai"
        
        # Create a temporary client with the region-specific host
        from .api_client import RecallApiClient
        region_client = RecallApiClient(api_host=api_host)
        
        # Use v1 API for bot creation (as per official docs)
        body = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
        }
        
        if join_at:
            body["join_at"] = join_at
        
        if platform:
            body["platform"] = platform
        
        if meeting_password:
            body["meeting_password"] = meeting_password
        
        if recording_config:
            body["recording_config"] = recording_config
        
        return region_client.request(
            path='/api/v1/bot/',
            method='POST',
            data=body
        )
    
    def get_bot(self, bot_id, region=None):
        """Get bot data by ID"""
        import os
        
        if region:
            api_host = f"https://{region}.recall.ai"
        else:
            recall_region = os.getenv('RECALL_REGION', 'us-west-2')
            api_host = f"https://{recall_region}.recall.ai"
        
        from .api_client import RecallApiClient
        region_client = RecallApiClient(api_host=api_host)
        
        return region_client.request(
            path=f'/api/v1/bot/{bot_id}/',
            method='GET'
        )


# Singleton instance
_service = None

def get_service():
    global _service
    if _service is None:
        _service = RecallService()
    return _service

