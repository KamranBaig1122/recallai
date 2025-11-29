"""
Static file serving for logo and other assets
"""
from django.http import HttpResponse, FileResponse
from django.conf import settings
from pathlib import Path
import os


def serve_logo(request):
    """Serve the Ellie logo"""
    logo_path = Path(settings.BASE_DIR) / 'static' / 'ellie-logo.svg'
    
    if logo_path.exists():
        return FileResponse(
            open(logo_path, 'rb'),
            content_type='image/svg+xml',
            headers={
                'Cache-Control': 'public, max-age=3600',
                'Access-Control-Allow-Origin': '*'
            }
        )
    else:
        return HttpResponse('Logo not found', status=404)

