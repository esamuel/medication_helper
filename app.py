from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from dotenv import load_dotenv
import sys
import logging

# Load environment variables from .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Flask(__name__)
app.logger.info('Starting up the Flask application...')

# Use environment variables for configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.error('No SECRET_KEY set in environment variables!')
    raise ValueError('No SECRET_KEY set in environment variables!')

# Set the environment
FLASK_ENV = os.environ.get('FLASK_ENV', 'production')
app.config['DEBUG'] = FLASK_ENV == 'development'

app.logger.info(f'Running in {FLASK_ENV} environment')

# Database configuration - use PostgreSQL in production, SQLite in development
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('postgres://'):
        # Heroku/Render provides DATABASE_URL starting with 'postgres://' but SQLAlchemy needs 'postgresql://'
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.logger.info('Using PostgreSQL database')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medications.db'
    app.logger.info('Using SQLite database')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

try:
    db = SQLAlchemy(app)
    app.logger.info('SQLAlchemy initialized successfully')
except Exception as e:
    app.logger.error(f'Error initializing SQLAlchemy: {str(e)}')
    raise

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=False)
    frequency = db.Column(db.String(100), nullable=False)
    time = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reminder_enabled = db.Column(db.Boolean, default=False)
    reminder_times = db.Column(db.String(500))  # Store times as JSON string
    last_reminded = db.Column(db.DateTime)

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.DateTime)
    gender = db.Column(db.String(20))
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    blood_type = db.Column(db.String(10))
    allergies = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

class VitalSigns(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    systolic_bp = db.Column(db.Integer)  # Systolic blood pressure
    diastolic_bp = db.Column(db.Integer)  # Diastolic blood pressure
    heart_rate = db.Column(db.Integer)    # Heart rate (bpm)
    temperature = db.Column(db.Float)      # Body temperature (°C)
    respiratory_rate = db.Column(db.Integer)  # Breaths per minute
    oxygen_saturation = db.Column(db.Integer) # SpO2 (%)
    blood_sugar = db.Column(db.Float)      # Blood glucose level
    notes = db.Column(db.Text)            # Any additional notes

@app.route('/')
def index():
    # Get user profile
    profile = UserProfile.query.first()
    
    # Calculate age if DOB exists
    age = None
    if profile and profile.date_of_birth:
        today = datetime.now()
        age = today.year - profile.date_of_birth.year - ((today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day))
    
    # Get today's medications
    today = datetime.now().date()
    medications = Medication.query.all()
    
    # Get latest vital signs
    latest_vitals = VitalSigns.query.order_by(VitalSigns.date_time.desc()).first()
    
    return render_template('index.html', 
                         profile=profile,
                         age=age,
                         medications=medications,
                         latest_vitals=latest_vitals,
                         current_time=datetime.now().time())

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
            app.logger.error(f'Error adding medication: {str(e)}')
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
            app.logger.error(f'Error updating medication: {str(e)}')
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
        app.logger.error(f'Error deleting medication: {str(e)}')
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
        profile.weight = float(request.form['weight'])
        profile.height = float(request.form['height'])
        profile.gender = request.form['gender']
        profile.blood_type = request.form['blood_type']
        profile.allergies = request.form['allergies']
        profile.medical_conditions = request.form['medical_conditions']

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            app.logger.error(f'Error updating profile: {str(e)}')
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
            app.logger.error(f'Error adding emergency contact: {str(e)}')
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
            app.logger.error(f'Error updating emergency contact: {str(e)}')
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
        app.logger.error(f'Error deleting emergency contact: {str(e)}')
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
            app.logger.error(f'Error recording vital signs: {str(e)}')
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
        app.logger.error(f'Error updating reminders: {str(e)}')
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

# Create tables and initialize database
def init_db():
    with app.app_context():
        try:
            # Create any missing tables first
            db.create_all()
            app.logger.info("Database tables verified/created successfully")
            
            # Check if we need to add new columns to the Medication table
            inspector = db.inspect(db.engine)
            existing_columns = [c['name'] for c in inspector.get_columns('medication')]
            
            if 'reminder_enabled' not in existing_columns:
                app.logger.info("Adding reminder columns to Medication table")
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
                            app.logger.warning(f"Column might already exist: {str(e)}")
                            conn.rollback()
                
                app.logger.info("Successfully added reminder columns")
            
            # Check if we need to create a default user profile
            if not UserProfile.query.first():
                default_profile = UserProfile(
                    name="Default User",
                    date_of_birth=datetime.now(),
                    weight=0,
                    height=0,
                    blood_type="",
                    allergies="",
                    medical_conditions=""
                )
                db.session.add(default_profile)
                db.session.commit()
                app.logger.info("Created default user profile")
        except Exception as e:
            app.logger.error(f"Error initializing database: {str(e)}")
            raise

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
else:
    # Initialize database when running under Gunicorn
    init_db()
