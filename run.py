#!/usr/bin/env python
"""
Simple script to run the Django development server
"""
import os
import sys
from django.core.management import execute_from_command_line

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'recallai.settings')
    
    # Get port from environment or use default
    port = os.getenv('PORT', '3003')
    
    # Run migrations first
    print("Running migrations...")
    execute_from_command_line(['manage.py', 'migrate'])
    
    # Start server
    print(f"Starting server on port {port}...")
    execute_from_command_line(['manage.py', 'runserver', f'0.0.0.0:{port}'])

