"""
WeGo - Local Tourist Guide Marketplace
A single-file Flask + SQLite app.

Sections in this file, top to bottom:
  1. Setup and database schema
  2. Shared helpers (page wrapper, login checks)
  3. Auth routes: signup, login, logout
  4. Guide profile routes: create/edit your own profile
  5. Search routes: browse and filter guides
  6. Booking routes: request, accept/reject, complete
  7. Review routes: leave a review after a completed booking
  8. Run the server
"""

import os
from functools import wraps
from flask import Flask, request, redirect, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
# In production, set a real SECRET_KEY environment variable on your host
# (Render/Railway dashboard -> Environment tab). Falls back to a dev-only
# value so it still runs locally without extra setup.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-locally")

DB_NAME = os.environ.get("DB_NAME", "wego.db")


# ============================================================
# 1. SETUP AND DATABASE SCHEMA
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["name"]
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            city TEXT
        );

        CREATE TABLE IF NOT EXISTS guide_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            bio TEXT,
            languages TEXT,
            price_per_hour REAL,
            city TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tourist_id INTEGER NOT NULL,
            guide_id INTEGER NOT NULL,
            date TEXT,
            time_slot TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (tourist_id) REFERENCES users (id),
            FOREIGN KEY (guide_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER UNIQUE NOT NULL,
            tourist_id INTEGER NOT NULL,
            guide_id INTEGER NOT NULL,
            rating INTEGER,
            comment TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings (id)
        );
    """)
    conn.commit()
    conn.close()


init_db()


# ============================================================
# 2. SHARED HELPERS
# ============================================================

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 15px; background: #f7f7f7; color: #222; }
  nav { margin-bottom: 20px; }
  nav a { margin-right: 12px; color: #1a73e8; text-decoration: none; font-size: 14px; }
  input, select, textarea { width: 100%; padding: 8px; margin: 6px 0 12px 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; font-size: 15px; }
  input[type=submit], button { background: #1a73e8; color: white; border: none; padding: 10px 16px; border-radius: 5px; font-size: 15px; }
  .card { background: white; padding: 12px; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
  .badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; color:white; }
  .pending { background: #e08a00; }
  .accepted { background: #1a73e8; }
  .completed { background: #1e8e3e; }
  .rejected { background: #888; }
  h2 { font-size: 20px; }
  h3 { font-size: 16px; }
</style>
</head>
<body>
<nav>
  <a href="/">Home</a>
  <a href="/guides">Find Guides</a>
  {% if user %}
    <a href="/bookings/mine">My Bookings</a>
    {% if user.role == 'guide' %}<a href="/guide/create">My Guide Profile</a>{% endif %}
    <a href="/logout">Logout ({{ user.name }})</a>
  {% else %}
    <a href="/signup">Sign up</a>
    <a href="/login">Log in</a>
  {% endif %}
</nav>
{{ body|safe }}
</body>
</html>
"""


def render_page(title, body_html):
    user = None
    if "user_id" in session:
        user = {"id": session["user_id"], "name": session["name"], "role": session["role"]}
    return render_template_string(PAGE_TEMPLATE, title=title, body=body_html, user=user)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect("/login")
            if session.get("role") != role:
                return render_page("Not allowed", f"<p>This page is only for {role}s.</p>")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def avg_rating_for(conn, guide_user_id):
    row = conn.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM reviews WHERE guide_id=?",
        (guide_user_id,)
    ).fetchone()
    if row["count"]:
        return f"{row['avg_rating']:.1f} \u2b50 ({row['count']} reviews)"
    return "No reviews yet"


# ============================================================
# 3. AUTH ROUTES
# ============================================================

@app.route("/")
def home():
    if "user_id" in session:
        body = f"<h2>Welcome back, {session['name']}!</h2><p>Role: {session['role']}</p>"
        if session["role"] == "tourist":
            body += "<p><a href='/guides'>Browse guides near you</a></p>"
        else:
            body += "<p><a href='/guide/create'>Set up or edit your guide profile</a></p>"
    else:
        body = (
            "<h2>Welcome to WeGo</h2>"
            "<p>Find a local guide for your trip, or become one and earn money "
            "showing tourists your city.</p>"
            "<p><a href='/signup'>Sign up</a> to get started.</p>"
        )
    return render_page("WeGo", body)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        city = request.form["city"].strip()
        role = request.form["role"]

        if not name or not email or not password:
            return render_page("Signup", "<p>Please fill all required fields. <a href='/signup'>Back</a></p>")

        password_hash = generate_password_hash(password)
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, city) VALUES (?, ?, ?, ?, ?)",
                (name, email, password_hash, role, city)
            )
            conn.commit()
            user_id = cur.lastrowid
        except sqlite3.IntegrityError:
            conn.close()
            return render_page("Signup", "<p>That email is already registered. <a href='/login'>Log in instead</a></p>")
        conn.close()

        # auto-login right after signup, less friction for testers
        session["user_id"] = user_id
        session["name"] = name
        session["role"] = role

        if role == "guide":
            return redirect("/guide/create")
        return redirect("/guides")

    body = """
    <h2>Sign up</h2>
    <form method="POST">
      Name<input name="name" required>
      Email<input name="email" type="email" required>
      Password<input name="password" type="password" required>
      City<input name="city" required>
      I am a...
      <select name="role">
        <option value="tourist">Tourist (looking for a guide)</option>
        <option value="guide">Local Guide (want to earn money)</option>
      </select>
      <input type="submit" value="Sign up">
    </form>
    <p>Already have an account? <a href="/login">Log in</a></p>
    """
    return render_page("Sign up", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect("/")
        return render_page("Login", "<p>Invalid email or password. <a href='/login'>Try again</a></p>")

    body = """
    <h2>Log in</h2>
    <form method="POST">
      Email<input name="email" type="email" required>
      Password<input name="password" type="password" required>
      <input type="submit" value="Log in">
    </form>
    <p>New here? <a href="/signup">Sign up</a></p>
    """
    return render_page("Log in", body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ============================================================
# 4. GUIDE PROFILE ROUTES
# ============================================================

@app.route("/guide/create", methods=["GET", "POST"])
@role_required("guide")
def guide_create():
    conn = get_db()
    existing = conn.execute("SELECT * FROM guide_profiles WHERE user_id=?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        bio = request.form["bio"].strip()
        languages = request.form["languages"].strip()
        city = request.form["city"].strip()

        try:
            price = float(request.form["price"])
        except ValueError:
            conn.close()
            return render_page("Guide Profile", "<p>Price must be a number. <a href='/guide/create'>Back</a></p>")

        if existing:
            conn.execute(
                "UPDATE guide_profiles SET bio=?, languages=?, price_per_hour=?, city=? WHERE user_id=?",
                (bio, languages, price, city, session["user_id"])
            )
        else:
            conn.execute(
                "INSERT INTO guide_profiles (user_id, bio, languages, price_per_hour, city) VALUES (?, ?, ?, ?, ?)",
                (session["user_id"], bio, languages, price, city)
            )
        conn.commit()
        conn.close()
        return redirect(f"/guides/{session['user_id']}")

    conn.close()
    bio_val = existing["bio"] if existing else ""
    lang_val = existing["languages"] if existing else ""
    price_val = existing["price_per_hour"] if existing else ""
    city_val = existing["city"] if existing else ""

    body = f"""
    <h2>{"Edit" if existing else "Create"} Your Guide Profile</h2>
    <form method="POST">
      City you guide in<input name="city" value="{city_val}" required>
      Languages you speak (comma separated)<input name="languages" value="{lang_val}" placeholder="English, Hindi">
      Price per hour (INR)<input name="price" type="number" step="1" value="{price_val}" required>
      About you<textarea name="bio" rows="4">{bio_val}</textarea>
      <input type="submit" value="Save Profile">
    </form>
    """
    return render_page("Guide Profile", body)


# ============================================================
# 5. SEARCH ROUTES
# ============================================================

@app.route("/guides")
def guides_list():
    city = request.args.get("city", "").strip()
    max_price = request.args.get("max_price", "").strip()
    language = request.args.get("language", "").strip()

    query = """
        SELECT u.id as user_id, u.name, gp.city, gp.price_per_hour, gp.languages, gp.bio
        FROM guide_profiles gp
        JOIN users u ON u.id = gp.user_id
        WHERE 1=1
    """
    params = []
    if city:
        query += " AND gp.city LIKE ?"
        params.append(f"%{city}%")
    if max_price:
        try:
            query += " AND gp.price_per_hour <= ?"
            params.append(float(max_price))
        except ValueError:
            pass
    if language:
        query += " AND gp.languages LIKE ?"
        params.append(f"%{language}%")

    conn = get_db()
    guides = conn.execute(query, params).fetchall()

    cards = ""
    for g in guides:
        rating_text = avg_rating_for(conn, g["user_id"])
        cards += f"""
        <div class="card">
          <b>{g['name']}</b> &mdash; {g['city']}<br>
          &#8377;{g['price_per_hour']}/hr | Speaks: {g['languages']}<br>
          {rating_text}<br>
          <a href="/guides/{g['user_id']}">View profile &amp; book</a>
        </div>
        """
    conn.close()

    if not cards:
        cards = "<p>No guides found. Try clearing filters.</p>"

    body = f"""
    <h2>Find a Local Guide</h2>
    <form method="GET">
      City<input name="city" value="{city}" placeholder="e.g. Jaipur">
      Max price per hour<input name="max_price" value="{max_price}" type="number">
      Language<input name="language" value="{language}" placeholder="e.g. English">
      <input type="submit" value="Search">
    </form>
    {cards}
    """
    return render_page("Find Guides", body)


@app.route("/guides/<int:guide_user_id>", methods=["GET", "POST"])
def guide_profile(guide_user_id):
    conn = get_db()
    guide_user = conn.execute("SELECT * FROM users WHERE id=? AND role='guide'", (guide_user_id,)).fetchone()
    if not guide_user:
        conn.close()
        return render_page("Not found", "<p>Guide not found.</p>")

    profile = conn.execute("SELECT * FROM guide_profiles WHERE user_id=?", (guide_user_id,)).fetchone()

    if request.method == "POST":
        if "user_id" not in session:
            conn.close()
            return redirect("/login")
        if session["role"] != "tourist":
            conn.close()
            return render_page("Booking", "<p>Only tourists can send booking requests.</p>")

        date = request.form["date"]
        time_slot = request.form["time_slot"]
        message = request.form.get("message", "")

        conn.execute(
            "INSERT INTO bookings (tourist_id, guide_id, date, time_slot, message, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (session["user_id"], guide_user_id, date, time_slot, message)
        )
        conn.commit()
        conn.close()
        return redirect("/bookings/mine")

    reviews = conn.execute(
        "SELECT r.rating, r.comment, u.name FROM reviews r JOIN users u ON u.id = r.tourist_id WHERE r.guide_id=?",
        (guide_user_id,)
    ).fetchall()
    rating_text = avg_rating_for(conn, guide_user_id)
    conn.close()

    review_html = "".join(
        f"<div class='card'><b>{r['name']}</b>: {r['rating']}&#11088;<br>{r['comment']}</div>" for r in reviews
    ) or "<p>No reviews yet.</p>"

    booking_form = ""
    if "user_id" in session and session["role"] == "tourist":
        booking_form = """
        <h3>Request a Booking</h3>
        <form method="POST">
          Date<input name="date" type="date" required>
          Time<input name="time_slot" type="time" required>
          Message (optional)<textarea name="message" rows="2"></textarea>
          <input type="submit" value="Send Request">
        </form>
        """
    elif "user_id" not in session:
        booking_form = "<p><a href='/login'>Log in as a tourist</a> to book this guide.</p>"

    body = f"""
    <h2>{guide_user['name']} &mdash; {profile['city'] if profile else ''}</h2>
    <p>&#8377;{profile['price_per_hour'] if profile else '-'}/hr | Speaks: {profile['languages'] if profile else '-'}</p>
    <p>{profile['bio'] if profile else ''}</p>
    <p>{rating_text}</p>
    {booking_form}
    <h3>Reviews</h3>
    {review_html}
    """
    return render_page(guide_user["name"], body)


# ============================================================
# 6. BOOKING ROUTES
# ============================================================

@app.route("/bookings/mine")
@login_required
def bookings_mine():
    conn = get_db()
    if session["role"] == "tourist":
        bookings = conn.execute("""
            SELECT b.*, u.name as other_name FROM bookings b
            JOIN users u ON u.id = b.guide_id
            WHERE b.tourist_id=?
            ORDER BY b.id DESC
        """, (session["user_id"],)).fetchall()
    else:
        bookings = conn.execute("""
            SELECT b.*, u.name as other_name FROM bookings b
            JOIN users u ON u.id = b.tourist_id
            WHERE b.guide_id=?
            ORDER BY b.id DESC
        """, (session["user_id"],)).fetchall()

    rows = ""
    for b in bookings:
        status_class = b["status"]
        actions = ""

        if session["role"] == "guide" and b["status"] == "pending":
            actions = f"""
            <form method="POST" action="/bookings/{b['id']}/status/accepted" style="display:inline">
              <input type="submit" value="Accept">
            </form>
            <form method="POST" action="/bookings/{b['id']}/status/rejected" style="display:inline">
              <input type="submit" value="Reject">
            </form>
            """
        elif session["role"] == "guide" and b["status"] == "accepted":
            actions = f"""
            <form method="POST" action="/bookings/{b['id']}/status/completed" style="display:inline">
              <input type="submit" value="Mark Completed">
            </form>
            """
        elif session["role"] == "tourist" and b["status"] == "completed":
            existing_review = conn.execute("SELECT id FROM reviews WHERE booking_id=?", (b["id"],)).fetchone()
            actions = f"<a href='/bookings/{b['id']}/review'>Leave a review</a>" if not existing_review else "Review submitted"

        rows += f"""
        <div class="card">
          With: {b['other_name']}<br>
          {b['date']} at {b['time_slot']}<br>
          Status: <span class="badge {status_class}">{b['status']}</span><br>
          {actions}
        </div>
        """
    conn.close()

    if not rows:
        rows = "<p>No bookings yet.</p>"

    return render_page("My Bookings", f"<h2>My Bookings</h2>{rows}")


@app.route("/bookings/<int:booking_id>/status/<action>", methods=["POST"])
@login_required
def booking_status(booking_id, action):
    if action not in ("accepted", "rejected", "completed"):
        return render_page("Error", "<p>Invalid action.</p>")

    conn = get_db()
    booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking or booking["guide_id"] != session["user_id"]:
        conn.close()
        return render_page("Error", "<p>Not allowed.</p>")

    conn.execute("UPDATE bookings SET status=? WHERE id=?", (action, booking_id))
    conn.commit()
    conn.close()
    return redirect("/bookings/mine")


# ============================================================
# 7. REVIEW ROUTES
# ============================================================

@app.route("/bookings/<int:booking_id>/review", methods=["GET", "POST"])
@role_required("tourist")
def leave_review(booking_id):
    conn = get_db()
    booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()

    if not booking or booking["tourist_id"] != session["user_id"] or booking["status"] != "completed":
        conn.close()
        return render_page("Error", "<p>You can't review this booking.</p>")

    if request.method == "POST":
        rating = int(request.form["rating"])
        comment = request.form.get("comment", "")
        try:
            conn.execute(
                "INSERT INTO reviews (booking_id, tourist_id, guide_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
                (booking_id, session["user_id"], booking["guide_id"], rating, comment)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_page("Error", "<p>You already reviewed this booking.</p>")
        conn.close()
        return redirect("/bookings/mine")

    conn.close()
    body = """
    <h2>Leave a Review</h2>
    <form method="POST">
      Rating (1-5)<input name="rating" type="number" min="1" max="5" required>
      Comment<textarea name="comment" rows="3"></textarea>
      <input type="submit" value="Submit Review">
    </form>
    """
    return render_page("Leave a Review", body)


# ============================================================
# 8. RUN THE SERVER
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
