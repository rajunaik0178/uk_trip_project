from flask import Flask, render_template, request, redirect, session
import mysql.connector
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="uk_trip"
    )


# HOME
@app.route("/")
def home():
    return render_template("login.html")


# LOGIN
@app.route("/login", methods=["POST"])
def login():

    role = request.form["role"]
    username = request.form["username"]
    password = request.form["password"]

    conn = db()
    cursor = conn.cursor()

    # ADMIN
    if role == "admin":
        cursor.execute(
            "SELECT * FROM admin WHERE name=%s AND password=%s",
            (username, password)
        )
        admin = cursor.fetchone()

        if admin:
            session["admin"] = admin[1]
            conn.close()
            return redirect("/admin_dashboard")

        conn.close()
        return "Invalid Admin Login"

    # USER
    cursor.execute(
        "SELECT * FROM traveler WHERE name=%s AND password=%s",
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        session["user"] = user[1]
        session["user_id"] = user[0]
        return redirect("/dashboard")

    return "Invalid User Login"


# REGISTER
@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/register_user", methods=["POST"])
def register_user():

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO traveler VALUES(%s,%s,%s,%s,%s)",
        (
            request.form["adhar"],
            request.form["name"],
            request.form["address"],
            request.form["mobile"],
            request.form["password"]
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")


# USER DASHBOARD
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html", user=session["user"])


# ===================== PACKAGES =====================

@app.route("/packages")
def packages():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.*, pi.image
    FROM package p
    LEFT JOIN package_images pi
    ON p.package_id = pi.package_id
    """)

    data = cursor.fetchall()

    packages = {}
    for row in data:
        pid = row["package_id"]

        if pid not in packages:
            packages[pid] = row
            packages[pid]["images"] = []

        if row["image"]:
            packages[pid]["images"].append(row["image"])

    packages = list(packages.values())

    conn.close()

    return render_template("packages.html", packages=packages)


# 🔥 VIEW ALL IMAGES (NEW)
@app.route("/view_images/<int:id>")
def view_images(id):

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT image FROM package_images WHERE package_id=%s",
        (id,)
    )

    images = cursor.fetchall()
    conn.close()

    return render_template("view_images.html", images=images)


# BOOK
@app.route("/book/<int:id>")
def book(id):

    if "user_id" not in session:
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM package WHERE package_id=%s", (id,))
    pkg = cursor.fetchone()

    cursor.execute(
        "INSERT INTO booking(adharno, package_id, travel_date, total_amount, status) VALUES(%s,%s,CURDATE(),%s,'Booked')",
        (session["user_id"], id, pkg["amt_rate"])
    )

    conn.commit()
    conn.close()

    return redirect("/my_bookings")


# MY BOOKINGS
@app.route("/my_bookings")
def my_bookings():

    if "user_id" not in session:
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM booking WHERE adharno=%s",
        (session["user_id"],)
    )

    bookings = cursor.fetchall()

    conn.close()

    return render_template("my_bookings.html", bookings=bookings)


# BOOKING ACTIONS
@app.route("/cancel/<int:id>")
def cancel(id):
    conn = db()
    cursor = conn.cursor()
    cursor.execute("UPDATE booking SET status='Cancelled' WHERE booking_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect("/my_bookings")


@app.route("/approve/<int:id>")
def approve(id):
    conn = db()
    cursor = conn.cursor()
    cursor.execute("UPDATE booking SET status='Approved' WHERE booking_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect("/my_bookings")


@app.route("/reject/<int:id>")
def reject(id):
    conn = db()
    cursor = conn.cursor()
    cursor.execute("UPDATE booking SET status='Rejected' WHERE booking_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect("/my_bookings")


# ===================== REVIEW =====================

@app.route("/add_review")
def add_review():

    if "user_id" not in session:
        return redirect("/")

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM booking WHERE adharno=%s",
        (session["user_id"],)
    )

    bookings = cursor.fetchall()
    conn.close()

    return render_template("add_review.html", bookings=bookings)


@app.route("/save_review", methods=["POST"])
def save_review():

    if "user_id" not in session:
        return redirect("/")

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO review(booking_id, adharno, rating, comment) VALUES(%s,%s,%s,%s)",
        (
            request.form["booking_id"],
            session["user_id"],
            request.form["rating"],
            request.form["review"]
        )
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ===================== ADMIN =====================

@app.route("/admin_dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect("/")
    return render_template("admin_dashboard.html")


@app.route("/manage_packages")
def manage_packages():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM package")
    packages = cursor.fetchall()

    conn.close()

    return render_template("manage_packages.html", packages=packages)


# MULTIPLE IMAGE UPLOAD
@app.route("/add_package", methods=["POST"])
def add_package():

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO package(category, amt_rate, description, duration) VALUES(%s,%s,%s,%s)",
        (
            request.form["category"],
            request.form["amt_rate"],
            request.form["description"],
            request.form["duration"]
        )
    )

    package_id = cursor.lastrowid

    files = request.files.getlist("images")

    for file in files:
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            cursor.execute(
                "INSERT INTO package_images(package_id, image) VALUES(%s,%s)",
                (package_id, filename)
            )

    conn.commit()
    conn.close()

    return redirect("/manage_packages")


@app.route("/delete_package/<int:id>")
def delete_package(id):
    conn = db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM package WHERE package_id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect("/manage_packages")


@app.route("/view_bookings")
def view_bookings():
    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM booking")
    bookings = cursor.fetchall()
    conn.close()
    return render_template("view_bookings.html", bookings=bookings)


@app.route("/update_booking/<int:id>/<status>")
def update_booking(id, status):
    conn = db()
    cursor = conn.cursor()
    cursor.execute("UPDATE booking SET status=%s WHERE booking_id=%s", (status, id))
    conn.commit()
    conn.close()
    return redirect("/view_bookings")


@app.route("/view_reviews")
def view_reviews():
    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM review")
    reviews = cursor.fetchall()
    conn.close()
    return render_template("view_reviews.html", reviews=reviews)


@app.route("/stats")
def stats():

    if "admin" not in session:
        return redirect("/")

    conn = db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM traveler")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM booking")
    bookings = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_amount) FROM booking")
    revenue = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "stats.html",
        users=users,
        bookings=bookings,
        revenue=revenue if revenue else 0
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)