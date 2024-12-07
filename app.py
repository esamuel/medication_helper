from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import zoneinfo
import os
from dotenv import load_dotenv
import sys
import logging
import time

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info('Starting up the Flask application...')

# Initialize Flask app
app = Flask(__name__)

# Set timezone to local timezone (Israel)
local_timezone = zoneinfo.ZoneInfo("Asia/Jerusalem")

@app.template_filter('format_age')
def format_age(dob):
    if not dob:
        return ""
    today = datetime.now(local_timezone)
    # Convert dob to timezone-aware if it's naive
    if dob.tzinfo is None:
        dob = dob.replace(tzinfo=local_timezone)
    
    years = today.year - dob.year
    months = today.month - dob.month
    
    if today.day < dob.day:
        months -= 1
    
    if months < 0:
        years -= 1
        months += 12
        
    return f"{years} years, {months} months"

# Set secret key - use environment variable if available, otherwise use a default for development
if os.environ.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    logger.info('Using production secret key from environment')
else:
    logger.warning('No SECRET_KEY in environment, using development key. DO NOT use in production!')
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

# Configure SQLAlchemy
try:
    # Use SQLite by default
    database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'medication_helper.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    logger.info('Successfully configured SQLite database')
except Exception as e:
    logger.error(f'Fatal database initialization error: {str(e)}')
    sys.exit(1)

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.DateTime(timezone=True))
    gender = db.Column(db.String(20))
    height = db.Column(db.Float)  # in cm
    weight = db.Column(db.Float)  # in kg
    blood_type = db.Column(db.String(10))
    allergies = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(local_timezone))
    last_updated = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(local_timezone), onupdate=lambda: datetime.now(local_timezone))

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(100))
    time = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(local_timezone))
    reminder_enabled = db.Column(db.Boolean, default=False)
    reminder_times = db.Column(db.String(500))  # Store times as JSON string
    last_reminded = db.Column(db.DateTime(timezone=True))

class BloodPressure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_time = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(local_timezone))
    systolic = db.Column(db.Integer)  # mmHg
    diastolic = db.Column(db.Integer)  # mmHg
    pulse = db.Column(db.Integer)  # bpm
    notes = db.Column(db.Text)

class BloodTests(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_time = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(local_timezone))
    blood_sugar = db.Column(db.Float)  # mg/dL
    oxygen_saturation = db.Column(db.Integer)  # percentage
    notes = db.Column(db.Text)

class EmergencyContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    relationship = db.Column(db.String(50), nullable=False)
    phone_primary = db.Column(db.String(20), nullable=False)
    phone_secondary = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(local_timezone))
    last_updated = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(local_timezone), onupdate=lambda: datetime.now(local_timezone))

def convert_blood_sugar():
    """Convert blood sugar values from mmol/L to mg/dL"""
    try:
        with app.app_context():
            blood_tests = BloodTests.query.all()
            for test in blood_tests:
                if test.blood_sugar is not None:
                    # Convert from mmol/L to mg/dL (multiplication factor is approximately 18)
                    test.blood_sugar = round(test.blood_sugar * 18.0, 1)
            db.session.commit()
            logger.info("Blood sugar values converted successfully")
    except Exception as e:
        logger.error(f"Error converting blood sugar values: {str(e)}")
        db.session.rollback()

def init_db(add_sample_data=False):
    """Initialize the database and optionally add sample data."""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            logger.info("Database tables created successfully")

            # Convert blood sugar values from mmol/L to mg/dL
            convert_blood_sugar()

            if add_sample_data:
                # Only add sample data if explicitly requested
                # Check if we already have a profile
                if not UserProfile.query.first():
                    # Add a sample profile
                    sample_profile = UserProfile(
                        name="John Doe",
                        date_of_birth=datetime(1980, 1, 1, tzinfo=local_timezone),
                        gender="Male",
                        height=175.0,
                        weight=70.0,
                        blood_type="A+",
                        allergies="None",
                        medical_conditions="None"
                    )
                    db.session.add(sample_profile)

                # Add sample medications if none exist
                if not Medication.query.first():
                    sample_medications = [
                        Medication(
                            name="Aspirin",
                            dosage="100mg",
                            frequency="Daily",
                            time="08:00",
                            notes="Take with food"
                        ),
                        Medication(
                            name="Vitamin D",
                            dosage="1000 IU",
                            frequency="Daily",
                            time="09:00",
                            notes="Take with breakfast"
                        )
                    ]
                    for med in sample_medications:
                        db.session.add(med)

                # Add sample blood pressure if none exist
                if not BloodPressure.query.first():
                    sample_blood_pressure = BloodPressure(
                        systolic=120,
                        diastolic=80,
                        pulse=72,
                        notes="Regular checkup"
                    )
                    db.session.add(sample_blood_pressure)

                # Add sample blood tests if none exist
                if not BloodTests.query.first():
                    sample_blood_test = BloodTests(
                        blood_sugar=100,  # This is now in mg/dL
                        oxygen_saturation=98,
                        notes="Regular checkup"
                    )
                    db.session.add(sample_blood_test)

                # Add sample emergency contact if none exist
                if not EmergencyContact.query.first():
                    sample_contact = EmergencyContact(
                        name="Jane Doe",
                        relationship="Spouse",
                        phone_primary="+1-555-0123",
                        phone_secondary="+1-555-0124",
                        email="jane.doe@example.com",
                        address="123 Main St, Anytown, USA",
                        notes="Primary emergency contact"
                    )
                    db.session.add(sample_contact)

                # Commit all sample data
                db.session.commit()
                logger.info("Sample data added successfully")
            
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        db.session.rollback()
        raise

# Initialize database when the app starts, but NEVER add sample data
init_db(add_sample_data=False)

@app.route('/')
def index():
    try:
        # Get the current time
        current_time = datetime.now(local_timezone)
        
        # Get the current user's profile
        profile = UserProfile.query.first()
        if not profile:
            # Create a default profile if none exists
            profile = UserProfile(
                name="Default User",
                date_of_birth=current_time,
                weight=0,
                height=0
            )
            try:
                db.session.add(profile)
                db.session.commit()
            except Exception as e:
                logger.error(f"Error creating default profile: {str(e)}")
                db.session.rollback()
                flash("Error creating default profile", "error")
                return render_template('error.html'), 500
        
        # Get latest blood pressure with error handling
        try:
            latest_blood_pressure = BloodPressure.query.order_by(BloodPressure.date_time.desc()).first()
        except Exception as e:
            logger.error(f"Error fetching blood pressure: {str(e)}")
            latest_blood_pressure = None
        
        # Get latest blood tests with error handling
        try:
            latest_blood_tests = BloodTests.query.order_by(BloodTests.date_time.desc()).first()
        except Exception as e:
            logger.error(f"Error fetching blood tests: {str(e)}")
            latest_blood_tests = None
        
        # Get medications with error handling
        try:
            medications = Medication.query.all()
            
            # Process medication times safely
            for med in medications:
                try:
                    if med.reminder_times and med.reminder_times.strip():
                        # If reminder_times exists and is not empty, use the first time
                        times = med.reminder_times.split(',')
                        med.time = times[0].strip() if times else "08:00"
                    else:
                        # Default to morning if no specific time is set
                        med.time = "08:00"
                except Exception as e:
                    logger.error(f"Error processing medication times for med {med.id}: {str(e)}")
                    med.time = "08:00"  # Set default time on error
                    
        except Exception as e:
            logger.error(f"Error fetching medications: {str(e)}")
            medications = []
            
        return render_template('index.html',
                             profile=profile,
                             latest_blood_pressure=latest_blood_pressure,
                             latest_blood_tests=latest_blood_tests,
                             medications=medications,
                             current_time=current_time)
                             
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        db.session.rollback()  # Ensure any failed transaction is rolled back
        flash("An error occurred while loading the page", "error")
        return render_template('error.html'), 500

@app.route('/add', methods=['GET', 'POST'])
def add_medication():
    if request.method == 'POST':
        name = request.form['name']
        dosage = request.form['dosage']
        frequency = request.form['frequency']
        time = request.form['time']
        notes = request.form['notes']

        new_medication = Medication(
            name=name,
            dosage=dosage,
            frequency=frequency,
            time=time,
            notes=notes
        )

        try:
            db.session.add(new_medication)
            db.session.commit()
            flash('Medication added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f'Error adding medication: {str(e)}')
            flash('There was an error adding your medication.', 'error')
            return redirect(url_for('add_medication'))

    return render_template('add.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_medication(id):
    medication = Medication.query.get_or_404(id)
    
    if request.method == 'POST':
        medication.name = request.form['name']
        medication.dosage = request.form['dosage']
        medication.frequency = request.form['frequency']
        medication.time = request.form['time']
        medication.notes = request.form['notes']

        try:
            db.session.commit()
            flash('Medication updated successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f'Error updating medication: {str(e)}')
            flash('There was an error updating your medication.', 'error')
            return redirect(url_for('edit_medication', id=id))

    return render_template('edit.html', medication=medication)

@app.route('/delete/<int:id>')
def delete_medication(id):
    medication = Medication.query.get_or_404(id)
    
    try:
        db.session.delete(medication)
        db.session.commit()
        flash('Medication deleted successfully!', 'success')
    except Exception as e:
        logger.error(f'Error deleting medication: {str(e)}')
        flash('There was an error deleting your medication.', 'error')
    
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    try:
        profile = UserProfile.query.first()
        if profile is None:
            profile = UserProfile(
                name="Default User",
                date_of_birth=datetime.now(local_timezone),
                weight=0,
                height=0
            )
            db.session.add(profile)
            db.session.commit()

        if request.method == 'POST':
            try:
                profile.name = request.form['name']
                
                # Handle date of birth with proper error handling
                date_str = request.form['date_of_birth']
                if date_str:
                    try:
                        profile.date_of_birth = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=local_timezone)
                    except ValueError as e:
                        logger.error(f'Invalid date format: {str(e)}')
                        flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
                        return render_template('profile.html', profile=profile)
                
                # Handle weight with proper error handling
                weight = request.form['weight']
                if weight.strip():
                    try:
                        profile.weight = float(weight)
                    except ValueError:
                        flash('Invalid weight value. Please enter a number.', 'error')
                        return render_template('profile.html', profile=profile)
                else:
                    profile.weight = None
                
                # Handle height with proper error handling
                height = request.form['height']
                if height.strip():
                    try:
                        profile.height = float(height)
                    except ValueError:
                        flash('Invalid height value. Please enter a number.', 'error')
                        return render_template('profile.html', profile=profile)
                else:
                    profile.height = None
                
                # Handle other fields
                profile.gender = request.form.get('gender', '')
                profile.blood_type = request.form.get('blood_type', '')
                profile.allergies = request.form.get('allergies', '')
                profile.medical_conditions = request.form.get('medical_conditions', '')

                db.session.commit()
                flash('Profile updated successfully!', 'success')
                
            except Exception as e:
                logger.error(f'Error updating profile: {str(e)}')
                db.session.rollback()
                flash('Error updating profile. Please try again.', 'error')
                
        return render_template('profile.html', profile=profile)
        
    except Exception as e:
        logger.error(f'Error in profile route: {str(e)}')
        flash('An unexpected error occurred. Please try again.', 'error')
        return render_template('error.html'), 500

@app.route('/emergency-contacts', methods=['GET'])
def emergency_contacts():
    contacts = EmergencyContact.query.order_by(EmergencyContact.created_at.desc()).all()
    return render_template('emergency_contacts.html', contacts=contacts)

@app.route('/emergency-contacts/add', methods=['GET', 'POST'])
def add_emergency_contact():
    if request.method == 'POST':
        new_contact = EmergencyContact(
            name=request.form['name'],
            relationship=request.form['relationship'],
            phone_primary=request.form['phone_primary'],
            phone_secondary=request.form['phone_secondary'],
            email=request.form['email'],
            address=request.form['address'],
            notes=request.form['notes']
        )
        
        try:
            db.session.add(new_contact)
            db.session.commit()
            flash('Emergency contact added successfully!', 'success')
            return redirect(url_for('emergency_contacts'))
        except Exception as e:
            logger.error(f'Error adding emergency contact: {str(e)}')
            db.session.rollback()
            flash('Error adding emergency contact.', 'error')
    
    return render_template('add_emergency_contact.html')

@app.route('/emergency-contacts/edit/<int:id>', methods=['GET', 'POST'])
def edit_emergency_contact(id):
    contact = EmergencyContact.query.get_or_404(id)
    
    if request.method == 'POST':
        contact.name = request.form['name']
        contact.relationship = request.form['relationship']
        contact.phone_primary = request.form['phone_primary']
        contact.phone_secondary = request.form['phone_secondary']
        contact.email = request.form['email']
        contact.address = request.form['address']
        contact.notes = request.form['notes']
        
        try:
            db.session.commit()
            flash('Emergency contact updated successfully!', 'success')
            return redirect(url_for('emergency_contacts'))
        except Exception as e:
            logger.error(f'Error updating emergency contact: {str(e)}')
            db.session.rollback()
            flash('Error updating emergency contact.', 'error')
    
    return render_template('edit_emergency_contact.html', contact=contact)

@app.route('/emergency-contacts/delete/<int:id>')
def delete_emergency_contact(id):
    contact = EmergencyContact.query.get_or_404(id)
    
    try:
        db.session.delete(contact)
        db.session.commit()
        flash('Emergency contact deleted successfully!', 'success')
    except Exception as e:
        logger.error(f'Error deleting emergency contact: {str(e)}')
        db.session.rollback()
        flash('Error deleting emergency contact.', 'error')
    
    return redirect(url_for('emergency_contacts'))

@app.route('/blood-pressure', methods=['GET'])
def blood_pressure():
    try:
        blood_pressure_list = BloodPressure.query.order_by(BloodPressure.date_time.desc()).all()
        return render_template('blood_pressure.html', blood_pressure=blood_pressure_list)
    except Exception as e:
        logger.error(f"Error fetching blood pressure: {str(e)}")
        flash('Error loading blood pressure', 'error')
        return render_template('blood_pressure.html', blood_pressure=[])

@app.route('/blood-pressure/add', methods=['GET', 'POST'])
def add_blood_pressure():
    if request.method == 'POST':
        new_blood_pressure = BloodPressure(
            systolic=request.form.get('systolic', type=int),
            diastolic=request.form.get('diastolic', type=int),
            pulse=request.form.get('pulse', type=int),
            notes=request.form.get('notes')
        )
        
        try:
            db.session.add(new_blood_pressure)
            db.session.commit()
            flash('Blood pressure recorded successfully!', 'success')
            return redirect(url_for('blood_pressure'))
        except Exception as e:
            logger.error(f'Error recording blood pressure: {str(e)}')
            db.session.rollback()
            flash('Error recording blood pressure.', 'error')
    
    return render_template('add_blood_pressure.html', now=datetime.now(local_timezone))

@app.route('/edit_blood_pressure/<int:id>', methods=['GET', 'POST'])
def edit_blood_pressure(id):
    try:
        blood_pressure = BloodPressure.query.get_or_404(id)
        
        if request.method == 'POST':
            blood_pressure.systolic = request.form.get('systolic', type=int)
            blood_pressure.diastolic = request.form.get('diastolic', type=int)
            blood_pressure.pulse = request.form.get('pulse', type=int)
            blood_pressure.notes = request.form.get('notes')
            
            try:
                db.session.commit()
                flash('Blood pressure updated successfully!', 'success')
                return redirect(url_for('blood_pressure'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating blood pressure: {str(e)}")
                flash('Error updating blood pressure', 'error')
                
        return render_template('edit_blood_pressure.html', blood_pressure=blood_pressure)
        
    except Exception as e:
        logger.error(f"Error in edit_blood_pressure: {str(e)}")
        flash('Error accessing blood pressure', 'error')
        return redirect(url_for('blood_pressure'))

@app.route('/delete_blood_pressure/<int:id>')
def delete_blood_pressure(id):
    try:
        blood_pressure = BloodPressure.query.get_or_404(id)
        db.session.delete(blood_pressure)
        db.session.commit()
        flash('Blood pressure deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting blood pressure: {str(e)}")
        flash('Error deleting blood pressure', 'error')
    
    return redirect(url_for('blood_pressure'))

@app.route('/blood-tests', methods=['GET'])
def blood_tests():
    try:
        blood_tests_list = BloodTests.query.order_by(BloodTests.date_time.desc()).all()
        return render_template('blood_tests.html', blood_tests=blood_tests_list)
    except Exception as e:
        logger.error(f"Error fetching blood tests: {str(e)}")
        flash('Error loading blood tests', 'error')
        return render_template('blood_tests.html', blood_tests=[])

@app.route('/blood-tests/add', methods=['GET', 'POST'])
def add_blood_tests():
    if request.method == 'POST':
        new_blood_test = BloodTests(
            blood_sugar=request.form.get('blood_sugar', type=float),
            oxygen_saturation=request.form.get('oxygen_saturation', type=int),
            notes=request.form.get('notes')
        )
        
        try:
            db.session.add(new_blood_test)
            db.session.commit()
            flash('Blood test recorded successfully!', 'success')
            return redirect(url_for('blood_tests'))
        except Exception as e:
            logger.error(f'Error recording blood test: {str(e)}')
            db.session.rollback()
            flash('Error recording blood test.', 'error')
    
    return render_template('add_blood_tests.html', now=datetime.now(local_timezone))

@app.route('/edit_blood_tests/<int:id>', methods=['GET', 'POST'])
def edit_blood_tests(id):
    try:
        blood_test = BloodTests.query.get_or_404(id)
        
        if request.method == 'POST':
            blood_test.blood_sugar = request.form.get('blood_sugar', type=float)
            blood_test.oxygen_saturation = request.form.get('oxygen_saturation', type=int)
            blood_test.notes = request.form.get('notes')
            
            try:
                db.session.commit()
                flash('Blood test updated successfully!', 'success')
                return redirect(url_for('blood_tests'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating blood test: {str(e)}")
                flash('Error updating blood test', 'error')
                
        return render_template('edit_blood_tests.html', blood_test=blood_test)
        
    except Exception as e:
        logger.error(f"Error in edit_blood_tests: {str(e)}")
        flash('Error accessing blood test', 'error')
        return redirect(url_for('blood_tests'))

@app.route('/delete_blood_tests/<int:id>')
def delete_blood_tests(id):
    try:
        blood_test = BloodTests.query.get_or_404(id)
        db.session.delete(blood_test)
        db.session.commit()
        flash('Blood test deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting blood test: {str(e)}")
        flash('Error deleting blood test', 'error')
    
    return redirect(url_for('blood_tests'))

@app.route('/reminders')
def reminders():
    medications = Medication.query.all()
    return render_template('reminders.html', medications=medications)

@app.route('/api/medication/<int:id>/reminders', methods=['GET'])
def get_medication_reminders(id):
    medication = Medication.query.get_or_404(id)
    return {
        'reminder_enabled': medication.reminder_enabled,
        'reminder_times': medication.reminder_times or ''
    }

@app.route('/api/medication/<int:id>/reminders', methods=['POST'])
def update_medication_reminders(id):
    medication = Medication.query.get_or_404(id)
    data = request.get_json()
    
    medication.reminder_enabled = data.get('reminder_enabled', False)
    medication.reminder_times = data.get('reminder_times', '')
    
    try:
        db.session.commit()
        return {'status': 'success'}
    except Exception as e:
        logger.error(f'Error updating reminders: {str(e)}')
        return {'status': 'error'}, 500

@app.route('/api/check_reminders')
def check_reminders():
    current_time = datetime.now(local_timezone)
    current_time_str = current_time.strftime('%H:%M')
    
    # Find medications with reminders at the current time
    medications = Medication.query.filter_by(reminder_enabled=True).all()
    due_medications = []
    
    for med in medications:
        if not med.reminder_times:
            continue
            
        reminder_times = med.reminder_times.split(',')
        if current_time_str in reminder_times:
            # Check if we haven't already reminded for this medication recently
            if not med.last_reminded or (current_time - med.last_reminded).total_seconds() > 300:  # 5 minutes
                due_medications.append({
                    'name': med.name,
                    'dosage': med.dosage,
                    'notes': med.notes
                })
                med.last_reminded = current_time
    
    if due_medications:
        db.session.commit()
    
    return jsonify(due_medications)

@app.route('/reset_data', methods=['POST'])
def reset_data():
    try:
        # Drop all tables
        db.drop_all()
        # Recreate all tables
        db.create_all()
        flash('All data has been reset successfully!', 'success')
    except Exception as e:
        logger.error(f"Error resetting data: {str(e)}")
        flash('Error resetting data', 'error')
    
    return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'toggle_theme':
            # Toggle theme in session
            current_theme = session.get('theme', 'light')
            session['theme'] = 'dark' if current_theme == 'light' else 'light'
            return jsonify({'theme': session['theme']})
            
        elif action == 'reset_data':
            try:
                # Drop all tables
                db.drop_all()
                # Recreate all tables
                db.create_all()
                flash('All data has been reset successfully!', 'success')
            except Exception as e:
                logger.error(f"Error resetting data: {str(e)}")
                flash('Error resetting data', 'error')
                
            return redirect(url_for('settings'))
    
    # Get current theme
    theme = session.get('theme', 'light')
    return render_template('settings.html', theme=theme)

@app.context_processor
def inject_theme():
    """Make theme available to all templates"""
    return {'theme': session.get('theme', 'light')}

if __name__ == '__main__':
    app.run(debug=True)
else:
    # Initialize database when running under Gunicorn, but NEVER add sample data
    init_db(add_sample_data=False)
