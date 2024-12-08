import sqlite3
import schedule
import time
from datetime import datetime
import os
import platform
import subprocess
from pathlib import Path

DB_PATH = Path(__file__).parent / 'medications.db'

def get_due_reminders():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_time = datetime.now().strftime('%H:%M')
    
    cursor.execute('''
        SELECT r.id, r.time, r.message, m.name
        FROM reminders r
        LEFT JOIN medications m ON r.medication_id = m.id
        WHERE r.time = ?
    ''', (current_time,))
    
    reminders = cursor.fetchall()
    conn.close()
    return reminders

def play_notification_sound():
    if platform.system() == 'Darwin':  # macOS
        subprocess.run(['osascript', '-e', 'display notification "Time to take your medication!" with title "Medication Reminder" sound name "Glass"'])
    elif platform.system() == 'Linux':
        os.system('paplay /usr/share/sounds/freedesktop/stereo/complete.oga')
    elif platform.system() == 'Windows':
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)

def check_reminders():
    reminders = get_due_reminders()
    for reminder in reminders:
        _, time, message, med_name = reminder
        title = f"Medication Reminder: {med_name}" if med_name else "Medication Reminder"
        
        # Send system notification with sound
        if platform.system() == 'Darwin':  # macOS
            notification_text = message or f"Time to take {med_name}!"
            script = f'''
            display notification "{notification_text}" with title "{title}" sound name "Glass"
            '''
            subprocess.run(['osascript', '-e', script])
        else:
            # Play sound for other platforms
            play_notification_sound()

def run_scheduler():
    # Check reminders every minute
    schedule.every().minute.do(check_reminders)
    
    print("Reminder service started. Checking for reminders every minute...")
    while True:
        schedule.run_pending()
        time.sleep(30)  # Sleep for 30 seconds between checks

if __name__ == '__main__':
    print("Starting reminder service...")
    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("\nStopping reminder service...")
