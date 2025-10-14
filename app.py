import os
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests

from config import Production
from models import (
    attach_db, db, User, Category, Product, CartItem,
    Order, OrderItem, TopUp, Coupon, Ticket, Setting
)

# --------- App Factory ----------
def create_app():
    app = Flask(_name_)
    app.config.from_object(Production)
    attach_db(app)

    # Seed minimal data (only once)
    with app.app_context():
        db.create_all()
        if not Setting.query.first():
            db.session.add(Setting(maintenance_mode=False))
        if not User.query.filter_by(is_admin=True).first():
            admin = User(
                username="Braan7",
                email="braan@admin.com",
                password_hash=generate_password_hash("Braan7"),
                is_admin=True,
                wallet_balance=Decimal("0.00"),
            )
            db.session.add(admin)
        if not Category.query.filter_by(name="Diamantes FF x ID").first():
            cat = Category(name="Diamantes FF x ID")
            db.session.add(cat)
            db.session.flush()
            # productos de diamantes
            seed = [
                ("Diamantes Free Fire - 110", 15),
                ("Diamantes Free Fire - 341", 45),
                ("Diamantes Free Fire - 572", 75),
                ("Diamantes Free Fire - 1166",150),
                ("Diamantes Free Fire - 2398",265),
                ("Diamantes Free Fire - 6160",600),
                ("Diamantes Free Fire - 12320",1195),
                ("Diamantes Free Fire - 18480",1795),
                ("Diamantes Free Fire - 24640",2395),
                ("Diamantes Free Fire - 30800",2995),
                ("Diamantes Free Fire - 50446",3595),
                ("Tarjeta Básica",8.5),
                ("Tarjeta Semanal",35),
                ("Pase Booyah",35),
                ("Tarjeta Mensual",160),
            ]
            for n,p in seed:
                db.session.add(Product(category_id=cat.id, name=n, price_mx=Decimal(str(p)), stock=999999))
        db.session.commit()

    register_routes(app)
    return app

# --------- Helpers ----------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Acceso solo para administradores", "warning")
            return redirect(url_for("auth_login"))
        return f(*args, **kwargs)
    return wrapper

def peso(val):
    return f"MX${Decimal(val):,.2f}".replace(",", "").replace(".", ",").replace("",".")

# --------- Routes ----------
def register_routes(app: Flask):

    # --- Auth (separate pages) ---
    @app.get("/auth/login")
    def auth_login():
        return render_template_string("""
        <h2>Iniciar sesión</h2>
        <form method="post" action="{{ url_for('auth_login_post') }}">
          <input name="username" placeholder="Usuario" required>
          <input name="password" type="password" placeholder="Contraseña" required>
          <button>Entrar</button>
        </form>
        <p>¿No tienes cuenta? <a href="{{ url_for('auth_register') }}">Regístrate</a></p>
        """)
    @app.post("/auth/login")
    def auth_login_post():
        u = User.query.filter_by(username=request.form["username"]).first()
        if not u or not check_password_hash(u.password_hash, request.form["password"]):
            flash("Credenciales inválidas","danger")
            return redirect(url_for("auth_login"))
        login_user(u)
        return redirect(url_for("home"))

    @app.get("/auth/register")
    def auth_register():
        return render_template_string("""
        <h2>Crear cuenta</h2>
        <form method="post" action="{{ url_for('auth_register_post') }}">
          <input name="username" placeholder="Usuario" required>
          <input name="email" type="email" placeholder="Email" required>
          <input name="password" type="password" placeholder="Contraseña" required>
          <button>Registrarme</button>
        </form>
        """)
    @app.post("/auth/register")
    def auth_register_post():
        if User.query.filter_by(username=request.form["username"]).first():
            flash("Usuario ya existe","warning"); return redirect(url_for("auth_register"))
        if User.query.filter_by(email=request.form["email"]).first():
            flash("Email ya registrado","warning"); return redirect(url_for("auth_register"))
        u = User(
            username=request.form["username"],
            email=request.form["email"],
            password_hash=generate_password_hash(request.form["password"]),
            wallet_balance=Decimal("0.00"),
        )
        db.session.add(u); db.session.commit()
        flash("Cuenta creada, inicia sesión","success")
        return redirect(url_for("auth_login"))

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("auth_login"))

    # --- Home ---
    @app.get("/")
    def home():
        s = Setting.query.first()
        if s and s.maintenance_mode:
            return "<h3>Mantenimiento en curso. Volvemos pronto.</h3>"
        # Top 3 recargadores “reales” por monto de los últimos 7 días
        tops = db.session.execute(db.text("""
            SELECT u.username, COALESCE(SUM(t.amount_mx),0) AS total
            FROM "user" u
            LEFT JOIN top_up t ON t.user_id = u.id AND t.status='approved'
              AND t.created_at >= (CURRENT_DATE - INTERVAL '7 day')
            GROUP BY u.username
            ORDER BY total DESC
            LIMIT 3
        """)).mappings().all()
        destacados = Product.query.filter(Product.active.is_(True)).limit(6).all()
        items = "".join([f"<li>{i+1}. {t['username']} — {peso(t['total'])}</li>" for i,t in enumerate(tops)])
        prods = "".join([f"<li>{p.name} — {peso(p.price_mx)}</li>" for p in destacados])
        return f"""
        <h1>Bienvenido a Tienda Digital Global</h1>
        <h3>Top 3 Recargadores</h3><ol>{items}</ol>
        <h3>Productos destacados</h3><ul>{prods}</ul>
        <p><a href="{url_for('diamonds_catalog')}">Diamantes FF x ID</a> ·
           <a href="{url_for('wallet_topup')}">Recargar saldo</a> ·
           <a href="https://wa.me/{os.getenv('WHATSAPP_NUMBER','+525648804810').replace('+','')}">WhatsApp</a></p>
        """

    # --- Diamonds catalog ---
    @app.route("/catalog/diamantes", methods=["GET","POST"])
    @login_required
    def diamonds_catalog():
        cat = Category.query.filter_by(name="Diamantes FF x ID").first()
        products = Product.query.filter_by(category_id=cat.id, active=True).all()
        if request.method == "POST":
            pid = int(request.form["product_id"])
            qty = int(request.form.get("qty",1))
            ff_id = request.form.get("ff_id","")
            ff_name = request.form.get("ff_name","")
            db.session.add(CartItem(user_id=current_user.id, product_id=pid, qty=qty,
                                    ff_player_id=ff_id, ff_player_name=ff_name))
            db.session.commit()
            flash("Producto agregado al carrito","success")
            return redirect(url_for("diamonds_catalog"))
        # vista simple
        rows = "".join([f"""
        <li>
            {p.name} — {peso(p.price_mx)}
            <form method="post" style="display:inline">
              <input type="hidden" name="product_id" value="{p.id}">
              <input name="ff_id" placeholder="ID del jugador" required>
              <input name="ff_name" placeholder="Nombre del jugador" required>
              <input name="qty" type="number" min="1" value="1">
              <button>Agregar al carrito</button>
            </form>
        </li>""" for p in products])
        return f"""
        <h2>Compra de Diamantes Free Fire</h2>
        <ul>{rows}</ul>
        <p><a href="{url_for('view_cart')}">Ver carrito</a></p>
        """

    # --- Cart & Checkout ---
    @app.get("/cart")
    @login_required
    def view_cart():
        items = (db.session.query(CartItem, Product)
                 .join(Product, Product.id == CartItem.product_id)
                 .filter(CartItem.user_id == current_user.id).all())
        total = sum(ci.qty * pr.price_mx for ci,pr in items)
        li = "".join([f"<li>{pr.name} × {ci.qty} — {peso(ci.qty*pr.price_mx)} "
                      f"({ci.ff_player_id} / {ci.ff_player_name})</li>" for ci,pr in items])
        return f"""
        <h2>Carrito</h2>
        <ul>{li}</ul>
        <p>Total: <b>{peso(total)}</b></p>
        <form method="post" action="{url_for('checkout')}">
          <select name="method" required>
            <option value="wallet">Pagar con saldo del cliente</option>
            <option value="binance">Pagar con Binance (envía comprobante por WhatsApp)</option>
          </select>
          <button>Confirmar compra</button>
        </form>
        <p><a href="{url_for('clear_cart')}">Vaciar carrito</a></p>
        """

    @app.post("/cart/checkout")
    @login_required
    def checkout():
        method = request.form["method"]
        items = (db.session.query(CartItem, Product)
                 .join(Product, Product.id == CartItem.product_id)
                 .filter(CartItem.user_id == current_user.id).all())
        if not items:
            flash("Carrito vacío","warning"); return redirect(url_for("view_cart"))
        total = sum(ci.qty * pr.price_mx for ci,pr in items)

        # cupon (opcional una vez por usuario)
        code = request.form.get("coupon","").strip()
        if code:
            c = Coupon.query.filter_by(code=code).first()
            if c and c.used_by != current_user.id:
                total = max(Decimal("0"), total - c.discount_mx)
                c.used_by = current_user.id
                db.session.add(c)

        if method == "wallet":
            if current_user.wallet_balance < total:
                flash("Saldo insuficiente","danger"); return redirect(url_for("view_cart"))
            current_user.wallet_balance -= total
        ord = Order(user_id=current_user.id, method=method, total_mx=total, status="processing")
        db.session.add(ord); db.session.flush()
        for ci,pr in items:
            db.session.add(OrderItem(order_id=ord.id, product_id=pr.id, qty=ci.qty,
                                     unit_price_mx=pr.price_mx, ff_player_id=ci.ff_player_id,
                                     ff_player_name=ci.ff_player_name))
            db.session.delete(ci)
        db.session.commit()

        if method == "binance":
            phone = os.getenv("WHATSAPP_NUMBER","+525648804810").replace("+","")
            return redirect(f"https://wa.me/{phone}?text=Hola,%20envié%20pago%20Binance%20por%20orden%20#{ord.id}%20total%20{peso(total)}")

        flash(f"Orden #{ord.id} creada. Estado: processing","success")
        return redirect(url_for("home"))

    @app.get("/cart/clear")
    @login_required
    def clear_cart():
        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return redirect(url_for("view_cart"))

    # --- Wallet Top-up (all payment methods with instructions) ---
    @app.route("/wallet/topup", methods=["GET","POST"])
    @login_required
    def wallet_topup():
        if request.method == "POST":
            amount = Decimal(request.form["amount"])
            method = request.form["method"]  # oxxo_qr/binance/btc/ltc
            proof = request.form.get("proof_url","")
            db.session.add(TopUp(user_id=current_user.id, amount_mx=amount, method=method, proof_url=proof))
            db.session.commit()
            flash("Solicitud enviada. Un admin aprobará/rechazará.","info")
            phone = os.getenv("WHATSAPP_NUMBER","+525648804810").replace("+","")
            return redirect(f"https://wa.me/{phone}?text=Hola,%20envié%20comprobante%20de%20recarga%20{peso(amount)}%20({method})")
        return """
        <h2>Recargar saldo</h2>
        <form method="post">
          <input name="amount" type="number" step="0.01" placeholder="Monto MXN" required>
          <select name="method" required>
            <option value="oxxo_qr">OXXO QR</option>
            <option value="binance">Binance (USDT/BEP20)</option>
            <option value="btc">Bitcoin</option>
            <option value="ltc">Litecoin</option>
          </select>
          <input name="proof_url" placeholder="URL del comprobante (opcional)">
          <button>Enviar solicitud</button>
        </form>
        <p>Instrucciones: paga por tu método y sube el comprobante. Un admin revisará tu recarga.</p>
        """

    # --- Admin basic actions ---
    @app.get("/admin")
    @login_required
    @admin_required
    def admin_home():
        pending_topups = TopUp.query.filter_by(status="pending").order_by(TopUp.created_at.desc()).all()
        pending_orders = Order.query.filter_by(status="processing").order_by(Order.created_at.desc()).all()
        return f"""
        <h2>Panel Admin</h2>
        <h3>Recargas pendientes</h3>
        <ul>{"".join([f"<li>#{t.id} {peso(t.amount_mx)} {t.method} — <a href='/admin/topup/{t.id}/approve'>Aprobar</a> | <a href='/admin/topup/{t.id}/reject'>Rechazar</a></li>" for t in pending_topups])}</ul>
        <h3>Órdenes en proceso</h3>
        <ul>{"".join([f"<li>#{o.id} {peso(o.total_mx)} {o.method} — <a href='/admin/order/{o.id}/done'>Marcar completada</a> | <a href='/admin/order/{o.id}/reject'>Rechazar</a></li>" for o in pending_orders])}</ul>
        <p><a href="/admin/maintenance/on">Activar mantenimiento</a> | <a href="/admin/maintenance/off">Desactivar</a></p>
        """

    @app.get("/admin/topup/<int:tid>/approve")
    @login_required
    @admin_required
    def admin_topup_approve(tid):
        t = TopUp.query.get_or_404(tid)
        t.status = "approved"
        u = User.query.get(t.user_id)
        u.wallet_balance += t.amount_mx
        db.session.commit()
        return redirect(url_for("admin_home"))

    @app.get("/admin/topup/<int:tid>/reject")
    @login_required
    @admin_required
    def admin_topup_reject(tid):
        t = TopUp.query.get_or_404(tid)
        t.status = "rejected"
        db.session.commit()
        return redirect(url_for("admin_home"))

    @app.get("/admin/order/<int:oid>/done")
    @login_required
    @admin_required
    def admin_order_done(oid):
        o = Order.query.get_or_404(oid)
        o.status = "done"
        db.session.commit()
        return redirect(url_for("admin_home"))

    @app.get("/admin/order/<int:oid>/reject")
    @login_required
    @admin_required
    def admin_order_reject(oid):
        o = Order.query.get_or_404(oid)
        o.status = "rejected"
        db.session.commit()
        return redirect(url_for("admin_home"))

    # --- Maintenance mode ---
    @app.get("/admin/maintenance/<string:state>")
    @login_required
    @admin_required
    def admin_maintenance(state):
        s = Setting.query.first()
        s.maintenance_mode = (state == "on")
        db.session.commit()
        return redirect(url_for("admin_home"))

    # --- Coupons (one-time per user) ---
    @app.post("/admin/coupon")
    @login_required
    @admin_required
    def admin_coupon_create():
        data = request.get_json(force=True)
        db.session.add(Coupon(code=data["code"], discount_mx=Decimal(str(data["discount_mx"])) ))
        db.session.commit()
        return jsonify(ok=True)

    # --- Tickets (support center) ---
    @app.route("/tickets", methods=["GET","POST"])
    @login_required
    def tickets():
        if request.method == "POST":
            db.session.add(Ticket(user_id=current_user.id,
                                  subject=request.form["subject"],
                                  message=request.form["message"]))
            db.session.commit()
            flash("Ticket creado","success")
            return redirect(url_for("tickets"))
        ts = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.created_at.desc()).all()
        items = "".join([f"<li>#{t.id} {t.subject} — {t.status}</li>" for t in ts])
        return f"""
        <h2>Centro de soporte</h2>
        <form method="post"><input name="subject" placeholder="Asunto" required>
        <textarea name="message" placeholder="Mensaje" required></textarea>
        <button>Enviar</button></form>
        <ul>{items}</ul>
        """

    # --- External APIs (SMM & Documents) : server-side helpers ---
    @app.post("/api/smm/order")
    @login_required
    def smm_order():
        # Expect: service, link, quantity
        payload = {
            "key": app.config["SMM_API_KEY"],
            "action": "add",
            "service": request.json.get("service"),
            "link": request.json.get("link"),
            "quantity": request.json.get("quantity"),
        }
        r = requests.post(app.config["SMM_API_URL"], data=payload, timeout=30)
        return (r.text, r.status_code, {"Content-Type":"application/json"})

    @app.post("/api/docs/order")
    @login_required
    def docs_order():
        # Expect: product_id, data fields per provider
        data = request.json or {}
        data["api_key"] = app.config["DOCS_API_KEY"]
        r = requests.post(f"{app.config['DOCS_API_URL']}/api/order", json=data, timeout=30)
        return (r.text, r.status_code, {"Content-Type":"application/json"})

# --- Dev server ---
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
