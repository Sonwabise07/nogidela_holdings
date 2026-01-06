from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# 1. Admin User Table (for managing the site)
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<Admin {self.username}>'


# 2. Service Table (Dynamic pricing - can be updated without code changes)
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_xh = db.Column(db.String(100))  # Xhosa translation
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.Text)
    description_xh = db.Column(db.Text)  # Xhosa translation
    is_active = db.Column(db.Boolean, default=True)
    requires_quantity = db.Column(db.Boolean, default=False)
    requires_animal_type = db.Column(db.Boolean, default=False)
    image_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Service {self.name} - R{self.price}>'


# 3. Booking/Enquiry Table (Customer requests)
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_contact = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120))
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    service_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    animal_type = db.Column(db.String(50))  # For meat cutting
    estimated_cost = db.Column(db.Float)
    additional_notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    service = db.relationship('Service', backref='bookings')
    
    def __repr__(self):
        return f'<Booking #{self.id} - {self.client_name}>'


# 4. Contact Messages Table (General enquiries)
class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Message from {self.name}>'