from flask import Flask, render_template, request, redirect, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "secret123"


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
    cursor = conn.cursor(dictionary=True)

    # ADMIN LOGIN
    if role == "admin":

        cursor.execute(
            "SELECT * FROM admin WHERE name=%s AND password=%s",
            (username, password)
        )

        admin = cursor.fetchone()

        if admin:
            session["admin"] = admin["name"]
            return redirect("/admin_dashboard")

        return "Invalid Admin Login"

    # USER LOGIN
    cursor.execute(
        "SELECT * FROM traveler WHERE name=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    conn.close()

    if user:
        session["user"] = user["name"]
        return redirect("/dashboard")

    return "Invalid User Login"


# REGISTER PAGE
@app.route("/register")
def register():
    return render_template("register.html")


# REGISTER USER
@app.route("/register_user", methods=["POST"])
def register_user():

    adhar = request.form["adhar"]
    name = request.form["name"]
    address = request.form["address"]
    mobile = request.form["mobile"]
    password = request.form["password"]

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO traveler VALUES(%s,%s,%s,%s,%s)",
        (adhar, name, address, mobile, password)
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


# VIEW PACKAGES
@app.route("/packages")
def packages():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM package")

    packages = cursor.fetchall()

    conn.close()

    return render_template("packages.html", packages=packages)


# ADD REVIEW PAGE
@app.route("/add_review")
def add_review():
    return render_template("add_review.html")


# SAVE REVIEW
@app.route("/save_review", methods=["POST"])
def save_review():

    review = request.form["review"]

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO review(review) VALUES(%s)",
        (review,)
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ADMIN DASHBOARD
@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/")

    return render_template("admin_dashboard.html")


# MANAGE PACKAGES
@app.route("/manage_packages")
def manage_packages():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM package")

    packages = cursor.fetchall()

    conn.close()

    return render_template("manage_packages.html", packages=packages)


# ADD PACKAGE
@app.route("/add_package", methods=["POST"])
def add_package():

    category = request.form["category"]
    amt_rate = request.form["amt_rate"]
    description = request.form["description"]
    duration = request.form["duration"]

    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO package(category, amt_rate, description, duration) VALUES(%s,%s,%s,%s)",
        (category, amt_rate, description, duration)
    )

    conn.commit()
    conn.close()

    return redirect("/manage_packages")


# VIEW BOOKINGS
@app.route("/view_bookings")
def view_bookings():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM booking")

    bookings = cursor.fetchall()

    conn.close()

    return render_template("view_bookings.html", bookings=bookings)


# VIEW REVIEWS
@app.route("/view_reviews")
def view_reviews():

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM review")

    reviews = cursor.fetchall()

    conn.close()

    return render_template("view_reviews.html", reviews=reviews)


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)