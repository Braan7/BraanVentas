from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = None  # will be set in attach_db

def attach_db(app):
    global migrate
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    migrate = Migrate(app, db)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    wallet_balance = db.Column(db.Numeric(12,2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    visible = db.Column(db.Boolean, default=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    price_mx = db.Column(db.Numeric(12,2), nullable=False)
    stock = db.Column(db.Integer, default=0)  # para PINES/servicios que lo requieran
    active = db.Column(db.Boolean, default=True)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, default=1)
    ff_player_id = db.Column(db.String(32))   # Free Fire ID
    ff_player_name = db.Column(db.String(64))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, processing, done, rejected
    method = db.Column(db.String(20))  # wallet / binance
    total_mx = db.Column(db.Numeric(12,2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, default=1)
    unit_price_mx = db.Column(db.Numeric(12,2), nullable=False)
    ff_player_id = db.Column(db.String(32))
    ff_player_name = db.Column(db.String(64))

class TopUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount_mx = db.Column(db.Numeric(12,2), nullable=False)
    method = db.Column(db.String(30))  # oxxo_qr / binance / btc / ltc
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    proof_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    discount_mx = db.Column(db.Numeric(12,2), default=0)
    used_by = db.Column(db.Integer)   # once per user (validado en app)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="open")  # open/closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maintenance_mode = db.Column(db.Boolean, default=False)
