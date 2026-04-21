from flask import Flask, render_template, request, redirect, session, flash, Response, g
import mysql.connector
import os, csv, io, datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "uktrip_secret_2024")

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ══════════════════════════════════════════════════════
#  DATABASE — one connection per request via Flask g
# ══════════════════════════════════════════════════════

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "uk_trip"),
            autocommit=False
        )
    return g.db


@app.teardown_appcontext
def close_db(error):
    db_conn = g.pop('db', None)
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass


def query(sql, params=(), one=False, commit=False):
    """Run a query. Returns list/dict/lastrowid. Never raises — returns None on error."""
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        if commit:
            conn.commit()
            lid = cursor.lastrowid
            cursor.close()
            return lid
        result = cursor.fetchone() if one else cursor.fetchall()
        cursor.close()
        return result
    except Exception:
        return None


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def verify_password(stored_password, provided_password):
    """
    Accepts BOTH plain-text passwords (old database) and
    werkzeug hashed passwords (new registrations).
    On first login with plain text, the login route upgrades it to a hash.
    """
    if not stored_password or not provided_password:
        return False
    # Detect hashed password (werkzeug format starts with algorithm name)
    if stored_password.startswith("pbkdf2:") or stored_password.startswith("scrypt:"):
        try:
            return check_password_hash(stored_password, provided_password)
        except Exception:
            return False
    # Plain text comparison (old database rows)
    return stored_password == provided_password


# ══════════════════════════════════════════════════════
#  AUTO CREATE NEW TABLES ON STARTUP
#  This runs once when Flask starts — safe, uses IF NOT EXISTS
# ══════════════════════════════════════════════════════

def create_new_tables():
    stmts = [
        """CREATE TABLE IF NOT EXISTS notification (
            id INT AUTO_INCREMENT PRIMARY KEY,
            adharno VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            is_read TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS wishlist (
            id INT AUTO_INCREMENT PRIMARY KEY,
            adharno VARCHAR(20) NOT NULL,
            package_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_wish (adharno, package_id)
        )""",
        """CREATE TABLE IF NOT EXISTS announcement (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]
    # Add admin_note column to booking if missing
    alter = "ALTER TABLE booking ADD COLUMN IF NOT EXISTS admin_note TEXT DEFAULT NULL"

    try:
        conn   = mysql.connector.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "uk_trip")
        )
        cursor = conn.cursor()
        for s in stmts:
            try:
                cursor.execute(s)
                conn.commit()
            except Exception:
                pass
        try:
            cursor.execute(alter)
            conn.commit()
        except Exception:
            pass
        cursor.close()
        conn.close()
    except Exception:
        pass  # DB might not be ready yet — routes handle their own errors


# Run table creation when app starts
with app.app_context():
    create_new_tables()


# ══════════════════════════════════════════════════════
#  TEMPLATE GLOBALS — injected into every template
#  CRITICAL FIX: wrapped in try/except so a missing table
#  never causes a 500 error on every page
# ══════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    notif_count   = 0
    pending_admin = 0
    announcements = []
    wishlist_count = 0

    try:
        if "user_id" in session:
            row = query(
                "SELECT COUNT(*) AS cnt FROM notification WHERE adharno=%s AND is_read=0",
                (session["user_id"],), one=True
            )
            notif_count = int(row["cnt"]) if row and row.get("cnt") else 0

            wl = query(
                "SELECT COUNT(*) AS cnt FROM wishlist WHERE adharno=%s",
                (session["user_id"],), one=True
            )
            wishlist_count = int(wl["cnt"]) if wl and wl.get("cnt") else 0

        if "admin" in session:
            row = query(
                "SELECT COUNT(*) AS cnt FROM booking WHERE status='Booked'", one=True
            )
            pending_admin = int(row["cnt"]) if row and row.get("cnt") else 0

        ann = query("SELECT * FROM announcement ORDER BY created_at DESC LIMIT 3")
        announcements = ann if ann else []

    except Exception:
        pass  # Never crash a page just because of sidebar counts

    return dict(
        notif_count=notif_count,
        pending_admin=pending_admin,
        announcements=announcements,
        wishlist_count=wishlist_count
    )


# ══════════════════════════════════════════════════════
#  AUTH DECORATORS
# ══════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin" not in session:
            flash("Admin access required.", "danger")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════
#  NOTIFICATION HELPER
# ══════════════════════════════════════════════════════

def notify(adharno, message):
    try:
        query(
            "INSERT INTO notification (adharno, message) VALUES (%s, %s)",
            (adharno, message), commit=True
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  HOME / AUTH
# ══════════════════════════════════════════════════════

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    if "admin" in session:
        return redirect("/admin_dashboard")
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    role     = request.form.get("role", "user").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect("/")

    try:
        if role == "admin":
            admin = query("SELECT * FROM admin WHERE name=%s", (username,), one=True)
            if admin and verify_password(admin["password"], password):
                # Auto-upgrade plain text to hash on first login
                if not admin["password"].startswith("pbkdf2:") and not admin["password"].startswith("scrypt:"):
                    query("UPDATE admin SET password=%s WHERE id=%s",
                          (generate_password_hash(password), admin["id"]), commit=True)
                session.clear()
                session["admin"] = admin["name"]
                return redirect("/admin_dashboard")
            flash("Invalid admin credentials.", "danger")
            return redirect("/")

        user = query("SELECT * FROM traveler WHERE name=%s", (username,), one=True)
        if user and verify_password(user["password"], password):
            # Auto-upgrade plain text to hash on first login
            if not user["password"].startswith("pbkdf2:") and not user["password"].startswith("scrypt:"):
                query("UPDATE traveler SET password=%s WHERE adharno=%s",
                      (generate_password_hash(password), user["adharno"]), commit=True)
            session.clear()
            session["user"]    = user["name"]
            session["user_id"] = user["adharno"]
            return redirect("/dashboard")

        flash("Invalid username or password.", "danger")
        return redirect("/")

    except Exception as e:
        flash(f"Login error: {e}", "danger")
        return redirect("/")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/register_user", methods=["POST"])
def register_user():
    adhar    = request.form.get("adhar", "").strip()
    name     = request.form.get("name", "").strip()
    address  = request.form.get("address", "").strip()
    mobile   = request.form.get("mobile", "").strip()
    password = request.form.get("password", "")

    if not all([adhar, name, address, mobile, password]):
        flash("All fields are required.", "danger")
        return redirect("/register")
    if not adhar.isdigit() or len(adhar) != 12:
        flash("Aadhaar must be exactly 12 digits.", "danger")
        return redirect("/register")
    if not mobile.isdigit() or len(mobile) != 10:
        flash("Mobile must be exactly 10 digits.", "danger")
        return redirect("/register")
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect("/register")

    try:
        existing = query("SELECT adharno FROM traveler WHERE adharno=%s", (adhar,), one=True)
        if existing:
            flash("This Aadhaar number is already registered.", "warning")
            return redirect("/register")

        hashed = generate_password_hash(password)
        query(
            "INSERT INTO traveler (adharno, name, address, mobile, password) VALUES (%s,%s,%s,%s,%s)",
            (adhar, name, address, mobile, hashed), commit=True
        )
        flash("Registration successful! Please log in.", "success")
        return redirect("/")

    except Exception as e:
        flash(f"Registration failed: {e}", "danger")
        return redirect("/register")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/")


# ══════════════════════════════════════════════════════
#  USER — DASHBOARD
# ══════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    try:
        r1 = query("SELECT COUNT(*) AS c FROM booking WHERE adharno=%s", (uid,), one=True)
        r2 = query("SELECT COUNT(*) AS c FROM booking WHERE adharno=%s AND status='Approved'", (uid,), one=True)
        r3 = query("SELECT COUNT(*) AS c FROM booking WHERE adharno=%s AND status='Booked'", (uid,), one=True)
        r4 = query("SELECT COALESCE(SUM(total_amount),0) AS s FROM booking WHERE adharno=%s AND status='Approved'", (uid,), one=True)

        total_bookings    = int(r1["c"]) if r1 else 0
        approved_bookings = int(r2["c"]) if r2 else 0
        pending_bookings  = int(r3["c"]) if r3 else 0
        total_spent       = int(r4["s"]) if r4 else 0

        recent_bookings = query(
            """SELECT b.*, p.category, p.duration
               FROM booking b
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE b.adharno=%s ORDER BY b.booking_id DESC LIMIT 5""",
            (uid,)
        ) or []

        wl = query("SELECT COUNT(*) AS c FROM wishlist WHERE adharno=%s", (uid,), one=True)
        wishlist_count = int(wl["c"]) if wl else 0

        return render_template("dashboard.html",
            user=session["user"],
            total_bookings=total_bookings,
            approved_bookings=approved_bookings,
            pending_bookings=pending_bookings,
            total_spent=total_spent,
            recent_bookings=recent_bookings,
            wishlist_count=wishlist_count
        )
    except Exception as e:
        flash(f"Could not load dashboard: {e}", "danger")
        return render_template("dashboard.html", user=session["user"],
            total_bookings=0, approved_bookings=0, pending_bookings=0,
            total_spent=0, recent_bookings=[], wishlist_count=0)


# ══════════════════════════════════════════════════════
#  USER — PROFILE
# ══════════════════════════════════════════════════════

@app.route("/profile")
@login_required
def profile():
    user = query("SELECT * FROM traveler WHERE adharno=%s", (session["user_id"],), one=True)
    if not user:
        flash("User not found.", "danger")
        return redirect("/dashboard")
    return render_template("profile.html", user=user)


@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    name    = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    mobile  = request.form.get("mobile", "").strip()
    cur_pw  = request.form.get("current_password", "")
    new_pw  = request.form.get("new_password", "")
    conf_pw = request.form.get("confirm_password", "")

    if not all([name, address, mobile]):
        flash("Name, address, and mobile are required.", "danger")
        return redirect("/profile")
    if not mobile.isdigit() or len(mobile) != 10:
        flash("Mobile must be 10 digits.", "danger")
        return redirect("/profile")

    try:
        if new_pw:
            if new_pw != conf_pw:
                flash("New passwords do not match.", "danger")
                return redirect("/profile")
            if len(new_pw) < 6:
                flash("Password must be at least 6 characters.", "danger")
                return redirect("/profile")
            row = query("SELECT password FROM traveler WHERE adharno=%s", (session["user_id"],), one=True)
            if not row or not verify_password(row["password"], cur_pw):
                flash("Current password is incorrect.", "danger")
                return redirect("/profile")
            hashed = generate_password_hash(new_pw)
            query(
                "UPDATE traveler SET name=%s, address=%s, mobile=%s, password=%s WHERE adharno=%s",
                (name, address, mobile, hashed, session["user_id"]), commit=True
            )
        else:
            query(
                "UPDATE traveler SET name=%s, address=%s, mobile=%s WHERE adharno=%s",
                (name, address, mobile, session["user_id"]), commit=True
            )
        session["user"] = name
        flash("Profile updated successfully.", "success")
        return redirect("/profile")
    except Exception as e:
        flash(f"Could not update profile: {e}", "danger")
        return redirect("/profile")


# ══════════════════════════════════════════════════════
#  USER — NOTIFICATIONS
# ══════════════════════════════════════════════════════

@app.route("/notifications")
@login_required
def notifications():
    try:
        notifs = query(
            "SELECT * FROM notification WHERE adharno=%s ORDER BY created_at DESC",
            (session["user_id"],)
        ) or []
        query("UPDATE notification SET is_read=1 WHERE adharno=%s",
              (session["user_id"],), commit=True)
        return render_template("notifications.html", notifs=notifs)
    except Exception as e:
        flash(f"Could not load notifications: {e}", "danger")
        return render_template("notifications.html", notifs=[])


# ══════════════════════════════════════════════════════
#  USER — WISHLIST
# ══════════════════════════════════════════════════════

@app.route("/wishlist")
@login_required
def wishlist():
    try:
        items = query(
            """SELECT p.*, pi.image
               FROM wishlist w
               JOIN package p ON w.package_id=p.package_id
               LEFT JOIN package_images pi ON p.package_id=pi.package_id
               WHERE w.adharno=%s
               GROUP BY p.package_id, pi.image""",
            (session["user_id"],)
        ) or []
        pkg_dict = {}
        for row in items:
            pid = row["package_id"]
            if pid not in pkg_dict:
                pkg_dict[pid] = dict(row)
                pkg_dict[pid]["images"] = []
            if row.get("image"):
                pkg_dict[pid]["images"].append(row["image"])
        return render_template("wishlist.html", packages=list(pkg_dict.values()))
    except Exception as e:
        flash(f"Could not load wishlist: {e}", "danger")
        return render_template("wishlist.html", packages=[])


@app.route("/wishlist/add/<int:pid>")
@login_required
def wishlist_add(pid):
    try:
        existing = query(
            "SELECT id FROM wishlist WHERE adharno=%s AND package_id=%s",
            (session["user_id"], pid), one=True
        )
        if not existing:
            query("INSERT INTO wishlist (adharno, package_id) VALUES (%s,%s)",
                  (session["user_id"], pid), commit=True)
            flash("Added to wishlist! ❤️", "success")
        else:
            flash("Already in your wishlist.", "info")
    except Exception as e:
        flash(f"Could not update wishlist: {e}", "danger")
    return redirect("/packages")


@app.route("/wishlist/remove/<int:pid>")
@login_required
def wishlist_remove(pid):
    try:
        query("DELETE FROM wishlist WHERE adharno=%s AND package_id=%s",
              (session["user_id"], pid), commit=True)
        flash("Removed from wishlist.", "info")
    except Exception as e:
        flash(f"Could not remove: {e}", "danger")
    return redirect("/wishlist")


# ══════════════════════════════════════════════════════
#  USER — PACKAGES
# ══════════════════════════════════════════════════════

@app.route("/packages")
@login_required
def packages():
    try:
        data = query(
            """SELECT p.*, pi.image
               FROM package p
               LEFT JOIN package_images pi ON p.package_id=pi.package_id
               ORDER BY p.package_id"""
        ) or []

        packages_dict = {}
        for row in data:
            pid = row["package_id"]
            if pid not in packages_dict:
                packages_dict[pid] = dict(row)
                packages_dict[pid]["images"] = []
            if row.get("image"):
                packages_dict[pid]["images"].append(row["image"])

        # Wishlist set for heart icons
        wl_rows = query(
            "SELECT package_id FROM wishlist WHERE adharno=%s", (session["user_id"],)
        ) or []
        wishlist_ids = {r["package_id"] for r in wl_rows}

        # Average ratings
        ratings = query(
            """SELECT b.package_id, AVG(r.rating) AS avg_rating, COUNT(r.review_id) AS review_count
               FROM review r JOIN booking b ON r.booking_id=b.booking_id
               GROUP BY b.package_id"""
        ) or []
        rating_map = {r["package_id"]: r for r in ratings}

        pkg_list = list(packages_dict.values())
        for p in pkg_list:
            p["in_wishlist"]   = p["package_id"] in wishlist_ids
            rd = rating_map.get(p["package_id"])
            p["avg_rating"]    = round(float(rd["avg_rating"]), 1) if rd else None
            p["review_count"]  = rd["review_count"] if rd else 0

        return render_template("packages.html", packages=pkg_list)
    except Exception as e:
        flash(f"Could not load packages: {e}", "danger")
        return redirect("/dashboard")


@app.route("/view_images/<int:id>")
@login_required
def view_images(id):
    try:
        images = query("SELECT image FROM package_images WHERE package_id=%s", (id,)) or []
        pkg    = query("SELECT category FROM package WHERE package_id=%s", (id,), one=True)
        return render_template("view_images.html", images=images, pkg=pkg)
    except Exception as e:
        flash(f"Could not load images: {e}", "danger")
        return redirect("/packages")


# ══════════════════════════════════════════════════════
#  USER — BOOKING
# ══════════════════════════════════════════════════════

@app.route("/book/<int:id>")
@login_required
def book(id):
    try:
        dup = query(
            "SELECT booking_id FROM booking WHERE adharno=%s AND package_id=%s AND status='Booked'",
            (session["user_id"], id), one=True
        )
        if dup:
            flash("You already have a pending booking for this package.", "warning")
            return redirect("/packages")

        pkg = query("SELECT * FROM package WHERE package_id=%s", (id,), one=True)
        if not pkg:
            flash("Package not found.", "danger")
            return redirect("/packages")

        travel_date = request.args.get("travel_date", "").strip()

        if travel_date:
            try:
                td = datetime.date.fromisoformat(travel_date)
                if td < datetime.date.today():
                    flash("Travel date cannot be in the past.", "danger")
                    return redirect("/packages")
            except ValueError:
                flash("Invalid travel date.", "danger")
                return redirect("/packages")
            query(
                "INSERT INTO booking(adharno,package_id,travel_date,total_amount,status) VALUES(%s,%s,%s,%s,'Booked')",
                (session["user_id"], id, travel_date, pkg["amt_rate"]), commit=True
            )
        else:
            query(
                "INSERT INTO booking(adharno,package_id,travel_date,total_amount,status) VALUES(%s,%s,CURDATE(),%s,'Booked')",
                (session["user_id"], id, pkg["amt_rate"]), commit=True
            )

        notify(session["user_id"],
               f"Your booking for '{pkg['category']}' (Rs.{pkg['amt_rate']}) is pending approval.")
        flash(f"Booking placed for '{pkg['category']}'! Awaiting admin approval.", "success")
        return redirect("/my_bookings")

    except Exception as e:
        flash(f"Booking failed: {e}", "danger")
        return redirect("/packages")


@app.route("/my_bookings")
@login_required
def my_bookings():
    try:
        bookings = query(
            """SELECT b.*, p.category, p.duration
               FROM booking b
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE b.adharno=%s ORDER BY b.booking_id DESC""",
            (session["user_id"],)
        ) or []
        return render_template("my_bookings.html", bookings=bookings)
    except Exception as e:
        flash(f"Could not load bookings: {e}", "danger")
        return render_template("my_bookings.html", bookings=[])


@app.route("/cancel/<int:id>")
@login_required
def cancel(id):
    try:
        query(
            "UPDATE booking SET status='Cancelled' WHERE booking_id=%s AND adharno=%s AND status='Booked'",
            (id, session["user_id"]), commit=True
        )
        flash("Booking cancelled.", "info")
    except Exception as e:
        flash(f"Could not cancel: {e}", "danger")
    return redirect("/my_bookings")


@app.route("/receipt/<int:id>")
@login_required
def receipt(id):
    try:
        b = query(
            """SELECT b.*, p.category, p.duration, p.description,
                      t.name AS traveler_name, t.mobile, t.address
               FROM booking b
               LEFT JOIN package p ON b.package_id=p.package_id
               LEFT JOIN traveler t ON b.adharno=t.adharno
               WHERE b.booking_id=%s AND b.adharno=%s""",
            (id, session["user_id"]), one=True
        )
        if not b:
            flash("Receipt not found.", "danger")
            return redirect("/my_bookings")
        return render_template("receipt.html", b=b)
    except Exception as e:
        flash(f"Could not load receipt: {e}", "danger")
        return redirect("/my_bookings")


# ══════════════════════════════════════════════════════
#  USER — REVIEWS
# ══════════════════════════════════════════════════════

@app.route("/add_review")
@login_required
def add_review():
    try:
        bookings = query(
            """SELECT b.booking_id, b.total_amount, b.status, p.category
               FROM booking b
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE b.adharno=%s AND b.status='Approved'""",
            (session["user_id"],)
        ) or []
        return render_template("add_review.html", bookings=bookings)
    except Exception as e:
        flash(f"Could not load bookings: {e}", "danger")
        return render_template("add_review.html", bookings=[])


@app.route("/save_review", methods=["POST"])
@login_required
def save_review():
    booking_id = request.form.get("booking_id", "").strip()
    rating     = request.form.get("rating", "").strip()
    comment    = request.form.get("review", "").strip()

    if not booking_id or not rating:
        flash("Please select a booking and a rating.", "warning")
        return redirect("/add_review")

    try:
        own = query(
            "SELECT booking_id FROM booking WHERE booking_id=%s AND adharno=%s AND status='Approved'",
            (booking_id, session["user_id"]), one=True
        )
        if not own:
            flash("Invalid booking selection.", "danger")
            return redirect("/add_review")

        dup = query("SELECT review_id FROM review WHERE booking_id=%s", (booking_id,), one=True)
        if dup:
            flash("You have already reviewed this booking.", "warning")
            return redirect("/my_reviews")

        query(
            "INSERT INTO review(booking_id, adharno, rating, comment) VALUES(%s,%s,%s,%s)",
            (booking_id, session["user_id"], rating, comment), commit=True
        )
        flash("Review submitted! Thank you.", "success")
        return redirect("/my_reviews")
    except Exception as e:
        flash(f"Could not save review: {e}", "danger")
        return redirect("/add_review")


@app.route("/my_reviews")
@login_required
def my_reviews():
    try:
        reviews = query(
            """SELECT r.*, p.category
               FROM review r
               LEFT JOIN booking b ON r.booking_id=b.booking_id
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE r.adharno=%s ORDER BY r.review_id DESC""",
            (session["user_id"],)
        ) or []
        return render_template("my_reviews.html", reviews=reviews)
    except Exception as e:
        flash(f"Could not load reviews: {e}", "danger")
        return render_template("my_reviews.html", reviews=[])


# ══════════════════════════════════════════════════════
#  USER — STATIC PAGES
# ══════════════════════════════════════════════════════

@app.route("/contact")
@login_required
def contact():
    return render_template("contact.html")


@app.route("/faq")
@login_required
def faq():
    return render_template("faq.html")


# ══════════════════════════════════════════════════════
#  ADMIN — DASHBOARD
# ══════════════════════════════════════════════════════

@app.route("/admin_dashboard")
@admin_required
def admin_dashboard():
    try:
        users          = int((query("SELECT COUNT(*) AS c FROM traveler", one=True) or {}).get("c", 0))
        bookings       = int((query("SELECT COUNT(*) AS c FROM booking", one=True) or {}).get("c", 0))
        approved       = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Approved'", one=True) or {}).get("c", 0))
        pending_count  = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Booked'", one=True) or {}).get("c", 0))
        cancelled      = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Cancelled'", one=True) or {}).get("c", 0))
        total_packages = int((query("SELECT COUNT(*) AS c FROM package", one=True) or {}).get("c", 0))
        rev_row        = query("SELECT COALESCE(SUM(total_amount),0) AS r FROM booking WHERE status='Approved'", one=True)
        revenue        = int(rev_row["r"]) if rev_row else 0

        recent_bookings = query(
            """SELECT b.*, t.name AS traveler_name, p.category
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY b.booking_id DESC LIMIT 6"""
        ) or []

        recent_reviews = query(
            """SELECT r.*, t.name AS traveler_name, p.category
               FROM review r
               LEFT JOIN traveler t ON r.adharno=t.adharno
               LEFT JOIN booking b ON r.booking_id=b.booking_id
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY r.review_id DESC LIMIT 5"""
        ) or []

        top_packages = query(
            """SELECT p.category, COUNT(b.booking_id) AS total
               FROM booking b JOIN package p ON b.package_id=p.package_id
               GROUP BY p.package_id, p.category ORDER BY total DESC LIMIT 3"""
        ) or []

        return render_template("admin_dashboard.html",
            users=users, bookings=bookings, approved=approved,
            pending_count=pending_count, cancelled=cancelled,
            total_packages=total_packages, revenue=revenue,
            recent_bookings=recent_bookings,
            recent_reviews=recent_reviews,
            top_packages=top_packages
        )
    except Exception as e:
        flash(f"Dashboard error: {e}", "danger")
        return render_template("admin_dashboard.html",
            users=0, bookings=0, approved=0, pending_count=0, cancelled=0,
            total_packages=0, revenue=0,
            recent_bookings=[], recent_reviews=[], top_packages=[])


# ══════════════════════════════════════════════════════
#  ADMIN — PACKAGES
# ══════════════════════════════════════════════════════

@app.route("/manage_packages")
@admin_required
def manage_packages():
    try:
        data = query(
            """SELECT p.*, pi.image
               FROM package p
               LEFT JOIN package_images pi ON p.package_id=pi.package_id
               ORDER BY p.package_id"""
        ) or []
        packages_dict = {}
        for row in data:
            pid = row["package_id"]
            if pid not in packages_dict:
                packages_dict[pid] = dict(row)
                packages_dict[pid]["images"] = []
            if row.get("image"):
                packages_dict[pid]["images"].append(row["image"])
        return render_template("manage_packages.html", packages=list(packages_dict.values()))
    except Exception as e:
        flash(f"Could not load packages: {e}", "danger")
        return render_template("manage_packages.html", packages=[])


@app.route("/add_package", methods=["POST"])
@admin_required
def add_package():
    category    = request.form.get("category", "").strip()
    amt_rate    = request.form.get("amt_rate", "").strip()
    description = request.form.get("description", "").strip()
    duration    = request.form.get("duration", "").strip()

    if not all([category, amt_rate, duration]):
        flash("Category, price, and duration are required.", "warning")
        return redirect("/manage_packages")

    try:
        float(amt_rate)
    except ValueError:
        flash("Price must be a valid number.", "danger")
        return redirect("/manage_packages")

    try:
        pkg_id = query(
            "INSERT INTO package(category, amt_rate, description, duration) VALUES(%s,%s,%s,%s)",
            (category, amt_rate, description, duration), commit=True
        )
        for file in request.files.getlist("images"):
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                query("INSERT INTO package_images(package_id, image) VALUES(%s,%s)",
                      (pkg_id, filename), commit=True)
        flash("Package added successfully.", "success")
    except Exception as e:
        flash(f"Could not add package: {e}", "danger")
    return redirect("/manage_packages")


@app.route("/edit_package/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_package(id):
    try:
        if request.method == "POST":
            category    = request.form.get("category", "").strip()
            amt_rate    = request.form.get("amt_rate", "").strip()
            description = request.form.get("description", "").strip()
            duration    = request.form.get("duration", "").strip()
            query(
                "UPDATE package SET category=%s, amt_rate=%s, description=%s, duration=%s WHERE package_id=%s",
                (category, amt_rate, description, duration, id), commit=True
            )
            flash("Package updated.", "success")
            return redirect("/manage_packages")

        pkg = query("SELECT * FROM package WHERE package_id=%s", (id,), one=True)
        if not pkg:
            flash("Package not found.", "danger")
            return redirect("/manage_packages")
        return render_template("edit_package.html", pkg=pkg)
    except Exception as e:
        flash(f"Could not edit package: {e}", "danger")
        return redirect("/manage_packages")


@app.route("/delete_package/<int:id>")
@admin_required
def delete_package(id):
    try:
        query("DELETE FROM wishlist WHERE package_id=%s", (id,), commit=True)
        query("DELETE FROM package_images WHERE package_id=%s", (id,), commit=True)
        bks = query("SELECT booking_id FROM booking WHERE package_id=%s", (id,)) or []
        for b in bks:
            query("DELETE FROM review WHERE booking_id=%s", (b["booking_id"],), commit=True)
        query("DELETE FROM booking WHERE package_id=%s", (id,), commit=True)
        query("DELETE FROM package WHERE package_id=%s", (id,), commit=True)
        flash("Package deleted.", "info")
    except Exception as e:
        flash(f"Could not delete package: {e}", "danger")
    return redirect("/manage_packages")


# ══════════════════════════════════════════════════════
#  ADMIN — BOOKINGS
# ══════════════════════════════════════════════════════

@app.route("/view_bookings")
@admin_required
def view_bookings():
    try:
        bookings = query(
            """SELECT b.*, t.name AS traveler_name, p.category
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY b.booking_id DESC"""
        ) or []
        return render_template("view_bookings.html", bookings=bookings)
    except Exception as e:
        flash(f"Could not load bookings: {e}", "danger")
        return render_template("view_bookings.html", bookings=[])


@app.route("/update_booking/<int:id>/<status>")
@admin_required
def update_booking(id, status):
    if status not in ("Approved", "Cancelled", "Rejected", "Booked"):
        flash("Invalid status.", "danger")
        return redirect("/view_bookings")
    try:
        bk = query("SELECT adharno, package_id FROM booking WHERE booking_id=%s", (id,), one=True)
        query("UPDATE booking SET status=%s WHERE booking_id=%s", (status, id), commit=True)
        if bk:
            pkg = query("SELECT category FROM package WHERE package_id=%s", (bk["package_id"],), one=True)
            pkg_name = pkg["category"] if pkg else "your package"
            msgs = {
                "Approved":  f"Your booking for '{pkg_name}' has been APPROVED! Get ready to travel.",
                "Rejected":  f"Your booking for '{pkg_name}' was rejected. Please contact support.",
                "Cancelled": f"Your booking for '{pkg_name}' was cancelled by admin."
            }
            if status in msgs:
                notify(bk["adharno"], msgs[status])
        flash(f"Booking #{id} marked as {status}.", "success")
    except Exception as e:
        flash(f"Could not update booking: {e}", "danger")
    return redirect("/view_bookings")


@app.route("/add_booking_note/<int:id>", methods=["POST"])
@admin_required
def add_booking_note(id):
    note = request.form.get("note", "").strip()
    if not note:
        flash("Note cannot be empty.", "warning")
        return redirect("/view_bookings")
    try:
        query("UPDATE booking SET admin_note=%s WHERE booking_id=%s", (note, id), commit=True)
        flash(f"Note added to booking #{id}.", "success")
    except Exception as e:
        flash(f"Could not add note: {e}", "danger")
    return redirect("/view_bookings")


@app.route("/export_bookings")
@admin_required
def export_bookings():
    try:
        rows = query(
            """SELECT b.booking_id, t.name AS traveler, b.adharno, p.category,
                      b.travel_date, b.total_amount, b.status,
                      COALESCE(b.admin_note,'') AS admin_note
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY b.booking_id DESC"""
        ) or []
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Booking ID","Traveler","Aadhaar","Package","Travel Date","Amount","Status","Admin Note"])
        for r in rows:
            writer.writerow([r["booking_id"], r["traveler"], r["adharno"],
                             r["category"], r["travel_date"], r["total_amount"],
                             r["status"], r["admin_note"]])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=bookings.csv"})
    except Exception as e:
        flash(f"Export failed: {e}", "danger")
        return redirect("/view_bookings")


@app.route("/export_travelers")
@admin_required
def export_travelers():
    try:
        rows = query(
            """SELECT t.adharno, t.name, t.mobile, t.address,
                      COUNT(b.booking_id) AS total_bookings,
                      COALESCE(SUM(b.total_amount),0) AS total_spent
               FROM traveler t
               LEFT JOIN booking b ON t.adharno=b.adharno
               GROUP BY t.adharno, t.name, t.mobile, t.address
               ORDER BY t.name"""
        ) or []
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Aadhaar","Name","Mobile","Address","Total Bookings","Total Spent"])
        for r in rows:
            writer.writerow([r["adharno"], r["name"], r["mobile"],
                             r["address"], r["total_bookings"], int(r["total_spent"])])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=travelers.csv"})
    except Exception as e:
        flash(f"Export failed: {e}", "danger")
        return redirect("/manage_travelers")


# ══════════════════════════════════════════════════════
#  ADMIN — REVIEWS
# ══════════════════════════════════════════════════════

@app.route("/view_reviews")
@admin_required
def view_reviews():
    try:
        reviews = query(
            """SELECT r.*, t.name AS traveler_name, p.category
               FROM review r
               LEFT JOIN traveler t ON r.adharno=t.adharno
               LEFT JOIN booking b ON r.booking_id=b.booking_id
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY r.review_id DESC"""
        ) or []
        return render_template("view_reviews.html", reviews=reviews)
    except Exception as e:
        flash(f"Could not load reviews: {e}", "danger")
        return render_template("view_reviews.html", reviews=[])


@app.route("/delete_review/<int:id>")
@admin_required
def delete_review(id):
    try:
        query("DELETE FROM review WHERE review_id=%s", (id,), commit=True)
        flash("Review deleted.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/view_reviews")


# ══════════════════════════════════════════════════════
#  ADMIN — TRAVELERS
# ══════════════════════════════════════════════════════

@app.route("/manage_travelers")
@admin_required
def manage_travelers():
    try:
        travelers = query(
            """SELECT t.adharno, t.name, t.mobile, t.address,
                      COUNT(b.booking_id) AS booking_count
               FROM traveler t
               LEFT JOIN booking b ON t.adharno=b.adharno
               GROUP BY t.adharno, t.name, t.mobile, t.address
               ORDER BY t.name"""
        ) or []
        return render_template("manage_travelers.html", travelers=travelers)
    except Exception as e:
        flash(f"Could not load travelers: {e}", "danger")
        return render_template("manage_travelers.html", travelers=[])


@app.route("/delete_traveler/<adharno>")
@admin_required
def delete_traveler(adharno):
    try:
        bks = query("SELECT booking_id FROM booking WHERE adharno=%s", (adharno,)) or []
        for b in bks:
            query("DELETE FROM review WHERE booking_id=%s", (b["booking_id"],), commit=True)
        query("DELETE FROM notification WHERE adharno=%s", (adharno,), commit=True)
        query("DELETE FROM wishlist WHERE adharno=%s", (adharno,), commit=True)
        query("DELETE FROM booking WHERE adharno=%s", (adharno,), commit=True)
        query("DELETE FROM traveler WHERE adharno=%s", (adharno,), commit=True)
        flash("Traveler deleted.", "info")
    except Exception as e:
        flash(f"Could not delete traveler: {e}", "danger")
    return redirect("/manage_travelers")


# ══════════════════════════════════════════════════════
#  ADMIN — ANNOUNCEMENTS
# ══════════════════════════════════════════════════════

@app.route("/announcements")
@admin_required
def announcements():
    try:
        all_ann = query("SELECT * FROM announcement ORDER BY created_at DESC") or []
        return render_template("announcements.html", announcements=all_ann)
    except Exception as e:
        flash(f"Could not load announcements: {e}", "danger")
        return render_template("announcements.html", announcements=[])


@app.route("/add_announcement", methods=["POST"])
@admin_required
def add_announcement():
    title   = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    if not title or not message:
        flash("Title and message are required.", "warning")
        return redirect("/announcements")
    try:
        query("INSERT INTO announcement(title, message) VALUES(%s,%s)",
              (title, message), commit=True)
        flash("Announcement posted.", "success")
    except Exception as e:
        flash(f"Could not post: {e}", "danger")
    return redirect("/announcements")


@app.route("/delete_announcement/<int:id>")
@admin_required
def delete_announcement(id):
    try:
        query("DELETE FROM announcement WHERE id=%s", (id,), commit=True)
        flash("Announcement deleted.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/announcements")


# ══════════════════════════════════════════════════════
#  ADMIN — STATISTICS
# ══════════════════════════════════════════════════════

@app.route("/stats")
@admin_required
def stats():
    try:
        users          = int((query("SELECT COUNT(*) AS c FROM traveler", one=True) or {}).get("c", 0))
        bookings       = int((query("SELECT COUNT(*) AS c FROM booking", one=True) or {}).get("c", 0))
        approved       = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Approved'", one=True) or {}).get("c", 0))
        cancelled      = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Cancelled'", one=True) or {}).get("c", 0))
        rejected       = int((query("SELECT COUNT(*) AS c FROM booking WHERE status='Rejected'", one=True) or {}).get("c", 0))
        total_packages = int((query("SELECT COUNT(*) AS c FROM package", one=True) or {}).get("c", 0))
        rev_row        = query("SELECT COALESCE(SUM(total_amount),0) AS r FROM booking WHERE status='Approved'", one=True)
        revenue        = int(rev_row["r"]) if rev_row else 0

        top_packages = query(
            """SELECT p.category, COUNT(b.booking_id) AS total,
                      COALESCE(SUM(b.total_amount),0) AS revenue
               FROM booking b JOIN package p ON b.package_id=p.package_id
               WHERE b.status='Approved'
               GROUP BY p.package_id, p.category ORDER BY total DESC LIMIT 5"""
        ) or []

        return render_template("stats.html",
            users=users, bookings=bookings, approved=approved,
            cancelled=cancelled, rejected=rejected,
            revenue=revenue, total_packages=total_packages,
            top_packages=top_packages
        )
    except Exception as e:
        flash(f"Could not load stats: {e}", "danger")
        return redirect("/admin_dashboard")


# ══════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)