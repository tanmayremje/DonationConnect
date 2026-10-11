from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file
)

import mysql.connector
import requests
import math

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from flask_mail import Mail, Message

app = Flask(__name__)

app.secret_key = "donationconnect_secret_key"

# --- EMAIL CONFIG - ADD THIS WHOLE BLOCK ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'donationconnect.admin@gmail.com'
app.config['MAIL_PASSWORD'] = ''
app.config['MAIL_DEFAULT_SENDER'] = 'donationconnect.admin@gmail.com'

mail = Mail(app)

def send_email(to, subject, body):
    try:
        msg = Message(subject, recipients=[to])
        msg.body = body
        mail.send(msg)
        print(f"Email sent to {to}")
        return True
    except Exception as e:
        print(f"EMAIL ERROR: {e}")
        return False

def add_notification(user_id, message, subject="DonationConnect Update"):
    try:
        # 1. Save to website notifications page
        db2 = get_db()
        cur2 = db2.cursor(dictionary=True)
        cur2.execute("INSERT INTO notifications (user_id, message) VALUES (%s,%s)", (user_id, message))
        db2.commit()
        # 2. Send same message to email
        cur2.execute("SELECT email, name FROM users WHERE id=%s", (user_id,))
        user = cur2.fetchone()
        cur2.close()
        db2.close()
        if user and user.get('email'):
            body = f"Hi {user['name']},\n\n{message}\n\nLogin here: http://127.0.0.1:5000/dashboard"
            send_email(user['email'], subject, body)
    except Exception as e:
        print(f"Notification error: {e}")
# --- END EMAIL CONFIG ---


# -------------------------------------------------
# DATABASE CONNECTION
# -------------------------------------------------

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="donationconnect"
    )


# -------------------------------------------------
# HOME
# -------------------------------------------------

@app.route("/")
def index():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT d.*, u.name AS donor_name
        FROM donations d
        JOIN users u ON d.donor_id = u.id
        WHERE d.status = 'Available'
        ORDER BY d.created_at DESC
        LIMIT 6
    """)

    donations = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "index.html",
        donations=donations
    )


# -------------------------------------------------
# REGISTER
# -------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        password = request.form["password"]
        role = request.form["role"]
        location = request.form["location"]

        password_hash = generate_password_hash(password)

        latitude = None
        longitude = None

        # -----------------------------------------
        # LOCATION GEOCODING
        # -----------------------------------------

        if location:

            try:

                response = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": location,
                        "format": "json",
                        "limit": 1
                    },
                    headers={
                        "User-Agent": "DonationConnect/1.0"
                    },
                    timeout=10
                )

                data = response.json()

                if data:

                    latitude = float(data[0]["lat"])
                    longitude = float(data[0]["lon"])

            except Exception:
                pass

        db = get_db()
        cursor = db.cursor()

        try:

            cursor.execute("""
                INSERT INTO users
                (name, email, mobile, password, role,
                 location, latitude, longitude)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                name,
                email,
                mobile,
                password_hash,
                role,
                location,
                latitude,
                longitude
            ))

            db.commit()

            flash(
                "Registration successful. Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except mysql.connector.Error as e:

            flash(
                "Email already exists or database error.",
                "danger"
            )

        finally:

            cursor.close()
            db.close()

    return render_template("register.html")


# -------------------------------------------------
# LOGIN
# -------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if session.get('role') == 'admin':
                return redirect(
                url_for("admin")
            )

            else:

                return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid email or password.",
            "danger"
        )

        

    return render_template("login.html")


# -------------------------------------------------
# LOGOUT
# -------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("index")
    )


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    donation_count = 0
    received_count = 0
    request_count = 0
    notification_count = 0

    user_id = session["user_id"]

    if session["role"] == "donor":

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM donations
            WHERE donor_id=%s
        """, (user_id,))

        donation_count = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM donation_requests r
            JOIN donations d ON r.donation_id = d.id
            WHERE d.donor_id=%s
            """, (user_id,))
        
        request_count = cursor.fetchone()["total"]
        
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE user_id=%s
            AND is_read=FALSE
            """, (user_id,))
        
        notification_count = cursor.fetchone()["total"]

    elif session["role"] == "acceptor" :

        cursor.execute("""
        SELECT COUNT(*) AS total
        FROM donation_requests
        WHERE acceptor_id = %s
        AND status = 'Completed'
        """, (user_id,))

        received_count = cursor.fetchone()["total"]
    

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM donation_requests
            WHERE acceptor_id=%s
        """, (user_id,))

        request_count = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE user_id=%s
            AND is_read=FALSE
        """, (user_id,))

        notification_count = cursor.fetchone()["total"]

    cursor.close()
    db.close()

    return render_template(
        "dashboard.html",
        donation_count=donation_count,
        received_count=received_count,
        request_count=request_count,
        notification_count=notification_count
    )


# -------------------------------------------------
# ADD DONATION
# -------------------------------------------------

@app.route("/add-donation", methods=["GET", "POST"])
def add_donation():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "donor":

        flash(
            "Only donors can add donations.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        name = request.form["name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        if latitude: latitude = float(latitude)
        if longitude: longitude = float(longitude)

        # -----------------------------------------
        # NOMINATIM GEOCODING
        # -----------------------------------------

        try:

            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": location,
                    "format": "json",
                    "limit": 1
                },
                headers={
                    "User-Agent": "DonationConnect/1.0"
                },
                timeout=10
            )

            data = response.json()

            if data:

                latitude = float(data[0]["lat"])
                longitude = float(data[0]["lon"])

        except Exception:

            pass

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO donations
            (
                donor_id,
                name,
                category,
                description,
                location,
                latitude,
                longitude
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            session["user_id"],
            name,
            category,
            description,
            location,
            latitude,
            longitude
        ))

        db.commit()

        cursor.close()
        db.close()

        flash(
            "Donation added successfully!",
            "success"
        )

        return redirect(
            url_for("donations")
        )

    return render_template(
        "add_donation.html"
    )


# -------------------------------------------------
# VIEW DONATIONS
# -------------------------------------------------

@app.route("/donations")
def donations():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get search and filter values
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    # Base query
    query = """
        SELECT
            d.*,
            u.name AS donor_name
        FROM donations d
        JOIN users u
            ON d.donor_id = u.id
        WHERE d.status = 'Available'
    """

    params = []

    # Search by donation name
    if search:

        query += """
            AND (
                d.name LIKE %s
                OR d.description LIKE %s
            )
        """

        search_value = "%" + search + "%"

        params.append(search_value)
        params.append(search_value)

    # Category filter
    if category:

        query += " AND d.category = %s"
        params.append(category)

    # Category filter
    if location:
    
        query += " AND d.location LIKE  %s"
        params.append(f"%{location}%")

    # Latest donations first
    query += """
        ORDER BY d.created_at DESC
    """

    cursor.execute(query, tuple(params))
    donations = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "donations.html",
        donations=donations,
        search=search,
        category=category,
        location=location
    )


# -------------------------------------------------
# REQUEST DONATION
# -------------------------------------------------

@app.route(
    "/request-donation/<int:donation_id>",
    methods=["POST"]
)
def request_donation(donation_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "acceptor":

        flash(
            "Only acceptors can request donations.",
            "danger"
        )

        return redirect(
            url_for("donations")
        )

    message = request.form.get(
        "message",
        ""
    )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT * donor_id, name
        FROM donations
        WHERE id=%s
    """, (donation_id,))

    donation = cursor.fetchone()

    if not donation:

        cursor.close()
        db.close()

        flash(
            "Donation not found.",
            "danger"
        )

        return redirect(
            url_for("donations")
        )

    cursor.execute("""
        SELECT id
        FROM donation_requests
        WHERE donation_id=%s
        AND acceptor_id=%s
        AND status='Pending'
    """, (
        donation_id,
        session["user_id"]
    ))

    existing = cursor.fetchone()

    if existing:

        flash(
            "You already requested this donation.",
            "warning"
        )

    else:

        cursor.execute("""
            INSERT INTO donation_requests
            (
                donation_id,
                acceptor_id,
                message
            )
            VALUES (%s,%s,%s)
        """, (
            donation_id,
            session["user_id"],
            message
        ))

        add_notification(
            donation["donor_id"],
            f"New request for your donation: {donation['name']}"
        )

        db.commit()

        # --- EMAIL TO DONOR ---
        cursor.execute("SELECT email, name FROM users WHERE id=%s", (donation["donor_id"],))
        donor = cursor.fetchone()
        cursor.execute("SELECT name FROM users WHERE id=%s", (session["user_id"],))
        acceptor = cursor.fetchone()

        if donor:
            send_email(
                to=donor['email'],
                subject=f"New Request for {donation['name']} - DonationConnect",
                body=f"Hi {donor['name']},\n\nYou have a new request for your donation '{donation['name']}' from {acceptor['name']}.\n\nMessage: {message}\n\nPlease login to DonationConnect to accept/reject.\n\nhttp://127.0.0.1:5000/requests"
            )

        flash(
            "Donation request sent!",
            "success"
        )

    cursor.close()
    db.close()

    return redirect(
        url_for("donations")
    )


# -------------------------------------------------
# DONATION REQUESTS
# -------------------------------------------------

@app.route("/requests")
def requests_page():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if session["role"] == "donor":

        cursor.execute("""
            SELECT
                r.*,
                d.name AS donation_name,
                u.name AS acceptor_name,
                u.mobile AS acceptor_mobile
            FROM donation_requests r
            JOIN donations d
                ON r.donation_id=d.id
            JOIN users u
                ON r.acceptor_id=u.id
            WHERE d.donor_id=%s
            ORDER BY r.created_at DESC
        """, (session["user_id"],))

    else:

        cursor.execute("""
            SELECT
                r.*,
                d.name AS donation_name,
                u.name AS donor_name
            FROM donation_requests r
            JOIN donations d
                ON r.donation_id=d.id
            JOIN users u
                ON d.donor_id=u.id
            WHERE r.acceptor_id=%s
            ORDER BY r.created_at DESC
        """, (session["user_id"],))

    requests_data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "requests.html",
        requests=requests_data
    )


# -------------------------------------------------
# ACCEPT REQUEST
# -------------------------------------------------

@app.route(
    "/accept-request/<int:request_id>"
)
def accept_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    # Only donor can accept a request
    if session["role"] != "donor":
        flash("Only donors can accept donation requests.", "danger")
        return redirect(url_for("requests_page"))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get request + donation + donor + acceptor details
    cursor.execute("""
        SELECT
            r.id AS request_id,
            r.donation_id,
            r.acceptor_id,
            r.status AS request_status,

            d.name AS donation_name,
            d.donor_id,

            donor.name AS donor_name,
            donor.mobile AS donor_mobile,
            donor.email AS donor_email,

            acceptor.name AS acceptor_name,
            acceptor.mobile AS acceptor_mobile,
            acceptor.email AS acceptor_email

        FROM donation_requests r

        JOIN donations d
            ON r.donation_id = d.id

        JOIN users donor
            ON d.donor_id = donor.id

        JOIN users acceptor
            ON r.acceptor_id = acceptor.id

        WHERE r.id = %s
    """, (request_id,))

    req = cursor.fetchone()

    if not req:
        cursor.close()
        db.close()

        flash("Donation request not found.", "danger")
        return redirect(url_for("requests_page"))

    # Security check:
    # Only the donor who owns the donation can accept it
    if req["donor_id"] != session["user_id"]:
        cursor.close()
        db.close()

        flash("You are not authorized to accept this request.", "danger")
        return redirect(url_for("requests_page"))

    # Don't accept an already processed request
    if req["request_status"] != "Pending":
        cursor.close()
        db.close()

        flash("This request has already been processed.", "warning")
        return redirect(url_for("requests_page"))

    # -------------------------------------------------
    # ACCEPT REQUEST
    # -------------------------------------------------

    cursor.execute("""
        UPDATE donation_requests
        SET status='Accepted'
        WHERE id=%s
    """, (request_id,))

    # Make donation reserved
    cursor.execute("""
        UPDATE donations
        SET status='Reserved'
        WHERE id=%s
    """, (req["donation_id"],))

    # -------------------------------------------------
    # SEND DONOR CONTACT TO ACCEPTOR
    # -------------------------------------------------

    acceptor_message = (
        f"Your request for '{req['donation_name']}' has been ACCEPTED.\n\n"
        f"Donor Name: {req['donor_name']}\n"
        f"Donor Mobile: {req['donor_mobile']}\n"
        f"Donor Email: {req['donor_email']}"
    )

    add_notification (
        req["acceptor_id"],
        acceptor_message
    )

    # -------------------------------------------------
    # SEND ACCEPTOR CONTACT TO DONOR
    # -------------------------------------------------

    donor_message = (
        f"Your donation '{req['donation_name']}' has been accepted by {req['acceptor_name']}.\n\n"
        f"Acceptor Name: {req['acceptor_name']}\n"
        f"Acceptor Mobile: {req['acceptor_mobile']}\n"
        f"Acceptor Email: {req['acceptor_email']}"
    )

    add_notification (
        req["donor_id"],
        donor_message
    )

    db.commit()

    cursor.close()
    db.close()

    flash(
        "Request accepted. Donor and acceptor contact details have been shared.",
        "success"
    )

    return redirect(url_for("requests_page"))


# -------------------------------------------------
# REJECT REQUEST
# -------------------------------------------------

@app.route(
    "/reject-request/<int:request_id>"
)
def reject_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            r.*,
            d.name AS donation_name
        FROM donation_requests r
        JOIN donations d
            ON r.donation_id=d.id
        WHERE r.id=%s
    """, (request_id,))

    req = cursor.fetchone()

    if req:

        cursor.execute("""
            UPDATE donation_requests
            SET status='Rejected'
            WHERE id=%s
        """, (request_id,))

        add_notification (
            req["acceptor_id"],
            f"Your request for '{req['donation_name']}' was rejected."
        )

        db.commit()

        flash(
            "Request rejected.",
            "warning"
        )

    cursor.close()
    db.close()

    return redirect(
        url_for("requests_page")
    )


# -------------------------------------------------
# COMPLETE DONATION
# -------------------------------------------------

@app.route(
    "/complete-request/<int:request_id>"
)
def complete_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT donation_id, acceptor_id
        FROM donation_requests
        WHERE id=%s
    """, (request_id,))

    req = cursor.fetchone()

    if req:

        cursor.execute("""
            UPDATE donation_requests
            SET status='Completed'
            WHERE id=%s
        """, (request_id,))

        cursor.execute("""
            UPDATE donations
            SET status='Completed'
            WHERE id=%s
        """, (req["donation_id"],))

        cursor.execute("""
            SELECT name
            FROM donations
            WHERE id=%s
        """, (req["donation_id"],))

        donation = cursor.fetchone()

        add_notification (
            req["acceptor_id"],
            f"Donation '{donation['name']}' marked as completed."
        )

        db.commit()

        flash(
            "Donation marked as completed.",
            "success"
        )

    cursor.close()
    db.close()

    return redirect(
        url_for("requests_page")
    )

# -------------------------------------------------
# DONATION CERTIFICATE
# -------------------------------------------------

@app.route("/certificate/<int:donation_id>")
def certificate(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only donor can view certificate
    if session.get("role") != "donor":
        flash(
            "Only donors can view certificates.",
            "danger"
        )
        return redirect(url_for("history"))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            d.id,
            d.name AS donation_name,
            d.status,
            d.created_at,
            u.name AS donor_name

        FROM donations d

        JOIN users u
            ON d.donor_id = u.id

        WHERE d.id = %s
        AND d.donor_id = %s
    """, (
        donation_id,
        session["user_id"]
    ))

    donation = cursor.fetchone()

    cursor.close()
    db.close()

    if not donation:

        flash(
            "Donation not found.",
            "danger"
        )

        return redirect(url_for("history"))

    if donation["status"] != "Completed":

        flash(
            "Certificate is available only after donation is completed.",
            "warning"
        )

        return redirect(url_for("history"))

    certificate_number = (
        f"DC-{donation['id']:05d}"
    )

    return render_template(
        "certificate.html",

        donor_name=donation["donor_name"],

        donation_name=donation["donation_name"],

        donation_date=donation["created_at"],

        certificate_number=certificate_number
    )

# -------------------------------------------------
# NOTIFICATIONS
# -------------------------------------------------

@app.route("/notifications")
def notifications():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM notifications
        WHERE user_id=%s
        ORDER BY created_at DESC
    """, (session["user_id"],))

    notifications_data = cursor.fetchall()

    cursor.execute("""
        UPDATE notifications
        SET is_read=TRUE
        WHERE user_id=%s
    """, (session["user_id"],))

    db.commit()

    cursor.close()
    db.close()

    return render_template(
        "notifications.html",
        notifications=notifications_data
    )


# -------------------------------------------------
# HISTORY
# -------------------------------------------------

@app.route("/history")
def history():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if session["role"] == "donor":

        cursor.execute("""
            SELECT
                r.*,
                d.name AS donation_name,
                u.name AS other_user
            FROM donation_requests r
            JOIN donations d
                ON r.donation_id=d.id
            JOIN users u
                ON r.acceptor_id=u.id
            WHERE d.donor_id=%s
            AND r.status='Completed'
            ORDER BY r.created_at DESC
        """, (session["user_id"],))

    else:

        cursor.execute("""
            SELECT
                r.*,
                d.name AS donation_name,
                u.name AS other_user
            FROM donation_requests r
            JOIN donations d
                ON r.donation_id=d.id
            JOIN users u
                ON d.donor_id=u.id
            WHERE r.acceptor_id=%s
            AND r.status='Completed'
            ORDER BY r.created_at DESC
        """, (session["user_id"],))

    history_data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "history.html",
        history=history_data
    )


# -------------------------------------------------
# COMPLAINT
# -------------------------------------------------

@app.route(
    "/complaint",
    methods=["GET", "POST"]
)
def complaint():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        subject = request.form["subject"]
        description = request.form["description"]

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO complaints
            (
                user_id,
                subject,
                description
            )
            VALUES (%s,%s,%s)
        """, (
            session["user_id"],
            subject,
            description
        ))

        db.commit()

        cursor.close()
        db.close()

        flash(
            "Complaint submitted successfully.",
            "success"
        )

        return redirect(
            url_for("complaint")
        )

    return render_template(
        "complaint.html"
    )

# ------------------------------
# ADMIN DASHBOARD
# ------------------------------

@app.route("/admin")
def admin():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "admin":

        flash(
            "Admin access required.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT COUNT(*) AS total FROM users"
    )
    total_users = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM users
        WHERE role='donor'
    """)
    total_donors = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM users
        WHERE role='acceptor'
    """)
    total_acceptors = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM donations"
    )
    total_donations = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM donation_requests
        WHERE status='Pending'
    """)
    pending_requests = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM donation_requests
        WHERE status='Completed'
    """)
    completed_donations = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT 
            c.id,
            c.subject,
            c.description,
            c.created_at,
            u.name AS user_name,
            u.email AS user_email,
            u.mobile AS user_mobile
        FROM complaints c
        LEFT JOIN users u
            ON c.user_id = u.id
        ORDER BY c.created_at DESC
    """)
    complaints_data = cursor.fetchall()
    print("Complaints found:", complaints_data)

    # Get all users
    cursor.execute("""
        SELECT id, name, email, mobile, role, created_at
        FROM users
        ORDER BY id DESC
    """)
    users = cursor.fetchall()

    # Get all donations
    cursor.execute("""
        SELECT
            d.id,
            d.name,
            d.category,
            d.description,
            d.location,
            d.status,
            d.created_at,
            u.name AS donor_name
        FROM donations d
        JOIN users u ON d.donor_id = u.id
        ORDER BY d.id DESC
    """)
    donations = cursor.fetchall()


    cursor.close()
    db.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_donors=total_donors,
        total_acceptors=total_acceptors,
        total_donations=total_donations,
        pending_requests=pending_requests,
        completed_donations=completed_donations,
        complaints=complaints_data, 
        users=users,
        donations=donations,
    )

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('admin'))

    # Prevent admin from deleting himself
    if user_id == session['user_id']:
        flash('You cannot delete your own admin account.', 'danger')
        return redirect(url_for('admin'))

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM users
        WHERE id = %s
    """, (user_id,))

    db.commit()

    cursor.close()
    db.close()

    flash('User deleted successfully.', 'success')

    return redirect(url_for('admin'))

@app.route('/admin/delete-donation/<int:donation_id>', methods=['POST'])
def admin_delete_donation(donation_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('admin'))

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM donations
        WHERE id = %s
    """, (donation_id,))

    db.commit()

    cursor.close()
    db.close()

    flash('Donation deleted successfully.', 'success')

    return redirect(url_for('admin'))

# ------------------------------
# RUN APPLICATION
# ------------------------------

if __name__ ==  "__main__":
    app.run(debug=True)
