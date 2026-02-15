#!/usr/bin/env python3
"""
Run background collector with auto-reload on file changes
"""

import subprocess
import time
import os
import sys
from pathlib import Path

def get_file_modification_times():
    """Get modification times for all Python files"""
    files_to_watch = [
        'background_collector.py',
        'config/settings.py',
        'database/models.py',
        'trading/trade_manager.py',
        'trading/mexc_client.py',
        'analyzers/ai_adapter.py',
        'analyzers/signal_generator.py',
        'telegram/bot.py',
        'collectors/dex_paprika.py'
    ]

    mod_times = {}
    for file_path in files_to_watch:
        if os.path.exists(file_path):
            mod_times[file_path] = os.path.getmtime(file_path)
    return mod_times

def files_changed(old_times):
    """Check if any files have been modified"""
    new_times = get_file_modification_times()
    for file_path, new_time in new_times.items():
        if file_path not in old_times or old_times[file_path] != new_time:
            return True
    return False

def main():
    print("🚀 Starting background collector with auto-reload...")

    # Get initial file modification times
    mod_times = get_file_modification_times()

    while True:
        try:
            print(f"📊 Starting background collector (PID: {os.getpid()})")
            print(f"🔍 Watching files: {list(mod_times.keys())}")

            # Start the background collector
            process = subprocess.Popen([
                sys.executable, 'background_collector.py'
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            # Monitor for file changes and output in real-time
            while process.poll() is None:  # While process is still running
                # Read any available output
                if process.stdout:
                    line = process.stdout.readline()
                    if line:
                        print(line.rstrip())  # Print output in real-time

                if files_changed(mod_times):
                    print("🔄 File changes detected, restarting background collector...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
                time.sleep(0.1)  # Check more frequently

            # Update modification times
            mod_times = get_file_modification_times()

            if process.poll() is not None:
                # Process ended, print any remaining output and restart
                remaining_output, _ = process.communicate()
                if remaining_output:
                    print("Remaining process output:")
                    print(remaining_output)

                print("🔄 Process ended, restarting in 3 seconds...")
                time.sleep(3)

        except KeyboardInterrupt:
            print("🛑 Received interrupt signal, stopping...")
            if 'process' in locals():
                process.terminate()
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)  # Wait before retrying

if __name__ == '__main__':
    main()