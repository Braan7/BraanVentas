from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
import json, requests
from config import Config
from models import attach_db, db, User, Categoria, Producto, Pedido, PedidoItem, Recarga
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    attach_db(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    class U(UserMixin, User):
        pass
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    @app.context_processor
    def inject_globals():
        return {"whatsapp": app.config["ADMIN_WHATSAPP"], "maintenance": app.config["MAINTENANCE"]}
    @app.before_request
    def maintenance_gate():
        if app.config["MAINTENANCE"] and not (current_user.is_authenticated and current_user.role == "admin"):
            if request.endpoint not in ("login", "static"):
                return render_template("maintenance.html"), 503
    @app.route("/")
    def index():
        cats = Categoria.query.filter_by(activa=True).all()
        destacados = Producto.query.filter_by(visible=True).limit(8).all()
        return render_template("index.html", categorias=cats, destacados=destacados)
    @app.route("/login", methods=["GET","POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username","").strip()
            password = request.form.get("password","")
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=True); return redirect(url_for("index"))
            flash("Credenciales inválidas","danger")
        return render_template("login.html")
    @app.route("/register", methods=["GET","POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username","").strip()
            email = request.form.get("email","").strip()
            password = request.form.get("password","")
            if User.query.filter((User.username==username)|(User.email==email)).first():
                flash("Usuario o email ya existe","warning")
            else:
                u = User(username=username, email=email, password_hash=generate_password_hash(password))
                db.session.add(u); db.session.commit()
                flash("Cuenta creada. Inicia sesión.","success"); return redirect(url_for("login"))
        return render_template("register.html")
    @app.route("/logout"); @login_required
    def logout():
        logout_user(); return redirect(url_for("index"))
    @app.route("/catalogo/<int:cat_id>")
    def catalogo(cat_id):
        cat = Categoria.query.get_or_404(cat_id)
        prods = Producto.query.filter_by(categoria_id=cat.id, visible=True).all()
        return render_template("catalogo.html", categoria=cat, productos=prods)
    def _cart(): return session.setdefault("cart", [])
    @app.route("/cart/add/<int:pid>", methods=["POST"])
    def cart_add(pid):
        qty = int(request.form.get("qty", 1))
        cart = _cart(); found=False
        for item in cart:
            if item["id"]==pid: item["qty"]+=qty; found=True; break
        if not found:
            p = Producto.query.get_or_404(pid)
            cart.append({"id":p.id,"name":p.nombre,"price":float(p.precio),"qty":qty})
        session["cart"]=cart
        return jsonify({"ok":True,"cart_items":sum(i["qty"] for i in cart)})
    @app.route("/cart")
    def cart_view():
        cart=_cart(); total=sum(Decimal(str(i["price"]))*i["qty"] for i in cart)
        return render_template("cart.html", cart=cart, total=total)
    @app.route("/cart/clear", methods=["POST"])
    def cart_clear():
        session["cart"]=[]; return jsonify({"ok":True})
    @app.route("/checkout", methods=["POST"]); @login_required
    def checkout():
        metodo=request.form.get("metodo"); extra_id=request.form.get("ff_id",""); extra_name=request.form.get("ff_name","")
        cart=_cart(); 
        if not cart: return jsonify({"ok":False,"msg":"Carrito vacío"}),400
        total=sum(Decimal(str(i["price"]))*i["qty"] for i in cart)
        if metodo=="saldo":
            if current_user.saldo<total: return jsonify({"ok":False,"msg":"Saldo insuficiente"}),400
            current_user.saldo=current_user.saldo-total
            pedido=Pedido(user_id=current_user.id,total=total,metodo_pago="saldo",estado="pagado",
                          extras_json=json.dumps({"ff_id":extra_id,"ff_name":extra_name}))
            db.session.add(pedido); db.session.flush()
            for it in cart:
                db.session.add(PedidoItem(pedido_id=pedido.id, producto_id=it["id"], cantidad=it["qty"], precio_unitario=Decimal(str(it["price"]))))
            db.session.commit(); session["cart"]=[]
            return jsonify({"ok":True,"redirect":url_for('pedido_ok',pedido_id=pedido.id)})
        elif metodo=="binance":
            pedido=Pedido(user_id=current_user.id,total=total,metodo_pago="binance",estado="pendiente",
                          extras_json=json.dumps({"ff_id":extra_id,"ff_name":extra_name}))
            db.session.add(pedido); db.session.commit()
            wa=app.config["ADMIN_WHATSAPP"].replace("+","")
            msg=f"Hola! Soy {current_user.username}. Quiero pagar por Binance el pedido #{pedido.id} por ${total}. ID FF: {extra_id} - Nombre: {extra_name}"
            link=f"https://wa.me/{wa}?text="+requests.utils.quote(msg)
            return jsonify({"ok":True,"redirect":link})
        else:
            return jsonify({"ok":False,"msg":"Método no soportado"}),400
    @app.route("/pedido-ok/<int:pedido_id>"); @login_required
    def pedido_ok(pedido_id):
        p=Pedido.query.get_or_404(pedido_id); return render_template("pedido_ok.html", pedido=p)
    @app.route("/recargar", methods=["GET","POST"]); @login_required
    def recargar():
        if request.method=="POST":
            from decimal import Decimal
            monto=Decimal(request.form.get("monto","0") or "0")
            metodo=request.form.get("metodo","binance"); comp=request.form.get("comprobante_url","")
            r=Recarga(user_id=current_user.id,monto=monto,metodo=metodo,comprobante_url=comp,estado="pendiente")
            db.session.add(r); db.session.commit()
            flash("Solicitud creada. Te notificaremos al aprobarla.","success")
            wa=app.config["ADMIN_WHATSAPP"].replace("+","")
            msg=f"Hola! Soy {current_user.username}. Envié una recarga de ${monto} por {metodo}. ID: {r.id}. Comprobante: {comp}"
            return redirect(f"https://wa.me/{wa}?text="+requests.utils.quote(msg))
        return render_template("recargar.html")
    def admin_required(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*a,**kw):
            if not current_user.is_authenticated or current_user.role!="admin": return redirect(url_for("login"))
            return fn(*a,**kw)
        return wrapper
    @app.route("/admin"); @login_required; @admin_required
    def admin_home():
        users=User.query.count(); prods=Producto.query.count(); rec_pend=Recarga.query.filter_by(estado="pendiente").count(); ventas=Pedido.query.count()
        return render_template("admin/dashboard.html", users=users, prods=prods, rec_pend=rec_pend, ventas=ventas)
    @app.route("/admin/recargas/<int:rec_id>/<action>", methods=["POST"]); @login_required; @admin_required
    def admin_recargas_action(rec_id, action):
        r=Recarga.query.get_or_404(rec_id)
        if action=="aprobar" and r.estado=="pendiente":
            from decimal import Decimal
            u=User.query.get(r.user_id); u.saldo=(u.saldo or Decimal(0))+r.monto; r.estado="aprobada"
        elif action=="rechazar": r.estado="rechazada"
        db.session.commit(); return redirect(url_for("admin_recargas"))
    @app.route("/admin/recargas"); @login_required; @admin_required
    def admin_recargas():
        recs=Recarga.query.order_by(Recarga.created_at.desc()).all()
        return render_template("admin/recargas.html", recs=recs)
    @app.route("/admin/categorias", methods=["GET","POST"]); @login_required; @admin_required
    def admin_categorias():
        if request.method=="POST":
            nom=request.form.get("nombre","").strip()
            if nom: db.session.add(Categoria(nombre=nom)); db.session.commit()
        cats=Categoria.query.order_by(Categoria.nombre.asc()).all()
        return render_template("admin/categorias.html", cats=cats)
    @app.route("/admin/productos", methods=["GET","POST"]); @login_required; @admin_required
    def admin_productos():
        if request.method=="POST":
            from decimal import Decimal
            cat=int(request.form.get("categoria_id")); nom=request.form.get("nombre",""); desc=request.form.get("descripcion",""); precio=Decimal(request.form.get("precio","0"))
            db.session.add(Producto(categoria_id=cat, nombre=nom, descripcion=desc, precio=precio)); db.session.commit()
        prods=Producto.query.order_by(Producto.id.desc()).all(); cats=Categoria.query.order_by(Categoria.nombre.asc()).all()
        return render_template("admin/productos.html", prods=prods, cats=cats)
    return app
app=create_app()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000)
