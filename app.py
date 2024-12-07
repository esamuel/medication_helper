from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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

# Initialize database when the app starts, but NEVER add sample data
init_db(add_sample_data=False)

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
    blood_sugar = db.Column(db.Float)  # mmol/L
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
    with app.app_context():
        try:
            # Test database connection first
            db.session.execute(db.text('SELECT 1'))
            db.session.commit()
            logger.info('Database connection verified')

            # Get list of existing tables
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            # Create tables if they don't exist
            if not tables:
                db.create_all()
                logger.info("Database tables created successfully")
            else:
                logger.info("Database tables already exist")

            # Ensure we have at least one user profile
            profile = UserProfile.query.first()
            if not profile:
                logger.info("Creating default user profile")
                profile = UserProfile(
                    name="Default User",
                    date_of_birth=datetime.now(),
                    weight=0,
                    height=0
                )
                db.session.add(profile)
                db.session.commit()
                logger.info("Default user profile created")

            # Check and update table schemas if needed
            if 'medication' in tables:
                existing_columns = {c['name'] for c in inspector.get_columns('medication')}
                required_columns = {
                    'reminder_enabled',
                    'reminder_times',
                    'last_reminded'
                }
                
                missing_columns = required_columns - existing_columns
                
                if missing_columns:
                    logger.info(f"Adding missing columns to Medication table: {missing_columns}")
                    
                    # Use appropriate SQL syntax based on database type
                    is_postgres = 'postgresql' in str(db.engine.url)
                    
                    for column in missing_columns:
                        try:
                            if is_postgres:
                                if column == 'reminder_enabled':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT FALSE"
                                    ))
                                elif column == 'reminder_times':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN IF NOT EXISTS reminder_times VARCHAR(500)"
                                    ))
                                elif column == 'last_reminded':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN IF NOT EXISTS last_reminded TIMESTAMP"
                                    ))
                            else:  # SQLite
                                if column == 'reminder_enabled':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN reminder_enabled BOOLEAN DEFAULT 0"
                                    ))
                                elif column == 'reminder_times':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN reminder_times VARCHAR(500)"
                                    ))
                                elif column == 'last_reminded':
                                    db.session.execute(db.text(
                                        "ALTER TABLE medication ADD COLUMN last_reminded TIMESTAMP"
                                    ))
                            db.session.commit()
                            logger.info(f"Successfully added column: {column}")
                        except Exception as e:
                            logger.error(f"Error adding column {column}: {str(e)}")
                            db.session.rollback()
                            # Continue with other columns even if one fails
                            continue

            if add_sample_data and not Medication.query.first():
                logger.info("No medications found, adding sample data is enabled but skipped for safety")
                
            db.session.commit()
            logger.info("Database initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Error in init_db: {str(e)}")
            db.session.rollback()
            raise

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
    vitals = VitalSigns.query.order_by(VitalSigns.date_time.desc()).all()
    print("Number of vital signs:", len(vitals))
    if len(vitals) > 0:
        print("First vital sign:", vitals[0].systolic_bp, "/", vitals[0].diastolic_bp)
    return render_template('vitals.html', vitals=vitals)

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
        # Delete all records from each table
        EmergencyContact.query.delete()
        VitalSigns.query.delete()
        Medication.query.delete()
        UserProfile.query.delete()
        
        # Commit the changes
        db.session.commit()
        flash('All data has been successfully reset!', 'success')
    except Exception as e:
        logger.error(f"Error resetting data: {str(e)}")
        db.session.rollback()
        flash('There was an error resetting the data.', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
else:
    # Initialize database when running under Gunicorn, but NEVER add sample data
    init_db(add_sample_data=False)
