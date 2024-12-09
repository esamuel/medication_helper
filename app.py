from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Blueprint
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import zoneinfo
import os
from dotenv import load_dotenv
import sys
import logging
import time
from flask_wtf.csrf import CSRFProtect

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info('Starting up the Flask application...')

# Initialize Flask app
app = Flask(__name__)

# Create blueprints
bp = Blueprint('blood_pressure', __name__, url_prefix='/blood-pressure')
bt = Blueprint('blood_tests', __name__, url_prefix='/blood-tests')
medication_bp = Blueprint('medication', __name__, url_prefix='/medication')
emergency_contacts_bp = Blueprint('emergency_contacts', __name__, url_prefix='/emergency-contacts')
vitals_bp = Blueprint('vitals', __name__, url_prefix='/vitals')

# Blood Pressure routes
@bp.route('/', methods=['GET'])
def blood_pressure_index():
    try:
        blood_pressure_list = BloodPressure.query.order_by(BloodPressure.date_time.desc()).all()
        return render_template('blood_pressure.html', blood_pressure=blood_pressure_list)
    except Exception as e:
        logger.error(f"Error fetching blood pressure: {str(e)}")
        flash('Error loading blood pressure', 'error')
        return render_template('blood_pressure.html', blood_pressure=[])

@bp.route('/add', methods=['GET', 'POST'])
def add_blood_pressure():
    if request.method == 'POST':
        try:
            new_blood_pressure = BloodPressure(
                systolic=request.form.get('systolic', type=int),
                diastolic=request.form.get('diastolic', type=int),
                pulse=request.form.get('pulse', type=int),
                notes=request.form.get('notes')
            )
            db.session.add(new_blood_pressure)
            db.session.commit()
            flash('Blood pressure record added successfully!', 'success')
            return redirect(url_for('blood_pressure.blood_pressure_index'))
        except Exception as e:
            logger.error(f"Error adding blood pressure: {str(e)}")
            db.session.rollback()
            flash('Error adding blood pressure record', 'error')
    return render_template('add_blood_pressure.html')

# Blood Tests routes
@bt.route('/', methods=['GET'])
def blood_tests_index():
    try:
        blood_tests_list = BloodTests.query.order_by(BloodTests.date_time.desc()).all()
        return render_template('blood_tests.html', blood_tests=blood_tests_list)
    except Exception as e:
        logger.error(f"Error fetching blood tests: {str(e)}")
        flash('Error loading blood tests', 'error')
        return render_template('blood_tests.html', blood_tests=[])

@bt.route('/add', methods=['GET', 'POST'])
def add_blood_test():
    if request.method == 'POST':
        try:
            new_blood_test = BloodTests(
                blood_sugar=request.form.get('blood_sugar', type=float),
                oxygen_saturation=request.form.get('oxygen_saturation', type=int),
                notes=request.form.get('notes')
            )
            db.session.add(new_blood_test)
            db.session.commit()
            flash('Blood test record added successfully!', 'success')
            return redirect(url_for('blood_tests.blood_tests_index'))
        except Exception as e:
            logger.error(f"Error adding blood test: {str(e)}")
            db.session.rollback()
            flash('Error adding blood test record', 'error')
    return render_template('add_blood_tests.html')

# Medication routes
@medication_bp.route('/', methods=['GET'])
def medication_index():
    try:
        medications_list = Medication.query.all()
        return render_template('medications.html', medications=medications_list)
    except Exception as e:
        logger.error(f"Error fetching medications: {str(e)}")
        flash('Error loading medications', 'error')
        return render_template('medications.html', medications=[])

# Vitals routes
@vitals_bp.route('/')
def vitals():
    return render_template('vitals.html')

@vitals_bp.route('/add', methods=['GET', 'POST'])
def add_vitals():
    if request.method == 'POST':
        # Add vitals logic here
        return redirect(url_for('vitals.vitals'))
    return render_template('add_vitals.html')

@vitals_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_vitals(id):
    if request.method == 'POST':
        # Edit vitals logic here
        return redirect(url_for('vitals.vitals'))
    return render_template('edit_vitals.html')

@vitals_bp.route('/delete/<int:id>')
def delete_vitals(id):
    # Delete vitals logic here
    return redirect(url_for('vitals.vitals'))

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Register all blueprints after defining their routes
app.register_blueprint(bp)
app.register_blueprint(bt)
app.register_blueprint(medication_bp)
app.register_blueprint(emergency_contacts_bp)
app.register_blueprint(vitals_bp)

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
    # Check for DATABASE_URL environment variable (used by Render.com)
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        # Replace postgres:// with postgresql:// for SQLAlchemy
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Use SQLite for local development
        database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'medication_helper.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    logger.info('Successfully configured database')
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
with app.app_context():
    db.create_all()
    logger.info("Database tables created successfully")
    convert_blood_sugar()

# Emergency Contacts routes
@emergency_contacts_bp.route('/', methods=['GET'])
def index():
    contacts = EmergencyContact.query.order_by(EmergencyContact.created_at.desc()).all()
    return render_template('emergency_contacts.html', contacts=contacts)

@emergency_contacts_bp.route('/add', methods=['GET', 'POST'])
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
            return redirect(url_for('emergency_contacts.index'))
        except Exception as e:
            logger.error(f'Error adding emergency contact: {str(e)}')
            db.session.rollback()
            flash('Error adding emergency contact.', 'error')
    
    return render_template('add_emergency_contact.html')

@emergency_contacts_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
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
            return redirect(url_for('emergency_contacts.index'))
        except Exception as e:
            logger.error(f'Error updating emergency contact: {str(e)}')
            db.session.rollback()
            flash('Error updating emergency contact.', 'error')
    
    return render_template('edit_emergency_contact.html', contact=contact)

@emergency_contacts_bp.route('/delete/<int:id>')
def delete_emergency_contact(id):
    contact = EmergencyContact.query.get_or_404(id)
    
    try:
        db.session.delete(contact)
        db.session.commit()
        flash('Emergency contact deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deleting emergency contact: {str(e)}')
        flash('Error deleting emergency contact.', 'error')
    
    return redirect(url_for('emergency_contacts.index'))

# Root route
@app.route('/')
def root():
    return redirect(url_for('medication.index'))

# Reset data route
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

# Context processor for theme
@app.context_processor
def inject_theme():
    """Make theme available to all templates"""
    return {'theme': session.get('theme', 'light')}

if __name__ == '__main__':
    # Get port from environment variable (Render sets this) or use 5001 as default
    port = int(os.environ.get('PORT', 5001))
    # When running on Render, we need to listen on 0.0.0.0
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # Initialize database when running under Gunicorn, but NEVER add sample data
    init_db(add_sample_data=False)
