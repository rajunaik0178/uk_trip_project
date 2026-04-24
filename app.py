from flask import Flask, render_template, request, redirect, session, flash, Response, g, jsonify
import mysql.connector
import os, csv, io, datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import random
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "uktrip_secret_2024")

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ══════════════════════════════════════════════════════
#  DATABASE
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
def send_email_otp(to_email, otp):
    sender_email = "rajunaik0178@gmail.com"
    sender_password = "dqkf fsnx seli rxvy"

    subject = "UK Trip Password Reset OTP"
    body = f"Your OTP for password reset is: {otp}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("Email Error:", e)
        return False

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_video(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS


def is_hashed(pw):
    return pw and (pw.startswith("pbkdf2:") or pw.startswith("scrypt:"))


def verify_password(stored_password, provided_password):
    if not stored_password or not provided_password:
        return False
    if is_hashed(stored_password):
        try:
            return check_password_hash(stored_password, provided_password)
        except Exception:
            return False
    return stored_password.strip() == provided_password.strip()


# ══════════════════════════════════════════════════════
#  AUTO CREATE ALL TABLES ON STARTUP
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
        """CREATE TABLE IF NOT EXISTS package_videos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            package_id INT NOT NULL,
            video VARCHAR(255) NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS trip_guide (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            destination VARCHAR(100) NOT NULL,
            duration_days INT DEFAULT 1,
            summary TEXT,
            itinerary TEXT,
            tips TEXT,
            cover_image VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS transport (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vehicle_type VARCHAR(100) NOT NULL,
            vehicle_number VARCHAR(50),
            driver_name VARCHAR(100),
            driver_mobile VARCHAR(15),
            capacity INT DEFAULT 4,
            status ENUM('Available','On Trip','Maintenance') DEFAULT 'Available',
            assigned_booking_id INT DEFAULT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS payment (
            id INT AUTO_INCREMENT PRIMARY KEY,
            booking_id INT NOT NULL,
            adharno VARCHAR(20) NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            payment_mode ENUM('Cash','UPI','Card','Bank Transfer','Other') DEFAULT 'Cash',
            payment_status ENUM('Pending','Paid','Failed','Refunded') DEFAULT 'Pending',
            transaction_id VARCHAR(100),
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS guide (
            guide_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            mobile VARCHAR(15),
            email VARCHAR(150),
            specialization VARCHAR(200),
            experience_years INT DEFAULT 0,
            languages VARCHAR(200),
            status ENUM('Available','Assigned','On Leave') DEFAULT 'Available',
            assigned_booking_id INT DEFAULT NULL,
            rating DECIMAL(3,1) DEFAULT 0,
            notes TEXT,
            guide_fee DECIMAL(10,2) DEFAULT NULL,
            fee_paid TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS contact_query (
            id INT AUTO_INCREMENT PRIMARY KEY,
            adharno VARCHAR(20),
            name VARCHAR(150) NOT NULL,
            subject VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            is_read TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    ]

    alters = [
        "ALTER TABLE booking ADD COLUMN IF NOT EXISTS admin_note TEXT DEFAULT NULL",
        "ALTER TABLE guide ADD COLUMN IF NOT EXISTS guide_fee DECIMAL(10,2) DEFAULT NULL",
        "ALTER TABLE guide ADD COLUMN IF NOT EXISTS fee_paid TINYINT DEFAULT 0",
    ]

    try:
        conn = mysql.connector.connect(
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
        for a in alters:
            try:
                cursor.execute(a)
                conn.commit()
            except Exception:
                pass
        cursor.close()
        conn.close()
    except Exception:
        pass


with app.app_context():
    create_new_tables()


# ══════════════════════════════════════════════════════
#  TEMPLATE GLOBALS
# ══════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    notif_count          = 0
    pending_admin        = 0
    announcements        = []
    wishlist_count       = 0
    unread_queries_count = 0

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

            uqrow = query(
                "SELECT COUNT(*) AS cnt FROM contact_query WHERE is_read=0", one=True
            )
            unread_queries_count = int(uqrow["cnt"]) if uqrow and uqrow.get("cnt") else 0

        ann = query("SELECT * FROM announcement ORDER BY created_at DESC LIMIT 3")
        announcements = ann if ann else []

    except Exception:
        pass

    return dict(
        notif_count=notif_count,
        pending_admin=pending_admin,
        announcements=announcements,
        wishlist_count=wishlist_count,
        unread_queries_count=unread_queries_count,
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
    def decorated_function(*args, **kwargs):
        if "admin" not in session:
            flash("Please login first.", "warning")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated_function


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
            if admin and str(admin["password"]).strip() == password.strip():
                session.clear()
                session["admin"] = admin["name"]
                flash("Admin login successful!", "success")
                return redirect("/admin_dashboard")
            flash("Invalid admin credentials.", "danger")
            return redirect("/")

        user = query("SELECT * FROM traveler WHERE name=%s", (username,), one=True)
        if user and verify_password(user["password"], password):
            if not is_hashed(user["password"]):
                query(
                    "UPDATE traveler SET password=%s WHERE adharno=%s",
                    (generate_password_hash(password), user["adharno"]), commit=True
                )
            session.clear()
            session["user"]    = user["name"]
            session["user_id"] = user["adharno"]
            flash("Login successful!", "success")
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
    email    = request.form.get("email", "").strip()
    mobile   = request.form.get("mobile", "").strip()
    password = request.form.get("password", "")

    if not all([adhar, name, address, email, mobile, password]):
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
        existing = query(
            "SELECT adharno FROM traveler WHERE adharno=%s",
            (adhar,),
            one=True
        )

        if existing:
            flash("This Aadhaar number is already registered.", "warning")
            return redirect("/register")

        hashed = generate_password_hash(password)

        query(
            "INSERT INTO traveler (adharno, name, address, email, mobile, password) VALUES (%s, %s, %s, %s, %s, %s)",
            (adhar, name, address, email, mobile, hashed),
            commit=True
        )

        flash("Registration successful! Please log in.", "success")
        return redirect("/")

    except Exception as e:
        flash(f"Registration failed: {e}", "danger")
        return redirect("/register")
@app.route("/forgot_password")
def forgot_password():
    return render_template("forgot_password.html")


@app.route("/send_otp", methods=["GET", "POST"])
def send_otp():
    email = request.form.get("email", "").strip()

    user = query(
        "SELECT * FROM traveler WHERE email=%s",
        (email,),
        one=True
    )

    if not user:
        flash("Email not found.", "danger")
        return redirect("/forgot_password")

    otp = str(random.randint(100000, 999999))

    session["reset_email"] = email
    session["reset_otp"] = otp

    if send_email_otp(email, otp):
        flash("OTP sent to your email.", "success")
        return redirect("/verify_otp")

    flash("Failed to send OTP.", "danger")
    return redirect("/forgot_password")


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    return render_template("verify_otp.html")


@app.route("/check_otp", methods=["POST"])
def check_otp():
    user_otp = request.form.get("otp", "").strip()

    if user_otp == session.get("reset_otp"):
        flash("OTP verified successfully.", "success")
        return redirect("/reset_password")

    flash("Invalid OTP.", "danger")
    return redirect("/verify_otp")


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    return render_template("reset_password.html")



@app.route("/update_password", methods=["POST"])
def update_password():
    new_password = request.form.get("password", "").strip()
    email = session.get("reset_email")

    if not email:
        flash("Session expired. Try again.", "danger")
        return redirect("/forgot_password")

    if len(new_password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect("/reset_password")

    hashed_password = generate_password_hash(new_password)

    query(
        "UPDATE traveler SET password=%s WHERE email=%s",
        (hashed_password, email),
        commit=True
    )

    session.pop("reset_email", None)
    session.pop("reset_otp", None)

    flash("Password updated successfully. Please login.", "success")
    return redirect("/")
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
               FROM booking b LEFT JOIN package p ON b.package_id=p.package_id
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
            if not row or not verify_password(row.get("password", ""), cur_pw):
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


@app.route("/wishlist/toggle/<int:pid>")
@login_required
def wishlist_toggle(pid):
    try:
        existing = query(
            "SELECT id FROM wishlist WHERE adharno=%s AND package_id=%s",
            (session["user_id"], pid), one=True
        )
        if existing:
            query("DELETE FROM wishlist WHERE adharno=%s AND package_id=%s",
                  (session["user_id"], pid), commit=True)
            in_wishlist = False
        else:
            query("INSERT INTO wishlist (adharno, package_id) VALUES (%s,%s)",
                  (session["user_id"], pid), commit=True)
            in_wishlist = True

        count_row = query(
            "SELECT COUNT(*) AS cnt FROM wishlist WHERE adharno=%s",
            (session["user_id"],), one=True
        )
        count = int(count_row["cnt"]) if count_row and count_row.get("cnt") else 0
        return jsonify({"ok": True, "in_wishlist": in_wishlist, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
                packages_dict[pid]["videos"] = []
            if row.get("image"):
                packages_dict[pid]["images"].append(row["image"])

        vid_rows = query("SELECT package_id, video FROM package_videos ORDER BY package_id") or []
        for vr in vid_rows:
            pid = vr["package_id"]
            if pid in packages_dict:
                packages_dict[pid]["videos"].append(vr["video"])

        wl_rows = query(
            "SELECT package_id FROM wishlist WHERE adharno=%s", (session["user_id"],)
        ) or []
        wishlist_ids = {r["package_id"] for r in wl_rows}

        ratings = query(
            """SELECT b.package_id, AVG(r.rating) AS avg_rating, COUNT(r.review_id) AS review_count
               FROM review r JOIN booking b ON r.booking_id=b.booking_id
               GROUP BY b.package_id"""
        ) or []
        rating_map = {r["package_id"]: r for r in ratings}

        pkg_list = list(packages_dict.values())
        for p in pkg_list:
            p["in_wishlist"]  = p["package_id"] in wishlist_ids
            rd = rating_map.get(p["package_id"])
            p["avg_rating"]   = round(float(rd["avg_rating"]), 1) if rd else None
            p["review_count"] = rd["review_count"] if rd else 0

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
               f"Your booking for '{pkg['category']}' (₹{pkg['amt_rate']}) is pending approval.")
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
        return render_template("reciept.html", b=b)
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
#  USER — CONTACT US  (saves to DB)
# ══════════════════════════════════════════════════════

@app.route("/contact")
@login_required
def contact():
    return render_template("contact.html")


@app.route("/contact_submit", methods=["POST"])
@login_required
def contact_submit():
    name    = session.get("user", "").strip()
    adharno = session.get("user_id", "")
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not subject or not message:
        flash("Subject and message are required.", "warning")
        return redirect("/contact")

    try:
        query(
            "INSERT INTO contact_query (adharno, name, subject, message) VALUES (%s,%s,%s,%s)",
            (adharno, name, subject, message), commit=True
        )
        flash("✅ Your message has been sent! Our team will get back to you within 24 hours.", "success")
    except Exception as e:
        flash(f"Could not send message: {e}", "danger")
    return redirect("/contact")


# ══════════════════════════════════════════════════════
#  USER — FAQ
# ══════════════════════════════════════════════════════

@app.route("/faq")
@login_required
def faq():
    return render_template("faq.html")


# ══════════════════════════════════════════════════════
#  USER — TRIP GUIDES  (view guides created by admin)
# ══════════════════════════════════════════════════════

@app.route("/guides")
@login_required
def guides():
    try:
        all_guides = query(
            "SELECT * FROM trip_guide ORDER BY created_at DESC"
        ) or []
        destinations = list({g["destination"] for g in all_guides if g.get("destination")})
        destinations.sort()
        return render_template("guides.html", guides=all_guides, destinations=destinations)
    except Exception as e:
        flash(f"Could not load trip guides: {e}", "danger")
        return render_template("guides.html", guides=[], destinations=[])


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

        unread_queries_count = int((query(
            "SELECT COUNT(*) AS c FROM contact_query WHERE is_read=0", one=True
        ) or {}).get("c", 0))

        return render_template("admin_dashboard.html",
            users=users, bookings=bookings, approved=approved,
            pending_count=pending_count, cancelled=cancelled,
            total_packages=total_packages, revenue=revenue,
            recent_bookings=recent_bookings,
            recent_reviews=recent_reviews,
            top_packages=top_packages,
            unread_queries_count=unread_queries_count
        )
    except Exception as e:
        flash(f"Dashboard error: {e}", "danger")
        return render_template("admin_dashboard.html",
            users=0, bookings=0, approved=0, pending_count=0, cancelled=0,
            total_packages=0, revenue=0,
            recent_bookings=[], recent_reviews=[], top_packages=[],
            unread_queries_count=0)


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
               ORDER BY p.package_id DESC"""
        ) or []

        packages_dict = {}
        for row in data:
            pid = row["package_id"]
            if pid not in packages_dict:
                packages_dict[pid] = {
                    "package_id":  row["package_id"],
                    "category":    row["category"],
                    "amt_rate":    row["amt_rate"],
                    "description": row["description"],
                    "duration":    row["duration"],
                    "images":      [],
                    "videos":      []
                }
            if row.get("image"):
                packages_dict[pid]["images"].append(row["image"])

        video_rows = query("SELECT package_id, video FROM package_videos") or []
        for v in video_rows:
            pid = v["package_id"]
            if pid in packages_dict and v.get("video"):
                packages_dict[pid]["videos"].append(v["video"])

        package_data = {}
        for pid, pkg in packages_dict.items():
            package_data[str(pid)] = {
                "name":   pkg["category"],
                "images": pkg["images"],
                "videos": pkg["videos"]
            }

        return render_template("manage_packages.html",
            packages=list(packages_dict.values()),
            package_data=package_data)
    except Exception as e:
        flash(f"Could not load packages: {e}", "danger")
        return render_template("manage_packages.html", packages=[], package_data={})


@app.route("/edit_package/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_package(id):
    try:
        if request.method == "POST":
            query(
                "UPDATE package SET category=%s, amt_rate=%s, description=%s, duration=%s WHERE package_id=%s",
                (
                    request.form.get("category", "").strip(),
                    request.form.get("amt_rate", "").strip(),
                    request.form.get("description", "").strip(),
                    request.form.get("duration", "").strip(),
                    id
                ), commit=True
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
        query("DELETE FROM package_videos WHERE package_id=%s", (id,), commit=True)
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
#  ADMIN — MEDIA
# ══════════════════════════════════════════════════════

@app.route("/upload_media/<int:id>", methods=["GET", "POST"])
@admin_required
def upload_media(id):
    try:
        pkg = query("SELECT * FROM package WHERE package_id=%s", (id,), one=True)
        if not pkg:
            flash("Package not found.", "danger")
            return redirect("/manage_packages")

        if request.method == "POST":
            uploaded = 0
            for file in request.files.getlist("images"):
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    query("INSERT INTO package_images(package_id, image) VALUES(%s,%s)",
                          (id, filename), commit=True)
                    uploaded += 1
            for file in request.files.getlist("videos"):
                if file and file.filename and allowed_video(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    query("INSERT INTO package_videos(package_id, video) VALUES(%s,%s)",
                          (id, filename), commit=True)
                    uploaded += 1
            flash(f"{uploaded} file(s) uploaded successfully.", "success")
            return redirect(f"/upload_media/{id}")

        images = query("SELECT image FROM package_images WHERE package_id=%s", (id,)) or []
        videos = query("SELECT video FROM package_videos WHERE package_id=%s", (id,)) or []
        return render_template("upload_media.html", pkg=pkg, images=images, videos=videos)
    except Exception as e:
        flash(f"Could not load media page: {e}", "danger")
        return redirect("/manage_packages")


@app.route("/delete_media/<mtype>/<int:pkg_id>/<filename>")
@admin_required
def delete_media(mtype, pkg_id, filename):
    try:
        if mtype == "image":
            query("DELETE FROM package_images WHERE package_id=%s AND image=%s",
                  (pkg_id, filename), commit=True)
        elif mtype == "video":
            query("DELETE FROM package_videos WHERE package_id=%s AND video=%s",
                  (pkg_id, filename), commit=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        flash("Media deleted.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect(f"/upload_media/{pkg_id}")


@app.route("/manage_gallery")
@admin_required
def manage_gallery():
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
                packages_dict[pid]["videos"] = []
            if row.get("image"):
                packages_dict[pid]["images"].append(row["image"])
        vid_data = query(
            """SELECT p.package_id, pv.video
               FROM package p
               LEFT JOIN package_videos pv ON p.package_id=pv.package_id
               ORDER BY p.package_id"""
        ) or []
        for row in vid_data:
            pid = row["package_id"]
            if pid in packages_dict and row.get("video"):
                packages_dict[pid]["videos"].append(row["video"])
        return render_template("manage_gallery.html", packages=list(packages_dict.values()))
    except Exception as e:
        flash(f"Could not load gallery: {e}", "danger")
        return render_template("manage_gallery.html", packages=[])


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
                "Approved":  f"Your booking for '{pkg_name}' has been APPROVED! Get ready to travel. 🎉",
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
#  ADMIN — INVOICE (print/view single invoice)
# ══════════════════════════════════════════════════════

@app.route("/invoice/<int:id>")
@admin_required
def invoice(id):
    try:
        b = query(
            """SELECT b.*, t.name AS traveler_name, t.mobile, t.address, t.adharno,
                      p.category, p.duration, p.description,
                      COALESCE(pay_total.paid, 0) AS amount_paid,
                      (b.total_amount - COALESCE(pay_total.paid, 0)) AS balance_due
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               LEFT JOIN (
                   SELECT booking_id, SUM(amount) AS paid
                   FROM payment WHERE payment_status='Paid'
                   GROUP BY booking_id
               ) pay_total ON b.booking_id=pay_total.booking_id
               WHERE b.booking_id=%s""",
            (id,), one=True
        )
        if not b:
            flash("Invoice not found.", "danger")
            return redirect("/manage_invoices")

        payments = query(
            """SELECT * FROM payment WHERE booking_id=%s ORDER BY payment_date DESC""",
            (id,)
        ) or []

        auto_print = request.args.get("print") == "1"
        return render_template("invoice_view.html", b=b, payments=payments, auto_print=auto_print)
    except Exception as e:
        flash(f"Could not load invoice: {e}", "danger")
        return redirect("/manage_invoices")


# ══════════════════════════════════════════════════════
#  ADMIN — INVOICES LIST
# ══════════════════════════════════════════════════════

@app.route("/manage_invoices")
@admin_required
def manage_invoices():
    try:
        bookings = query(
            """SELECT b.*, t.name AS traveler_name, t.mobile, t.adharno,
                      p.category, p.duration,
                      COALESCE(pay_total.paid, 0) AS amount_paid,
                      (b.total_amount - COALESCE(pay_total.paid, 0)) AS balance_due
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               LEFT JOIN (
                   SELECT booking_id, SUM(amount) AS paid
                   FROM payment WHERE payment_status='Paid'
                   GROUP BY booking_id
               ) pay_total ON b.booking_id=pay_total.booking_id
               ORDER BY b.booking_id DESC"""
        ) or []

        payments = query(
            """SELECT pay.*, t.name AS traveler_name, p.category,
                      b.travel_date, b.total_amount AS booking_amount
               FROM payment pay
               LEFT JOIN booking b ON pay.booking_id=b.booking_id
               LEFT JOIN traveler t ON pay.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY pay.id DESC"""
        ) or []

        total_invoiced = float((query(
            "SELECT COALESCE(SUM(total_amount),0) AS s FROM booking", one=True) or {}).get("s", 0))
        total_paid = float((query(
            "SELECT COALESCE(SUM(amount),0) AS s FROM payment WHERE payment_status='Paid'",
            one=True) or {}).get("s", 0))
        outstanding = total_invoiced - total_paid

        return render_template("manage_invoices.html",
            bookings=bookings, payments=payments,
            total_invoiced=total_invoiced, total_paid=total_paid, outstanding=outstanding)
    except Exception as e:
        flash(f"Could not load invoices: {e}", "danger")
        return render_template("manage_invoices.html",
            bookings=[], payments=[], total_invoiced=0, total_paid=0, outstanding=0)


# ══════════════════════════════════════════════════════
#  ADMIN — PAYMENTS
# ══════════════════════════════════════════════════════

@app.route("/manage_payments")
@admin_required
def manage_payments():
    try:
        payments = query(
            """SELECT pay.*, t.name AS traveler_name, p.category,
                      b.travel_date, b.total_amount AS booking_amount
               FROM payment pay
               LEFT JOIN booking b ON pay.booking_id=b.booking_id
               LEFT JOIN traveler t ON pay.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY pay.id DESC"""
        ) or []

        bookings = query(
            """SELECT b.booking_id, t.name AS traveler_name, t.adharno,
                      p.category, b.total_amount, b.status
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY b.booking_id DESC"""
        ) or []

        total_collected = float((query(
            "SELECT COALESCE(SUM(amount),0) AS s FROM payment WHERE payment_status='Paid'",
            one=True) or {}).get("s", 0))
        pending_amount = float((query(
            "SELECT COALESCE(SUM(amount),0) AS s FROM payment WHERE payment_status='Pending'",
            one=True) or {}).get("s", 0))
        total_payments = int((query(
            "SELECT COUNT(*) AS c FROM payment", one=True) or {}).get("c", 0))
        paid_count = int((query(
            "SELECT COUNT(*) AS c FROM payment WHERE payment_status='Paid'",
            one=True) or {}).get("c", 0))

        return render_template("manage_payments.html",
            payments=payments, bookings=bookings,
            total_collected=total_collected, pending_amount=pending_amount,
            total_payments=total_payments, paid_count=paid_count)
    except Exception as e:
        flash(f"Could not load payments: {e}", "danger")
        return render_template("manage_payments.html",
            payments=[], bookings=[],
            total_collected=0, pending_amount=0,
            total_payments=0, paid_count=0)


@app.route("/add_payment", methods=["POST"])
@admin_required
def add_payment():
    try:
        booking_id     = request.form.get("booking_id", "").strip()
        amount         = request.form.get("amount", "0").strip()
        payment_mode   = request.form.get("payment_mode", "Cash").strip()
        payment_status = request.form.get("payment_status", "Paid").strip()
        transaction_id = request.form.get("transaction_id", "").strip()
        notes          = request.form.get("notes", "").strip()

        if not booking_id or not amount:
            flash("Booking and amount are required.", "warning")
            return redirect("/manage_payments")

        bk = query("SELECT adharno, package_id FROM booking WHERE booking_id=%s",
                   (booking_id,), one=True)
        if not bk:
            flash("Booking not found.", "danger")
            return redirect("/manage_payments")

        query(
            """INSERT INTO payment
               (booking_id, adharno, amount, payment_mode, payment_status, transaction_id, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (booking_id, bk["adharno"], float(amount),
             payment_mode, payment_status,
             transaction_id or None, notes or None),
            commit=True
        )

        if payment_status == "Paid":
            pkg = query("SELECT category FROM package WHERE package_id=%s",
                        (bk["package_id"],), one=True)
            pkg_name = pkg["category"] if pkg else "your booking"
            notify(bk["adharno"],
                   f"Payment of ₹{amount} received for '{pkg_name}'. Thank you!")

        flash(f"Payment of ₹{amount} recorded successfully.", "success")
    except Exception as e:
        flash(f"Could not record payment: {e}", "danger")
    return redirect("/manage_invoices")


@app.route("/update_payment_status/<int:id>/<status>")
@admin_required
def update_payment_status(id, status):
    if status not in ("Paid", "Pending", "Refunded", "Failed"):
        flash("Invalid payment status.", "danger")
        return redirect("/manage_payments")
    try:
        query("UPDATE payment SET payment_status=%s WHERE id=%s", (status, id), commit=True)
        flash(f"Payment #{id} updated to {status}.", "success")
    except Exception as e:
        flash(f"Could not update payment: {e}", "danger")
    return redirect("/manage_payments")


@app.route("/delete_payment/<int:id>")
@admin_required
def delete_payment(id):
    try:
        query("DELETE FROM payment WHERE id=%s", (id,), commit=True)
        flash("Payment record deleted.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/manage_payments")


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
            top_packages=top_packages)
    except Exception as e:
        flash(f"Could not load stats: {e}", "danger")
        return redirect("/admin_dashboard")


# ══════════════════════════════════════════════════════
#  ADMIN — TRIP GUIDES (admin create/edit/delete)
# ══════════════════════════════════════════════════════

@app.route("/manage_guides")
@admin_required
def manage_guides():
    try:
        all_guides = query("SELECT * FROM trip_guide ORDER BY id DESC") or []
        packages   = query("SELECT DISTINCT category FROM package ORDER BY category ASC") or []
        return render_template("manage_guides.html", guides=all_guides, packages=packages)
    except Exception as e:
        flash(f"Could not load guides: {e}", "danger")
        return render_template("manage_guides.html", guides=[], packages=[])


@app.route("/add_guide", methods=["POST"])
@admin_required
def add_guide():
    title         = request.form.get("title", "").strip()
    destination   = request.form.get("destination", "").strip()
    duration_days = request.form.get("duration_days", "0").strip()
    summary       = request.form.get("summary", "").strip()
    itinerary     = request.form.get("itinerary", "").strip()
    tips          = request.form.get("tips", "").strip()

    if not title or not destination:
        flash("Title and destination are required.", "warning")
        return redirect("/manage_guides")

    try:
        cover_image = None
        file = request.files.get("cover_image")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            cover_image = filename

        query(
            """INSERT INTO trip_guide
               (title, destination, duration_days, summary, itinerary, tips, cover_image)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (title, destination, duration_days, summary, itinerary, tips, cover_image),
            commit=True
        )
        flash("Guide added successfully.", "success")
    except Exception as e:
        flash(f"Could not add guide: {e}", "danger")
    return redirect("/manage_guides")


@app.route("/edit_guide/<int:id>", methods=["POST"])
@admin_required
def edit_guide(id):
    title         = request.form.get("title", "").strip()
    destination   = request.form.get("destination", "").strip()
    duration_days = request.form.get("duration_days", "0").strip()
    summary       = request.form.get("summary", "").strip()
    itinerary     = request.form.get("itinerary", "").strip()
    tips          = request.form.get("tips", "").strip()

    try:
        file = request.files.get("cover_image")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            query(
                """UPDATE trip_guide
                   SET title=%s, destination=%s, duration_days=%s,
                       summary=%s, itinerary=%s, tips=%s, cover_image=%s
                   WHERE id=%s""",
                (title, destination, duration_days, summary, itinerary, tips, filename, id),
                commit=True
            )
        else:
            query(
                """UPDATE trip_guide
                   SET title=%s, destination=%s, duration_days=%s,
                       summary=%s, itinerary=%s, tips=%s
                   WHERE id=%s""",
                (title, destination, duration_days, summary, itinerary, tips, id),
                commit=True
            )
        flash("Guide updated.", "success")
    except Exception as e:
        flash(f"Could not update guide: {e}", "danger")
    return redirect("/manage_guides")


@app.route("/delete_guide/<int:id>")
@admin_required
def delete_guide(id):
    try:
        query("DELETE FROM trip_guide WHERE id=%s", (id,), commit=True)
        flash("Guide deleted.", "info")
    except Exception as e:
        flash(f"Could not delete guide: {e}", "danger")
    return redirect("/manage_guides")


# ══════════════════════════════════════════════════════
#  ADMIN — TRANSPORT
# ══════════════════════════════════════════════════════

@app.route("/manage_transport")
@admin_required
def manage_transport():
    try:
        vehicles = query(
            """SELECT t.*, tr.name AS traveler_name, p.category
               FROM transport t
               LEFT JOIN booking b ON t.assigned_booking_id=b.booking_id
               LEFT JOIN traveler tr ON b.adharno=tr.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY t.id DESC"""
        ) or []

        bookings = query(
            """SELECT b.booking_id, t.name AS traveler_name, p.category, b.travel_date
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE b.status='Approved'
               ORDER BY b.travel_date ASC"""
        ) or []

        stats = {
            'total':       int((query("SELECT COUNT(*) AS c FROM transport", one=True) or {}).get("c", 0)),
            'available':   int((query("SELECT COUNT(*) AS c FROM transport WHERE status='Available'", one=True) or {}).get("c", 0)),
            'on_trip':     int((query("SELECT COUNT(*) AS c FROM transport WHERE status='On Trip'", one=True) or {}).get("c", 0)),
            'maintenance': int((query("SELECT COUNT(*) AS c FROM transport WHERE status='Maintenance'", one=True) or {}).get("c", 0)),
        }
        return render_template("manage_transport.html",
                               vehicles=vehicles, bookings=bookings, stats=stats)
    except Exception as e:
        flash(f"Could not load transport: {e}", "danger")
        return render_template("manage_transport.html", vehicles=[], bookings=[], stats={})


@app.route("/add_transport", methods=["POST"])
@admin_required
def add_transport():
    try:
        query(
            """INSERT INTO transport
               (vehicle_type, vehicle_number, driver_name, driver_mobile, capacity, status, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                request.form.get("vehicle_type", "").strip(),
                request.form.get("vehicle_number", "").strip().upper(),
                request.form.get("driver_name", "").strip(),
                request.form.get("driver_mobile", "").strip(),
                int(request.form.get("capacity", 4) or 4),
                request.form.get("initial_status", "Available"),
                request.form.get("notes", "").strip()
            ), commit=True
        )
        flash("Vehicle added to fleet.", "success")
    except Exception as e:
        flash(f"Could not add vehicle: {e}", "danger")
    return redirect("/manage_transport")


@app.route("/edit_transport/<int:id>", methods=["POST"])
@admin_required
def edit_transport(id):
    try:
        query(
            """UPDATE transport
               SET vehicle_type=%s, vehicle_number=%s, driver_name=%s,
                   driver_mobile=%s, capacity=%s, notes=%s
               WHERE id=%s""",
            (
                request.form.get("vehicle_type", "").strip(),
                request.form.get("vehicle_number", "").strip().upper(),
                request.form.get("driver_name", "").strip(),
                request.form.get("driver_mobile", "").strip(),
                int(request.form.get("capacity", 4) or 4),
                request.form.get("notes", "").strip(),
                id
            ), commit=True
        )
        flash("Vehicle details updated.", "success")
    except Exception as e:
        flash(f"Could not update vehicle: {e}", "danger")
    return redirect("/manage_transport")


@app.route("/update_transport/<int:id>", methods=["POST"])
@admin_required
def update_transport(id):
    try:
        status     = request.form.get("status", "Available")
        booking_id = request.form.get("assigned_booking_id") or None
        notes      = request.form.get("notes", "").strip()
        if status != "On Trip":
            booking_id = None
        query(
            "UPDATE transport SET status=%s, assigned_booking_id=%s, notes=%s WHERE id=%s",
            (status, booking_id, notes, id), commit=True
        )
        flash(f"Vehicle #{id} updated to {status}.", "success")
    except Exception as e:
        flash(f"Could not update: {e}", "danger")
    return redirect("/manage_transport")


@app.route("/delete_transport/<int:id>")
@admin_required
def delete_transport(id):
    try:
        query("DELETE FROM transport WHERE id=%s", (id,), commit=True)
        flash("Vehicle removed from fleet.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/manage_transport")


# ══════════════════════════════════════════════════════
#  ADMIN — TOUR GUIDES (staff guides, not trip_guide)
# ══════════════════════════════════════════════════════

@app.route("/manage_guides_admin")
@admin_required
def manage_guides_admin():
    try:
        guides = query(
            """SELECT g.*, t.name AS traveler_name, p.category
               FROM guide g
               LEFT JOIN booking b ON g.assigned_booking_id=b.booking_id
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               ORDER BY g.guide_id DESC"""
        ) or []

        bookings = query(
            """SELECT b.booking_id, t.name AS traveler_name, p.category, b.travel_date
               FROM booking b
               LEFT JOIN traveler t ON b.adharno=t.adharno
               LEFT JOIN package p ON b.package_id=p.package_id
               WHERE b.status='Approved'
               ORDER BY b.travel_date ASC"""
        ) or []

        stats = {
            'total':     int((query("SELECT COUNT(*) AS c FROM guide", one=True) or {}).get("c", 0)),
            'available': int((query("SELECT COUNT(*) AS c FROM guide WHERE status='Available'", one=True) or {}).get("c", 0)),
            'assigned':  int((query("SELECT COUNT(*) AS c FROM guide WHERE status='Assigned'", one=True) or {}).get("c", 0)),
            'on_leave':  int((query("SELECT COUNT(*) AS c FROM guide WHERE status='On Leave'", one=True) or {}).get("c", 0)),
        }

        fee_row = query(
            "SELECT COALESCE(SUM(guide_fee),0) AS s FROM guide WHERE fee_paid=0 AND guide_fee IS NOT NULL",
            one=True)
        total_guide_fees_due = float(fee_row["s"]) if fee_row else 0

        return render_template("manage_guides_admin.html",
            guides=guides, bookings=bookings,
            stats=stats, total_guide_fees_due=total_guide_fees_due)
    except Exception as e:
        flash(f"Could not load guides: {e}", "danger")
        return render_template("manage_guides_admin.html",
            guides=[], bookings=[], stats={}, total_guide_fees_due=0)


@app.route("/add_guide_admin", methods=["POST"])
@admin_required
def add_guide_admin():
    try:
        guide_fee_raw = request.form.get("guide_fee", "").strip()
        guide_fee     = float(guide_fee_raw) if guide_fee_raw else None
        query(
            """INSERT INTO guide
               (name, mobile, email, specialization, experience_years, languages,
                status, notes, guide_fee, fee_paid)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
            (
                request.form.get("name", "").strip(),
                request.form.get("mobile", "").strip(),
                request.form.get("email", "").strip(),
                request.form.get("specialization", "").strip(),
                int(request.form.get("experience_years", 0) or 0),
                request.form.get("languages", "").strip(),
                request.form.get("initial_status", "Available"),
                request.form.get("notes", "").strip(),
                guide_fee
            ), commit=True
        )
        flash("Guide registered successfully.", "success")
    except Exception as e:
        flash(f"Could not add guide: {e}", "danger")
    return redirect("/manage_guides_admin")


@app.route("/edit_guide_admin/<int:id>", methods=["POST"])
@admin_required
def edit_guide_admin(id):
    try:
        rating_raw = request.form.get("rating", "").strip()
        rating     = float(rating_raw) if rating_raw else None

        if rating is not None:
            query(
                """UPDATE guide
                   SET name=%s, mobile=%s, email=%s, specialization=%s,
                       experience_years=%s, languages=%s, notes=%s, rating=%s
                   WHERE guide_id=%s""",
                (
                    request.form.get("name", "").strip(),
                    request.form.get("mobile", "").strip(),
                    request.form.get("email", "").strip(),
                    request.form.get("specialization", "").strip(),
                    int(request.form.get("experience_years", 0) or 0),
                    request.form.get("languages", "").strip(),
                    request.form.get("notes", "").strip(),
                    rating, id
                ), commit=True
            )
        else:
            query(
                """UPDATE guide
                   SET name=%s, mobile=%s, email=%s, specialization=%s,
                       experience_years=%s, languages=%s, notes=%s
                   WHERE guide_id=%s""",
                (
                    request.form.get("name", "").strip(),
                    request.form.get("mobile", "").strip(),
                    request.form.get("email", "").strip(),
                    request.form.get("specialization", "").strip(),
                    int(request.form.get("experience_years", 0) or 0),
                    request.form.get("languages", "").strip(),
                    request.form.get("notes", "").strip(),
                    id
                ), commit=True
            )
        flash("Guide details updated.", "success")
    except Exception as e:
        flash(f"Could not update guide: {e}", "danger")
    return redirect("/manage_guides_admin")


@app.route("/update_guide_admin/<int:id>", methods=["POST"])
@admin_required
def update_guide_admin(id):
    try:
        status        = request.form.get("status", "Available")
        booking_id    = request.form.get("assigned_booking_id") or None
        notes         = request.form.get("notes", "").strip()
        guide_fee_raw = request.form.get("guide_fee", "").strip()
        guide_fee     = float(guide_fee_raw) if guide_fee_raw else None
        fee_paid      = int(request.form.get("fee_paid", 0))
        rating_raw    = request.form.get("rating", "").strip()
        rating        = float(rating_raw) if rating_raw else None

        if status != "Assigned":
            booking_id = None

        if rating is not None:
            query(
                """UPDATE guide
                   SET status=%s, assigned_booking_id=%s, notes=%s,
                       guide_fee=%s, fee_paid=%s, rating=%s
                   WHERE guide_id=%s""",
                (status, booking_id, notes, guide_fee, fee_paid, rating, id), commit=True
            )
        else:
            query(
                """UPDATE guide
                   SET status=%s, assigned_booking_id=%s, notes=%s,
                       guide_fee=%s, fee_paid=%s
                   WHERE guide_id=%s""",
                (status, booking_id, notes, guide_fee, fee_paid, id), commit=True
            )

        flash(f"Guide assignment updated to {status}.", "success")

        if status == "Assigned" and booking_id:
            bk = query("SELECT adharno FROM booking WHERE booking_id=%s", (booking_id,), one=True)
            g  = query("SELECT name FROM guide WHERE guide_id=%s", (id,), one=True)
            if bk and g:
                notify(bk["adharno"],
                       f"Your tour guide '{g['name']}' has been assigned to your upcoming trip. 🧭")

    except Exception as e:
        flash(f"Could not update guide: {e}", "danger")
    return redirect("/manage_guides_admin")


@app.route("/delete_guide_admin/<int:id>")
@admin_required
def delete_guide_admin(id):
    try:
        query("DELETE FROM guide WHERE guide_id=%s", (id,), commit=True)
        flash("Guide removed.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/manage_guides_admin")


# ══════════════════════════════════════════════════════
#  ADMIN — USER QUERIES / CONTACT MESSAGES
# ══════════════════════════════════════════════════════

@app.route("/admin_queries")
@admin_required
def admin_queries():
    try:
        queries_list = query(
            "SELECT * FROM contact_query ORDER BY is_read ASC, created_at DESC"
        ) or []
        return render_template("admin_queries.html", queries=queries_list)
    except Exception as e:
        flash(f"Could not load queries: {e}", "danger")
        return render_template("admin_queries.html", queries=[])


@app.route("/admin_query_read/<int:id>")
@admin_required
def admin_query_read(id):
    try:
        query("UPDATE contact_query SET is_read=1 WHERE id=%s", (id,), commit=True)
        flash("Message marked as read.", "success")
    except Exception as e:
        flash(f"Could not update: {e}", "danger")
    return redirect("/admin_queries")


@app.route("/admin_query_delete/<int:id>")
@admin_required
def admin_query_delete(id):
    try:
        query("DELETE FROM contact_query WHERE id=%s", (id,), commit=True)
        flash("Message deleted.", "info")
    except Exception as e:
        flash(f"Could not delete: {e}", "danger")
    return redirect("/admin_queries")


# ══════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)