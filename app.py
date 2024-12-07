from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import sys
import logging

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
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        logger.info('Using PostgreSQL database on Render')
        
        # Configure PostgreSQL connection pool for web deployment
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 5,  # Maximum number of permanent connections
            'max_overflow': 2,  # Maximum number of temporary connections
            'pool_timeout': 30,  # Seconds to wait before giving up on getting a connection
            'pool_recycle': 1800,  # Recycle connections after 30 minutes
        }
        logger.info('Configured PostgreSQL connection pool')
    else:
        # Local SQLite database - store in a persistent location
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'medications.db')
        # Create the data directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        logger.info(f'Using SQLite database at {db_path} (local development)')

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    logger.info('SQLAlchemy initialized successfully')
    
    # Test database connection
    with app.app_context():
        db.engine.connect()
        logger.info('Successfully connected to the database')
except Exception as e:
    logger.error(f'Error initializing database: {str(e)}')
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
            # Check if database file exists and has data
            if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
                logger.info("Database file exists and has data, skipping initialization")
                return
            
            # Only create tables if they don't exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            if not tables:
                # Create tables only if database is empty
                db.create_all()
                logger.info("Database tables created successfully")
            else:
                logger.info("Database tables already exist, skipping creation")
            
            # Check if we need to add new columns to the Medication table
            if 'medication' in tables:
                existing_columns = [c['name'] for c in inspector.get_columns('medication')]
                
                if 'reminder_enabled' not in existing_columns:
                    logger.info("Adding reminder columns to Medication table")
                    # Use PostgreSQL-specific syntax when using PostgreSQL
                    if 'postgresql' in str(db.engine.url):
                        with db.engine.connect() as conn:
                            conn.execute(db.text(
                                """
                                ALTER TABLE medication 
                                ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT FALSE,
                                ADD COLUMN IF NOT EXISTS reminder_times VARCHAR(500),
                                ADD COLUMN IF NOT EXISTS last_reminded TIMESTAMP;
                                """
                            ))
                            conn.commit()
                    else:
                        # SQLite syntax for local development
                        with db.engine.connect() as conn:
                            try:
                                conn.execute(db.text("ALTER TABLE medication ADD COLUMN reminder_enabled BOOLEAN DEFAULT FALSE;"))
                                conn.execute(db.text("ALTER TABLE medication ADD COLUMN reminder_times VARCHAR(500);"))
                                conn.execute(db.text("ALTER TABLE medication ADD COLUMN last_reminded DATETIME;"))
                                conn.commit()
                            except Exception as e:
                                logger.warning(f"Column might already exist: {str(e)}")
                                conn.rollback()
                    
                    logger.info("Successfully added reminder columns")

        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            db.session.rollback()
            raise

# Initialize database when the app starts, but NEVER add sample data
init_db(add_sample_data=False)

@app.route('/')
def index():
    # Get the current user's profile
    profile = UserProfile.query.first()
    
    # Get latest vital signs
    latest_vitals = VitalSigns.query.order_by(VitalSigns.date_time.desc()).first()
    
    # Get medications for today
    medications = Medication.query.all()
    
    # Process medication times
    current_time = datetime.now()
    for med in medications:
        if med.reminder_times:
            # If reminder_times exists, use the first time
            med.time = med.reminder_times.split(',')[0].strip()
        else:
            # Default to morning if no specific time is set
            med.time = "08:00"
    
    return render_template('index.html',
                         profile=profile,
                         latest_vitals=latest_vitals,
                         medications=medications)

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
        profile.name = request.form['name']
        profile.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d')
        
        # Handle weight - convert empty string to None
        weight = request.form['weight']
        profile.weight = float(weight) if weight.strip() else None
        
        # Handle height - convert empty string to None
        height = request.form['height']
        profile.height = float(height) if height.strip() else None
        
        profile.gender = request.form['gender']
        profile.blood_type = request.form['blood_type']
        profile.allergies = request.form['allergies']
        profile.medical_conditions = request.form['medical_conditions']

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            logger.error(f'Error updating profile: {str(e)}')
            db.session.rollback()
            flash('Error updating profile.', 'error')

    return render_template('profile.html', profile=profile)

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
