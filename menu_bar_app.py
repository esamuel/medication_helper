import rumps
import webbrowser
import os
from pathlib import Path

class MedicationHelperStatusBarApp(rumps.App):
    def __init__(self):
        super(MedicationHelperStatusBarApp, self).__init__(
            "💊",  # Using an emoji as icon temporarily
            quit_button=None  # We'll add our own quit button
        )
        self.menu = [
            "Open Medication Helper",
            "Check Reminders",
            None,  # Separator
            "Quit"
        ]

    @rumps.clicked("Open Medication Helper")
    def open_app(self, _):
        webbrowser.open('http://localhost:5000')

    @rumps.clicked("Check Reminders")
    def check_reminders(self, _):
        # This will be implemented to show current reminders
        rumps.notification(
            title="Medication Helper",
            subtitle="Checking Reminders",
            message="Checking for due medications..."
        )

    @rumps.clicked("Quit")
    def quit_app(self, _):
        rumps.quit_application()

if __name__ == '__main__':
    app = MedicationHelperStatusBarApp()
    app.run()
