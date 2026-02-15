#!/usr/bin/env python3
"""
Test script for Celery tasks
"""

from scheduler.tasks import full_cycle_task

if __name__ == '__main__':
    print("Testing Celery task...")
    result = full_cycle_task.delay('ethereum', 3)
    print(f"Task sent: {result.id}")
    print(f"Task result: {result.get(timeout=60)}")