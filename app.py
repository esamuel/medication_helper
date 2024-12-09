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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info('Starting up the Flask application...')

# Initialize Flask app
app = Flask(__name__)

# Create blueprints
medication_bp = Blueprint('medication', __name__, url_prefix='/medication')
emergency_contacts_bp = Blueprint('emergency_contacts', __name__, url_prefix='/emergency-contacts')
vitals_bp = Blueprint('vitals', __name__, url_prefix='/vitals')

# Root route
@app.route('/')
def root():
    try:
        return redirect(url_for('medication.index'))
    except Exception as e:
        logger.error(f"Error in root route: {str(e)}")
        return render_template('error.html', error=str(e)), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    logger.error(f"404 error: {error}")
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    return render_template('error.html', error="Internal server error"), 500

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Set timezone to local timezone (Israel)
local_timezone = zoneinfo.ZoneInfo("Asia/Jerusalem")

# Set secret key
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
        logger.info('Using PostgreSQL database')
    else:
        # Use SQLite for local development
        database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'medication_helper.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
        logger.info('Using SQLite database')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    logger.info('Successfully configured database')
except Exception as e:
    logger.error(f'Fatal database initialization error: {str(e)}')
    sys.exit(1)

# Models
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
    reminder_times = db.Column(db.String(500))
    last_reminded = db.Column(db.DateTime(timezone=True))

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

# Medication routes
@medication_bp.route('/', methods=['GET'])
def index():
    try:
        medications_list = Medication.query.all()
        return render_template('medications.html', medications=medications_list)
    except Exception as e:
        logger.error(f"Error fetching medications: {str(e)}")
        flash('Error loading medications', 'error')
        return render_template('error.html', error=str(e)), 500

@medication_bp.route('/add', methods=['GET', 'POST'])
def add_medication():
    if request.method == 'POST':
        try:
            new_medication = Medication(
                name=request.form['name'],
                dosage=request.form['dosage'],
                frequency=request.form['frequency'],
                time=request.form['time'],
                notes=request.form['notes'],
                reminder_enabled='reminder_enabled' in request.form,
                reminder_times=request.form.get('reminder_times', '')
            )
            db.session.add(new_medication)
            db.session.commit()
            flash('Medication added successfully!', 'success')
            return redirect(url_for('medication.index'))
        except Exception as e:
            logger.error(f'Error adding medication: {str(e)}')
            flash('Error adding medication', 'error')
            return render_template('error.html', error=str(e)), 500
    return render_template('add_medication.html')

# Emergency Contacts routes
@emergency_contacts_bp.route('/', methods=['GET'])
def index():
    try:
        contacts = EmergencyContact.query.all()
        return render_template('emergency_contacts.html', contacts=contacts)
    except Exception as e:
        logger.error(f"Error fetching contacts: {str(e)}")
        flash('Error loading contacts', 'error')
        return render_template('error.html', error=str(e)), 500

@emergency_contacts_bp.route('/add', methods=['GET', 'POST'])
def add_contact():
    if request.method == 'POST':
        try:
            new_contact = EmergencyContact(
                name=request.form['name'],
                relationship=request.form['relationship'],
                phone_primary=request.form['phone_primary'],
                phone_secondary=request.form.get('phone_secondary'),
                email=request.form.get('email'),
                address=request.form.get('address'),
                notes=request.form.get('notes')
            )
            db.session.add(new_contact)
            db.session.commit()
            flash('Contact added successfully!', 'success')
            return redirect(url_for('emergency_contacts.index'))
        except Exception as e:
            logger.error(f'Error adding contact: {str(e)}')
            flash('Error adding contact', 'error')
            return render_template('error.html', error=str(e)), 500
    return render_template('add_contact.html')

# Vitals routes
@vitals_bp.route('/')
def index():
    try:
        return render_template('vitals.html')
    except Exception as e:
        logger.error(f"Error loading vitals page: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@vitals_bp.route('/add', methods=['GET', 'POST'])
def add_vitals():
    try:
        if request.method == 'POST':
            return redirect(url_for('vitals.index'))
        return render_template('add_vitals.html')
    except Exception as e:
        logger.error(f"Error in add vitals: {str(e)}")
        return render_template('error.html', error=str(e)), 500

# Register blueprints
app.register_blueprint(medication_bp)
app.register_blueprint(emergency_contacts_bp)
app.register_blueprint(vitals_bp)

# Initialize database
with app.app_context():
    try:
        db.create_all()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
