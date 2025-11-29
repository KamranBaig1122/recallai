import requests
from django.conf import settings
from urllib.parse import urlencode


class RecallApiClient:
    def __init__(self, api_key=None, api_host=None):
        self.api_key = api_key or settings.RECALL_API_KEY
        # If api_host is provided, use it; otherwise use settings or default
        if api_host:
            self.api_host = api_host
        else:
            self.api_host = settings.RECALL_API_HOST
    
    def build_url(self, path, query_params=None):
        url = f"{self.api_host}{path}"
        if query_params:
            # Filter out None values
            filtered_params = {k: v for k, v in query_params.items() if v is not None}
            if filtered_params:
                url += "?" + urlencode(filtered_params)
        return url
    
    def request(self, path=None, url=None, method='GET', data=None, query_params=None):
        if not url:
            url = self.build_url(path, query_params)
        
        headers = {
            'Authorization': f'Token {self.api_key}',
            'Content-Type': 'application/json',
        }
        
        print(f'Making {method} request to {url} with token {self.api_key}...')
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f'Unsupported method: {method}')
        
        if response.status_code > 299:
            error_msg = f'{method} request failed with status {response.status_code}'
            if response.status_code < 500:
                error_msg += f', response body: {response.text}'
            raise Exception(error_msg)
        
        if response.status_code == 204 or not response.content:
            return None
        
        return response.json()


# Singleton instance
_client = None

def get_client():
    global _client
    if _client is None:
        _client = RecallApiClient()
    return _client

