"""
Management command to retrieve completed bot recordings
Run this periodically (e.g., via cron) to auto-retrieve completed recordings
"""
from django.core.management.base import BaseCommand
from app.logic.bot_retriever import check_and_retrieve_completed_bots


class Command(BaseCommand):
    help = 'Check and retrieve completed bot recordings'

    def handle(self, *args, **options):
        self.stdout.write('Checking for completed bot recordings...')
        
        result = check_and_retrieve_completed_bots()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Retrieved {result["retrieved"]} recordings, {result["errors"]} errors'
            )
        )

