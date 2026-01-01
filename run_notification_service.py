r"""
Continuous notification service runner.

This script runs the check_unresolved_meetings command in a loop,
checking for unresolved meetings at the configured interval.

The service reads configuration from environment variables:
- UNRESOLVED_MEETING_CHECK_INTERVAL_MINUTES: How often to check (default: 5)
- UNRESOLVED_MEETING_NOTIFICATION_THRESHOLD_MINUTES: When to notify after meeting ends (default: 10)

Usage:
    # Activate virtual environment first
    cd recallai
    .\venv\Scripts\activate
    
    # Run the service
    python run_notification_service.py
    
    # Or run in background (Windows)
    pythonw run_notification_service.py
    
    # Or use the batch file
    run_notification_service.bat
"""

import os
import sys
import time
from pathlib import Path
import logging
from datetime import datetime

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'recallai.settings')

import django
django.setup()

from django.conf import settings
from django.core.management import call_command

# Configure logging
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / f'notification_service_{datetime.now().strftime("%Y%m%d")}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)

logger = logging.getLogger(__name__)


def run_notification_check():
    """Run the notification check command."""
    try:
        logger.info('=' * 80)
        logger.info(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Running notification check...')
        
        # Call the Django management command
        call_command('check_unresolved_meetings', verbosity=1)
        
        logger.info(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Notification check completed successfully')
        logger.info('=' * 80)
        return True
    except KeyboardInterrupt:
        logger.info('Notification check interrupted by user')
        raise
    except Exception as e:
        logger.error(f'Error running notification check: {e}', exc_info=True)
        return False


def main():
    """Main service loop."""
    # Get configuration from environment variables (via Django settings)
    check_interval_minutes = settings.UNRESOLVED_MEETING_CHECK_INTERVAL_MINUTES
    threshold_minutes = settings.UNRESOLVED_MEETING_NOTIFICATION_THRESHOLD_MINUTES
    check_interval_seconds = check_interval_minutes * 60
    
    django_settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'recallai.settings')
    
    logger.info('=' * 80)
    logger.info('NOTIFICATION SERVICE STARTED')
    logger.info('=' * 80)
    logger.info(f'Configuration:')
    logger.info(f'  - Check Interval: {check_interval_minutes} minutes ({check_interval_seconds} seconds)')
    logger.info(f'  - Notification Threshold: {threshold_minutes} minutes after meeting ends')
    logger.info(f'  - Log File: {LOG_FILE}')
    logger.info(f'  - Django Settings Module: {django_settings_module}')
    logger.info('=' * 80)
    logger.info('Service is running. Press Ctrl+C to stop.')
    logger.info('=' * 80)
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    try:
        while True:
            try:
                # Run the check
                success = run_notification_check()
                
                if success:
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f'Too many consecutive errors ({consecutive_errors}). Stopping service.')
                        sys.exit(1)
                
                # Wait for the next interval
                logger.info(f'Waiting {check_interval_minutes} minute(s) until next check...')
                logger.info('')
                
                # Sleep in smaller chunks to allow for graceful shutdown
                sleep_chunk = 10  # Check every 10 seconds if we should continue
                slept = 0
                while slept < check_interval_seconds:
                    time.sleep(min(sleep_chunk, check_interval_seconds - slept))
                    slept += sleep_chunk
                    
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f'Unexpected error in service loop: {e}', exc_info=True)
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f'Too many consecutive errors ({consecutive_errors}). Stopping service.')
                    sys.exit(1)
                # Wait a bit before retrying
                time.sleep(30)
                
    except KeyboardInterrupt:
        logger.info('=' * 80)
        logger.info('NOTIFICATION SERVICE STOPPED BY USER')
        logger.info('=' * 80)
        sys.exit(0)
    except Exception as e:
        logger.error(f'Fatal error in notification service: {e}', exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

