# ============ IMPORTS ============
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
from datetime import datetime, date, timedelta
import os
import logging
from functools import wraps
from urllib.parse import quote
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from pathlib import Path

# Database models (imported after app config)
from models import db, Admin, Service, Booking, ContactMessage

# ============ INITIALIZATION ============
load_dotenv()  # Load environment variables

app = Flask(__name__)

# ============ CONFIGURATION ============
# Database Configuration - Railway Volume Support
# Check if running on Railway (use persistent volume)
if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_STATIC_URL"):
    # On Railway - use persistent volume at /data
    db_dir = Path("/data")
    db_dir.mkdir(exist_ok=True)  # Create directory if it doesn't exist
    db_path = db_dir / "nogidela.db"
    database_url = f"sqlite:///{db_path}"
    print(f"🚂 Railway Environment Detected")
    print(f"📁 Database path: {db_path}")
else:
    # Local development or other platforms
    database_url = os.getenv('DATABASE_URL', 'sqlite:///nogidela.db')
    print(f"💻 Local Development Environment")
    print(f"📁 Database: {database_url}")

# Fix for PostgreSQL URLs (if you ever switch to PostgreSQL)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Session Management (12-hour timeout)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# Email Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'Nogidela Holdings <noreply@nogidelaholdings.co.za>')

# Initialize Extensions
mail = Mail(app)
db.init_app(app)  # Only initialize once!

# ============ BUSINESS CONFIGURATION ============
# Read from environment variables with defaults
BUSINESS_CONTACTS = {
    'whatsapp': os.getenv('WHATSAPP_NUMBER', '27732165687'),
    'phone': os.getenv('PHONE_NUMBER', '0823286307'),
    'phone_display': os.getenv('PHONE_DISPLAY', '082 328 6307'),
    'email': os.getenv('BUSINESS_EMAIL', 'mbeko@nogidelaholdings.co.za'),
    'address': os.getenv('BUSINESS_ADDRESS', '8 Bel Avenue, Centane/Kentani, Eastern Cape')
}

# ============ LOGGING SETUP ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ HELPER FUNCTIONS ============
def admin_required(f):
    """Decorator to protect admin routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def format_whatsapp_message(booking_data):
    """Format booking data into WhatsApp message"""
    msg = f"""🔔 NEW BOOKING REQUEST - NOGIDELA HOLDINGS

📋 Service: {booking_data['service_name']}
📅 Date: {booking_data['date']}
📍 Location: {booking_data['location']}

👤 CUSTOMER DETAILS:
Name: {booking_data['customer_name']}
Phone: {booking_data['customer_phone']}
Email: {booking_data['customer_email'] or 'Not provided'}"""
    
    if booking_data.get('quantity'):
        msg += f"\n📦 Quantity: {booking_data['quantity']}"
    
    if booking_data.get('animal_details'):
        msg += f"\n🐄 Animals: {booking_data['animal_details']}"
    
    if booking_data.get('estimated_cost'):
        msg += f"\n💰 Estimated Cost: R{booking_data['estimated_cost']:,.2f}"
    
    if booking_data.get('notes'):
        msg += f"\n📝 Notes: {booking_data['notes']}"
    
    msg += f"\n\n📞 Contact: {BUSINESS_CONTACTS['phone_display']}"
    msg += f"\n✉️ Email: {BUSINESS_CONTACTS['email']}"
    msg += "\n\n⚠️ Please confirm availability and respond to customer."
    return msg

def generate_whatsapp_link(message):
    """Generate WhatsApp link with pre-filled message"""
    return f"https://wa.me/{BUSINESS_CONTACTS['whatsapp']}?text={quote(message)}"

def validate_phone_number(phone):
    """Validate South African phone numbers"""
    import re
    # Remove spaces, plus signs, etc
    clean_phone = re.sub(r'[+\s\-()]', '', phone)
    
    # Check if it's a valid SA number
    if clean_phone.startswith('0'):
        # Local number: 0821234567
        if len(clean_phone) == 10 and clean_phone[0] == '0':
            return '27' + clean_phone[1:]  # Convert to international
    elif clean_phone.startswith('27'):
        # International SA format
        if len(clean_phone) == 11:
            return clean_phone
    
    return None  # Invalid format

# ============ EMAIL FUNCTIONS ============
def send_booking_email(booking, service):
    """Send booking confirmation email to business owner"""
    try:
        formatted_date = booking.service_date.strftime('%A, %d %B %Y')
        animal_details = ""
        
        if service.category == 'Meat' and booking.quantity:
            animal_details = f"""
Animal Details:
- Type: {booking.animal_type}
- Quantity: {booking.quantity}
- Unit Price: R{service.price:,.2f}
"""
        
        cost_section = f"\nEstimated Cost: R{booking.estimated_cost:,.2f}" if booking.estimated_cost else ""
        
        body = f"""NEW BOOKING REQUEST FROM WEBSITE
{'=' * 50}

SERVICE DETAILS:
{'─' * 50}
Service: {service.name}
Category: {service.category}
Date Required: {formatted_date}
Location: {booking.location}
{animal_details}{cost_section}

CUSTOMER INFORMATION:
{'─' * 50}
Name: {booking.client_name}
Phone: {booking.client_contact}
Email: {booking.client_email or 'Not provided'}

ADDITIONAL NOTES:
{'─' * 50}
{booking.additional_notes or 'None'}

BOOKING REFERENCE: #{booking.id}
{'=' * 50}

⚠️ ACTION REQUIRED:
Please confirm availability and contact the customer as soon as possible.

---
Nogidela Holdings Automated Booking System
{BUSINESS_CONTACTS['phone_display']}
{BUSINESS_CONTACTS['email']}"""
        
        msg = Message(
            subject=f"🔔 NEW BOOKING: {service.name} - {formatted_date}",
            recipients=[BUSINESS_CONTACTS['email']],
            body=body
        )
        
        mail.send(msg)
        logger.info(f"✅ Email sent for Booking #{booking.id}")
        return True, None
        
    except Exception as e:
        error_msg = f"Email sending failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg

def send_contact_email(contact_message):
    """Send contact form message to business owner"""
    try:
        body = f"""NEW CONTACT MESSAGE FROM WEBSITE
{'=' * 50}

SENDER INFORMATION:
{'─' * 50}
Name: {contact_message.name}
Email: {contact_message.email or 'Not provided'}
Phone: {contact_message.phone or 'Not provided'}

SUBJECT: {contact_message.subject}

MESSAGE:
{'─' * 50}
{contact_message.message}

{'=' * 50}
Message ID: #{contact_message.id}
Received: {contact_message.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---
Nogidela Holdings Contact Form
{BUSINESS_CONTACTS['phone_display']}
{BUSINESS_CONTACTS['email']}"""
        
        msg = Message(
            subject=f"📧 Contact Form: {contact_message.subject}",
            recipients=[BUSINESS_CONTACTS['email']],
            body=body
        )
        
        mail.send(msg)
        logger.info(f"✅ Contact email sent for Message #{contact_message.id}")
        return True, None
        
    except Exception as e:
        error_msg = f"Contact email failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg

def send_customer_confirmation_email(booking, service):
    """Send confirmation email to customer"""
    if not booking.client_email:
        return False, "No customer email provided"
    
    try:
        formatted_date = booking.service_date.strftime('%A, %d %B %Y')
        
        body = f"""Dear {booking.client_name},

Thank you for booking with Nogidela Holdings!

YOUR BOOKING DETAILS:
{'─' * 50}
Service: {service.name}
Date: {formatted_date}
Location: {booking.location}
Booking Reference: #{booking.id}

We have received your booking request and will contact you within shortly to confirm availability and finalize details.

If you have any questions, please contact us:
📞 Phone: {BUSINESS_CONTACTS['phone_display']}
📧 Email: {BUSINESS_CONTACTS['email']}
💬 WhatsApp: https://wa.me/{BUSINESS_CONTACTS['whatsapp']}

Thank you for choosing Nogidela Holdings!

---
Nogidela Holdings (PTY) LTD
Professional Services in Eastern Cape
{BUSINESS_CONTACTS['address']}"""
        
        msg = Message(
            subject="✅ Booking Confirmation - Nogidela Holdings",
            recipients=[booking.client_email],
            body=body
        )
        
        mail.send(msg)
        logger.info(f"✅ Customer confirmation sent to {booking.client_email}")
        return True, None
        
    except Exception as e:
        error_msg = f"Customer email failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg

# ============ DATABASE INITIALIZATION ============
def init_database():
    """Initialize database with admin and seed services only in development"""
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Create admin only if explicitly enabled via environment variable
        create_admin = os.getenv('CREATE_ADMIN', 'false').lower() == 'true'
        
        if create_admin:
            admin_username = os.getenv('ADMIN_USERNAME', 'admin')
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@nogidelaholdings.co.za')
            admin_password = os.getenv('ADMIN_PASSWORD')
            
            if admin_password:
                existing_admin = Admin.query.filter_by(username=admin_username).first()
                if not existing_admin:
                    admin = Admin(username=admin_username, email=admin_email)
                    admin.set_password(admin_password)
                    db.session.add(admin)
                    db.session.commit()
                    logger.info(f"✓ Admin user '{admin_username}' created")
                else:
                    logger.info(f"ℹ️ Admin user '{admin_username}' already exists")
            else:
                logger.warning("⚠️ ADMIN_PASSWORD not set, skipping admin creation")
        
        # Seed services only if no services exist
        if Service.query.count() == 0:
            initial_services = [
                # MEAT CUTTING SERVICES
                Service(name="Meat Cutting - Cow", name_xh="Ukusika iNyama - Inkomo", price=850.0, unit="per cow", category="Meat", requires_quantity=True, requires_animal_type=True),
                Service(name="Meat Cutting - Sheep", name_xh="Ukusika iNyama - Igusha", price=200.0, unit="per sheep", category="Meat", requires_quantity=True, requires_animal_type=True),
                Service(name="Meat Cutting - Pig", name_xh="Ukusika iNyama - Ihagu", price=250.0, unit="per pig", category="Meat", requires_quantity=True, requires_animal_type=True),
                
                # HIRING SERVICES
                Service(name="Mobile Fridge Hiring", name_xh="Ukuqasha iFiriji Ehambayo", price=2000.0, unit="per event", category="Hiring"),
                Service(name="Cattle Trailer Hiring", name_xh="Ukuqasha iTreyla Yenkomo", price=1000.0, unit="per day", category="Hiring"),
                Service(name="Firewood Delivery", name_xh="Iinkuni", price=1200.0, unit="per load", category="Hiring"),
                
                # LABOR SERVICES
                Service(name="Grass Cutting", name_xh="Ukusika iNgca", price=0.0, unit="quote", category="Labor"),
                Service(name="Tree Felling", name_xh="Ukugawula iMithi", price=0.0, unit="quote", category="Labor"),
                Service(name="Site Clearance", name_xh="Ukucoca iSiza", price=0.0, unit="quote", category="Labor"),
                
                # CONSTRUCTION & TRADING
                Service(name="Construction Services", name_xh="Iinkonzo Zokwakha", price=0.0, unit="quote", category="Construction"),
                Service(name="General Trading", name_xh="Urhwebo Ngokubanzi", price=0.0, unit="quote", category="Trading")
            ]
            db.session.bulk_save_objects(initial_services)
            db.session.commit()
            logger.info("✓ Database initialized with 11 services")
        else:
            # Check if Firewood Delivery exists, add it if not
            firewood_service = Service.query.filter_by(name="Firewood Delivery").first()
            if not firewood_service:
                firewood = Service(name="Firewood Delivery", name_xh="Iinkuni", price=1200.0, unit="per load", category="Hiring")
                db.session.add(firewood)
                db.session.commit()
                logger.info("✓ Firewood Delivery service added to existing database")

# ============ CONTEXT PROCESSORS ============
@app.context_processor
def inject_globals():
    """Inject global variables into all templates"""
    return {
        'contacts': BUSINESS_CONTACTS,
        'current_year': datetime.now().year,
        'env': os.getenv('FLASK_ENV', 'development')
    }

# ============ PUBLIC ROUTES ============
@app.route('/')
def home():
    """Homepage - Browse services freely"""
    services = Service.query.filter_by(is_active=True).all()
    return render_template('home.html', services=services)

@app.route('/services')
def services():
    """Services page - View all services with prices"""
    all_services = Service.query.filter_by(is_active=True).all()
    categories = {
        'Meat': [s for s in all_services if s.category == 'Meat'],
        'Hiring': [s for s in all_services if s.category == 'Hiring'],
        'Labor': [s for s in all_services if s.category == 'Labor'],
        'Construction': [s for s in all_services if s.category == 'Construction'],
        'Trading': [s for s in all_services if s.category == 'Trading']
    }
    return render_template('services.html', categories=categories, today=date.today().isoformat())

@app.route('/service/<int:service_id>')
def service_detail(service_id):
    """Individual service detail page"""
    service = Service.query.get_or_404(service_id)
    return render_template('service_detail.html', service=service)

@app.route('/booking/step1/<int:service_id>', methods=['GET', 'POST'])
def booking_step1(service_id):
    """Step 1: Collect customer details and service specifics"""
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        try:
            # Validate required fields
            required_fields = ['customer_name', 'customer_phone', 'service_date', 'location']
            for field in required_fields:
                if not request.form.get(field):
                    flash(f'Please fill in {field.replace("_", " ")}', 'danger')
                    return redirect(url_for('services'))
            
            # Create booking from form data
            booking = Booking(
                client_name=request.form.get('customer_name').strip(),
                client_contact=request.form.get('customer_phone').strip(),
                client_email=request.form.get('customer_email', '').strip() or None,
                service_id=service_id,
                service_date=datetime.strptime(request.form.get('service_date'), '%Y-%m-%d').date(),
                location=request.form.get('location').strip(),
                additional_notes=request.form.get('additional_notes', '').strip()
            )
            
            # Handle meat cutting specifics
            if service.category == 'Meat':
                booking.quantity = int(request.form.get('quantity', 0))
                booking.estimated_cost = float(request.form.get('estimated_cost', 0))
                
                # Build animal details
                animal_parts = []
                for animal, qty in [('Cow', 'cow_qty'), ('Sheep', 'sheep_qty'), ('Pig', 'pig_qty')]:
                    animal_qty = int(request.form.get(qty, 0))
                    if animal_qty > 0:
                        animal_parts.append(f"{animal_qty} {animal}(s)")
                booking.animal_type = ", ".join(animal_parts) if animal_parts else "Mixed"
            else:
                booking.quantity = 1
                if service.price > 0:
                    booking.estimated_cost = service.price
            
            db.session.add(booking)
            db.session.commit()
            
            # Send emails
            email_success, _ = send_booking_email(booking, service)
            if booking.client_email:
                send_customer_confirmation_email(booking, service)
            
            session['booking_id'] = booking.id
            session['email_sent'] = email_success
            
            return redirect(url_for('booking_confirmation', booking_id=booking.id))
            
        except ValueError as e:
            db.session.rollback()
            flash('Invalid date format. Please try again.', 'danger')
            logger.error(f"Booking error: {e}")
            return redirect(url_for('services'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            logger.error(f"Booking error: {e}")
            return redirect(url_for('services'))
    
    return render_template('booking_step1.html', service=service)

@app.route('/booking/confirmation/<int:booking_id>')
def booking_confirmation(booking_id):
    """Confirmation page with email status and WhatsApp backup"""
    booking = Booking.query.get_or_404(booking_id)
    service = booking.service
    email_sent = session.get('email_sent', False)
    session.pop('email_sent', None)
    
    # Prepare WhatsApp backup
    booking_data = {
        'service_name': service.name,
        'date': booking.service_date.strftime('%A, %d %B %Y'),
        'location': booking.location,
        'customer_name': booking.client_name,
        'customer_phone': booking.client_contact,
        'customer_email': booking.client_email,
        'notes': booking.additional_notes
    }
    
    if booking.quantity and booking.quantity > 1:
        booking_data['quantity'] = booking.quantity
        if service.category == 'Meat':
            booking_data['animal_details'] = f"{booking.quantity}x {service.name}"
    
    if booking.estimated_cost:
        booking_data['estimated_cost'] = booking.estimated_cost
    
    whatsapp_message = format_whatsapp_message(booking_data)
    whatsapp_link = generate_whatsapp_link(whatsapp_message)
    
    return render_template('booking_confirmation.html',
                         booking=booking, service=service,
                         email_sent=email_sent, whatsapp_link=whatsapp_link)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page with FAQ"""
    if request.method == 'POST':
        try:
            # Validate required fields
            if not request.form.get('name') or not request.form.get('message'):
                flash('Please fill in required fields', 'danger')
                return redirect(url_for('contact'))
            
            inquiry_type = request.form.get('inquiry_type')
            message_text = f"FAQ Inquiry: {request.form.get('faq_question')}" if inquiry_type == 'faq' else request.form.get('message')
            
            message = ContactMessage(
                name=request.form.get('name').strip(),
                email=request.form.get('email', '').strip() or None,
                phone=request.form.get('phone', '').strip() or None,
                subject=request.form.get('subject', 'General Inquiry').strip(),
                message=message_text.strip()
            )
            db.session.add(message)
            db.session.commit()
            
            email_success, _ = send_contact_email(message)
            
            # WhatsApp backup
            contact_msg = f"""📧 NEW CONTACT MESSAGE - NOGIDELA HOLDINGS

From: {message.name}
Phone: {message.phone or 'Not provided'}
Email: {message.email or 'Not provided'}

Subject: {message.subject}

Message:
{message.message}"""
            whatsapp_link = generate_whatsapp_link(contact_msg)
            
            flash('Thank you for your message! We will get back to you soon.', 'success')
            return render_template('contact_success.html',
                                 email_sent=email_success,
                                 whatsapp_link=whatsapp_link)
            
        except Exception as e:
            flash('An error occurred. Please try again.', 'danger')
            logger.error(f"Contact error: {e}")
    
    # FAQs
    faqs = [
        {'question': 'What areas do you serve?', 'answer': 'We primarily serve the Eastern Cape region, especially Centane/Kentani and surrounding areas.'},
        {'question': 'How do I change or cancel my booking?', 'answer': 'Contact us via WhatsApp or email with your booking reference number.'},
        {'question': 'Do you offer emergency services?', 'answer': 'Yes, for urgent requests call or WhatsApp directly.'},
        {'question': 'What payment methods do you accept?', 'answer': 'Cash, EFT, and other agreed payment methods.'},
        {'question': 'How far in advance should I book?', 'answer': '3-7 days in advance, especially for weekends and events.'}
    ]
    
    return render_template('contact.html', faqs=faqs)

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

# ============ ADMIN ROUTES (HIDDEN URL: /ng-control/) ============
@app.route('/ng-control/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page - HIDDEN URL for security"""
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter username and password', 'danger')
            return render_template('admin/login.html')
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            session.permanent = True
            logger.info(f"Admin login: {username}")
            flash('Welcome back!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            logger.warning(f"Failed admin login attempt: {username}")
            flash('Invalid username or password', 'danger')
    
    return render_template('admin/login.html')

@app.route('/ng-control/logout')
@admin_required
def admin_logout():
    """Admin logout - Clears all session data"""
    username = session.get('admin_username')
    session.clear()
    logger.info(f"Admin logout: {username}")
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

@app.route('/ng-control/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard - MAIN CONTROL PANEL"""
    from sqlalchemy import func
    
    # Current month stats
    now = datetime.now()
    first_day = datetime(now.year, now.month, 1)
    this_month_bookings = Booking.query.filter(Booking.created_at >= first_day).all()
    this_month_revenue = sum(b.estimated_cost for b in this_month_bookings if b.estimated_cost and b.status in ['Confirmed', 'Completed'])
    
    # Quick stats
    stats = {
        'pending_count': Booking.query.filter_by(status='Pending').count(),
        'this_month_bookings': len(this_month_bookings),
        'this_month_revenue': this_month_revenue,
        'unread_messages': ContactMessage.query.filter_by(is_read=False).count(),
        'total_services': Service.query.filter_by(is_active=True).count(),
        'total_customers': db.session.query(Booking.client_contact).distinct().count()
    }
    
    # Data for display
    pending_bookings = Booking.query.filter_by(status='Pending').order_by(Booking.service_date.asc()).all()
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(30).all()
    unread_messages = ContactMessage.query.filter_by(is_read=False).order_by(ContactMessage.created_at.desc()).all()
    services = Service.query.order_by(Service.category, Service.name).all()
    
    return render_template('admin/dashboard.html',
                         stats=stats, pending_bookings=pending_bookings,
                         recent_bookings=recent_bookings, unread_messages=unread_messages,
                         services=services, now=datetime.now())

@app.route('/ng-control/services', methods=['GET', 'POST'])
@admin_required
def admin_services():
    """Manage services and prices - MAIN FEATURE"""
    services = Service.query.order_by(Service.category, Service.name).all()
    services_by_category = {}
    for service in services:
        if service.category not in services_by_category:
            services_by_category[service.category] = []
        services_by_category[service.category].append(service)
    
    return render_template('admin/services.html', services_by_category=services_by_category)

@app.route('/ng-control/service/update-price/<int:service_id>', methods=['POST'])
@admin_required
def update_service_price(service_id):
    """Quick price update"""
    service = Service.query.get_or_404(service_id)
    
    try:
        new_price = float(request.form.get('price', 0))
        old_price = service.price
        service.price = new_price
        db.session.commit()
        logger.info(f"Price updated: {service.name} - R{old_price:.2f} → R{new_price:.2f}")
        flash(f'✅ {service.name}: Price updated from R{old_price:.2f} to R{new_price:.2f}', 'success')
    except ValueError:
        flash('❌ Please enter a valid number', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error updating price: {str(e)}', 'danger')
    
    return redirect(url_for('admin_services'))

@app.route('/ng-control/service/toggle/<int:service_id>', methods=['POST'])
@admin_required
def toggle_service(service_id):
    """Activate/Deactivate service"""
    service = Service.query.get_or_404(service_id)
    service.is_active = not service.is_active
    db.session.commit()
    status = "activated" if service.is_active else "deactivated"
    logger.info(f"Service {status}: {service.name}")
    flash(f'✅ {service.name} has been {status}', 'success')
    return redirect(url_for('admin_services'))

@app.route('/ng-control/bookings')
@admin_required
def admin_bookings():
    """View all bookings with filters"""
    status_filter = request.args.get('status', 'all')
    month_filter = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    query = Booking.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            start_date = datetime(year, month, 1)
            end_date = datetime(year, month + 1, 1) if month != 12 else datetime(year + 1, 1, 1)
            query = query.filter(Booking.created_at >= start_date, Booking.created_at < end_date)
        except:
            pass
    
    bookings = query.order_by(Booking.created_at.desc()).all()
    total_revenue = sum(b.estimated_cost for b in bookings if b.estimated_cost)
    
    return render_template('admin/bookings.html',
                         bookings=bookings, total_revenue=total_revenue,
                         status_filter=status_filter, month_filter=month_filter)

@app.route('/ng-control/booking/<int:booking_id>/status', methods=['POST'])
@admin_required
def update_booking_status(booking_id):
    """Update booking status"""
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    
    if new_status in ['Pending', 'Confirmed', 'Completed', 'Cancelled']:
        old_status = booking.status
        booking.status = new_status
        db.session.commit()
        logger.info(f"Booking #{booking.id} status changed: {old_status} → {new_status}")
        flash(f'✅ Booking #{booking.id} status changed from {old_status} to {new_status}', 'success')
    
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/ng-control/messages')
@admin_required
def admin_messages():
    """View all contact messages"""
    filter_type = request.args.get('filter', 'all')
    
    query = ContactMessage.query
    
    if filter_type == 'unread':
        query = query.filter_by(is_read=False)
    elif filter_type == 'today':
        today = date.today()
        query = query.filter(func.date(ContactMessage.created_at) == today)
    
    messages = query.order_by(ContactMessage.is_read.asc(), ContactMessage.created_at.desc()).all()
    
    # Stats for the page
    unread_count = ContactMessage.query.filter_by(is_read=False).count()
    total_messages = ContactMessage.query.count()
    today_messages = ContactMessage.query.filter(func.date(ContactMessage.created_at) == date.today()).count()
    
    return render_template('admin/messages.html',
                         messages=messages, filter_type=filter_type,
                         unread_count=unread_count, total_messages=total_messages,
                         today_messages=today_messages, now=datetime.now())

@app.route('/ng-control/message/<int:message_id>/toggle-read', methods=['POST'])
@admin_required
def toggle_message_read(message_id):
    """Mark message as read/unread"""
    message = ContactMessage.query.get_or_404(message_id)
    message.is_read = not message.is_read
    db.session.commit()
    status = "read" if message.is_read else "unread"
    logger.info(f"Message #{message.id} marked as {status}")
    flash(f'✅ Message marked as {status}', 'success')
    return redirect(url_for('admin_messages'))

@app.route('/ng-control/reports/monthly')
@admin_required
def admin_monthly_report():
    """Generate monthly report"""
    import calendar
    month_str = request.args.get('month', datetime.now().strftime('%Y-%m'))
    year, month = map(int, month_str.split('-'))
    
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59)
    
    bookings = Booking.query.filter(Booking.created_at >= first_day, Booking.created_at <= last_day).all()
    messages = ContactMessage.query.filter(ContactMessage.created_at >= first_day, ContactMessage.created_at <= last_day).all()
    
    # Calculate stats
    total_bookings = len(bookings)
    completed = len([b for b in bookings if b.status == 'Completed'])
    confirmed = len([b for b in bookings if b.status == 'Confirmed'])
    pending = len([b for b in bookings if b.status == 'Pending'])
    cancelled = len([b for b in bookings if b.status == 'Cancelled'])
    total_revenue = sum(b.estimated_cost for b in bookings if b.estimated_cost and b.status in ['Confirmed', 'Completed'])
    
    # Group by service
    service_stats = {}
    for booking in bookings:
        service_name = booking.service.name
        if service_name not in service_stats:
            service_stats[service_name] = {'count': 0, 'revenue': 0}
        service_stats[service_name]['count'] += 1
        if booking.estimated_cost and booking.status in ['Confirmed', 'Completed']:
            service_stats[service_name]['revenue'] += booking.estimated_cost
    
    report_data = {
        'month': first_day.strftime('%B %Y'),
        'month_value': month_str,
        'total_bookings': total_bookings,
        'completed': completed,
        'confirmed': confirmed,
        'pending': pending,
        'cancelled': cancelled,
        'total_revenue': total_revenue,
        'service_stats': service_stats,
        'total_messages': len(messages),
        'bookings': bookings
    }
    
    return render_template('admin/monthly_report.html', report=report_data)

@app.route('/ng-control/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    """Change admin password - Security feature"""
    if request.method == 'POST':
        admin = Admin.query.get(session['admin_id'])
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not admin.check_password(current_password):
            flash('❌ Current password is incorrect', 'danger')
        elif new_password != confirm_password:
            flash('❌ New passwords do not match', 'danger')
        elif len(new_password) < 8:
            flash('❌ Password must be at least 8 characters', 'danger')
        elif current_password == new_password:
            flash('❌ New password must be different from current password', 'danger')
        else:
            admin.set_password(new_password)
            db.session.commit()
            logger.info(f"Password changed for admin: {admin.username}")
            flash('✅ Password changed successfully! Please log in again.', 'success')
            session.clear()
            return redirect(url_for('admin_login'))
    
    return render_template('admin/change_password.html')

# ============ API ENDPOINTS ============
@app.route('/api/services')
def api_services():
    """API endpoint to get all active services"""
    services = Service.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': s.id, 'name': s.name, 'name_xh': s.name_xh,
        'price': s.price, 'unit': s.unit, 'category': s.category
    } for s in services])

@app.route('/api/service/<int:service_id>')
def api_service_detail(service_id):
    """API endpoint to get single service details"""
    service = Service.query.get_or_404(service_id)
    return jsonify({
        'id': service.id, 'name': service.name, 'name_xh': service.name_xh,
        'price': service.price, 'unit': service.unit, 'category': service.category,
        'description': service.description, 'requires_quantity': service.requires_quantity
    })

# ============ ERROR HANDLERS ============
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 Error: {e}")
    return render_template('errors/500.html'), 500

# ============ APP RUNNER ============
if __name__ == '__main__':
    print("=" * 60)
    print("NOGIDELA HOLDINGS - Starting Server")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Check environment
    env = os.getenv('FLASK_ENV', 'development')
    print(f"\n🌍 Environment: {env}")
    
    # Check email configuration
    print("\n📧 Email Configuration:")
    if app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'):
        print(f"   ✅ Email configured: {app.config['MAIL_USERNAME'][:10]}...")
        print(f"   ✅ Mail server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
    else:
        print("   ⚠️  WARNING: Email not configured! Booking emails will not be sent")
    
    # Check business contacts
    print("\n📞 Business Contacts:")
    print(f"   ✅ WhatsApp: {BUSINESS_CONTACTS['whatsapp']}")
    print(f"   ✅ Phone: {BUSINESS_CONTACTS['phone_display']}")
    print(f"   ✅ Email: {BUSINESS_CONTACTS['email']}")
    
    print("\n" + "=" * 60)
    print("✅ Server is ready!")
    print("=" * 60)

    # RENDER / DEPLOYMENT CONFIGURATION:
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)