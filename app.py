from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
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

@app.template_filter('format_age')
def format_age(dob):
    if not dob:
        return ""
    today = datetime.now()
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
    if os.environ.get('DATABASE_URL'):
        # Handle Render's database URL format
        database_url = os.environ.get('DATABASE_URL')
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
        # Set up basic configuration with PostgreSQL 16 specific settings
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_size': 1,
            'max_overflow': 0,
            'connect_args': {
                'connect_timeout': 10,
                'options': '-c timezone=UTC -c client_encoding=UTF8 -c jit=off'
            }
        }
        
        # Import and configure psycopg2 directly
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, parse_dsn
        
        # Parse the URL to get connection parameters
        dsn = parse_dsn(database_url)
        
        # Test direct connection first with PostgreSQL 16 specific settings
        try:
            logger.info("Testing direct psycopg2 connection...")
            conn = psycopg2.connect(
                **dsn,
                sslmode='require',
                connect_timeout=10,
                options="-c timezone=UTC -c client_encoding=UTF8 -c jit=off"
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            # Test connection and get PostgreSQL version
            cur = conn.cursor()
            cur.execute('SHOW server_version')
            version = cur.fetchone()[0]
            logger.info(f"Connected to PostgreSQL version: {version}")
            
            cur.close()
            conn.close()
            logger.info("Direct connection test successful")
        except Exception as e:
            logger.error(f"Direct connection test failed: {str(e)}")
            raise
            
        logger.info('Using PostgreSQL 16 database on Render')
    else:
        # Local SQLite database - store in a persistent location
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'medications.db')
        # Create the data directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        logger.info(f'Using SQLite database at {db_path} (local development)')

    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    
    # Test database connection once
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            logger.info("Database tables created successfully")

            # Test connection with version check
            if 'postgresql' in str(db.engine.url):
                result = db.session.execute(db.text('SHOW server_version')).scalar()
                logger.info(f'Connected to PostgreSQL version: {result}')
            db.session.commit()
            logger.info('Database connection successful')
    except Exception as e:
        logger.error(f'Database connection test failed: {str(e)}')
        raise

except Exception as e:
    logger.error(f'Fatal database initialization error: {str(e)}')
    raise

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.DateTime)
    gender = db.Column(db.String(20))
    height = db.Column(db.Float)  # in cm
    weight = db.Column(db.Float)  # in kg
    blood_type = db.Column(db.String(10))
    allergies = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(100))
    time = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reminder_enabled = db.Column(db.Boolean, default=False)
    reminder_times = db.Column(db.String(500))  # Store times as JSON string
    last_reminded = db.Column(db.DateTime)

class VitalSigns(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    systolic_bp = db.Column(db.Integer)  # mmHg
    diastolic_bp = db.Column(db.Integer)  # mmHg
    heart_rate = db.Column(db.Integer)  # bpm
    temperature = db.Column(db.Float)  # Celsius
    respiratory_rate = db.Column(db.Integer)  # breaths per minute
    oxygen_saturation = db.Column(db.Integer)  # percentage
    blood_sugar = db.Column(db.Float)  # mg/dL
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db(add_sample_data=False):
    """Initialize the database and optionally add sample data."""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            logger.info("Database tables created successfully")

            if add_sample_data:
                # Only add sample data if explicitly requested
                # Check if we already have a profile
                if not UserProfile.query.first():
                    # Add a sample profile
                    sample_profile = UserProfile(
                        name="John Doe",
                        date_of_birth=datetime(1980, 1, 1),
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

                # Add sample vital signs if none exist
                if not VitalSigns.query.first():
                    sample_vitals = VitalSigns(
                        systolic_bp=120,
                        diastolic_bp=80,
                        heart_rate=72,
                        temperature=36.6,
                        respiratory_rate=16,
                        oxygen_saturation=98,
                        blood_sugar=100,
                        notes="Regular checkup"
                    )
                    db.session.add(sample_vitals)

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
        current_time = datetime.now()
        
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
        
        # Get latest vital signs with error handling
        try:
            latest_vitals = VitalSigns.query.order_by(VitalSigns.date_time.desc()).first()
        except Exception as e:
            logger.error(f"Error fetching vital signs: {str(e)}")
            latest_vitals = None
        
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
                             latest_vitals=latest_vitals,
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
                date_of_birth=datetime.now(),
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
                        profile.date_of_birth = datetime.strptime(date_str, '%Y-%m-%d')
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

@app.route('/vitals', methods=['GET'])
def vitals():
    try:
        vitals_list = VitalSigns.query.order_by(VitalSigns.date_time.desc()).all()
        return render_template('vitals.html', vitals=vitals_list)
    except Exception as e:
        logger.error(f"Error fetching vital signs: {str(e)}")
        flash('Error loading vital signs', 'error')
        return render_template('vitals.html', vitals=[])

@app.route('/vitals/add', methods=['GET', 'POST'])
def add_vitals():
    if request.method == 'POST':
        new_vitals = VitalSigns(
            date_time=datetime.strptime(request.form['date_time'], '%Y-%m-%dT%H:%M'),
            systolic_bp=request.form.get('systolic_bp', type=int),
            diastolic_bp=request.form.get('diastolic_bp', type=int),
            heart_rate=request.form.get('heart_rate', type=int),
            temperature=request.form.get('temperature', type=float),
            respiratory_rate=request.form.get('respiratory_rate', type=int),
            oxygen_saturation=request.form.get('oxygen_saturation', type=int),
            blood_sugar=request.form.get('blood_sugar', type=float),
            notes=request.form.get('notes')
        )
        
        try:
            db.session.add(new_vitals)
            db.session.commit()
            flash('Vital signs recorded successfully!', 'success')
            return redirect(url_for('vitals'))
        except Exception as e:
            logger.error(f'Error recording vital signs: {str(e)}')
            db.session.rollback()
            flash('Error recording vital signs.', 'error')
    
    return render_template('add_vitals.html', now=datetime.now())

@app.route('/edit_vitals/<int:id>', methods=['GET', 'POST'])
def edit_vitals(id):
    try:
        vital = VitalSigns.query.get_or_404(id)
        
        if request.method == 'POST':
            vital.systolic_bp = request.form.get('systolic_bp', type=int)
            vital.diastolic_bp = request.form.get('diastolic_bp', type=int)
            vital.heart_rate = request.form.get('heart_rate', type=int)
            vital.temperature = request.form.get('temperature', type=float)
            vital.respiratory_rate = request.form.get('respiratory_rate', type=int)
            vital.oxygen_saturation = request.form.get('oxygen_saturation', type=int)
            vital.blood_sugar = request.form.get('blood_sugar', type=float)
            vital.notes = request.form.get('notes')
            
            try:
                db.session.commit()
                flash('Vital signs updated successfully!', 'success')
                return redirect(url_for('vitals'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating vital signs: {str(e)}")
                flash('Error updating vital signs', 'error')
                
        return render_template('edit_vitals.html', vital=vital)
        
    except Exception as e:
        logger.error(f"Error in edit_vitals: {str(e)}")
        flash('Error accessing vital signs', 'error')
        return redirect(url_for('vitals'))

@app.route('/delete_vitals/<int:id>')
def delete_vitals(id):
    try:
        vital = VitalSigns.query.get_or_404(id)
        db.session.delete(vital)
        db.session.commit()
        flash('Vital signs deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting vital signs: {str(e)}")
        flash('Error deleting vital signs', 'error')
    
    return redirect(url_for('vitals'))

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
    current_time = datetime.now()
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
