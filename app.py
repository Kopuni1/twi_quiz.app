# -------------------------------
# Section 1: Imports and Initialization
# -------------------------------

import os
import random
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse
from functools import wraps
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Flask imports
from flask import Flask, render_template, request, session, flash, redirect, url_for, g

# Load environment variables if using a .env file
from dotenv import load_dotenv
load_dotenv()

# ---------------------------
# Initialize Flask app
# ---------------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key_here')

# ---------------------------
# Database connection
# ---------------------------
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ ERROR: DATABASE_URL is not set!")
        return None
    try:
        result = urlparse(db_url)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
            sslmode="require",
            cursor_factory=psycopg2.extras.DictCursor
        )
        return conn
    except Exception as e:
        print("❌ Database connection FAILED:", e)
        return None

# ---------------------------
# Custom login_required decorator
# ---------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("You must log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------------
# Context processors
# ---------------------------
@app.context_processor
def inject_globals():
    return dict(session=session, datetime=datetime, date=date)

@app.context_processor
def inject_unread_count():
    unread_count = 0
    if session.get('username') == 'kwadwo':
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM contact_messages WHERE is_read = FALSE")
                    unread_count = cur.fetchone()[0]
            finally:
                conn.close()
    return dict(unread_count=unread_count)

# -------------------------------
# Section 2: Authentication
# -------------------------------

# Sign-Up
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        raw_password = request.form['password'].strip()
        password = generate_password_hash(raw_password)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            flash("Username already exists.", "error")
            cur.close()
            conn.close()
            return redirect(url_for('signup'))

        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s,%s,%s)",
            (username, password, 'user')
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password_input = request.form['password'].strip()

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user['password'], password_input):
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f"Welcome, {user['username']}!", "success")
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))

@app.route('/scrabble')
@login_required
def scrabble():
    return render_template('scrabble.html')  # Make sure this template exists

# -------------------------------
# Section 3: Dashboards
# -------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    today = date.today()
    cur.execute("SELECT * FROM word_of_the_day WHERE date_selected=%s", (today,))
    today_word = cur.fetchone()

    if not today_word:
        cur.execute("SELECT word, pronunciation, part_of_speech, definition, example, audio_file FROM words")
        words = cur.fetchall()
        if words:
            random_word = random.choice(words)
            cur.execute("""
                INSERT INTO word_of_the_day 
                (word, pronunciation, part_of_speech, definition, example, audio_file, date_selected)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (*random_word, today))
            conn.commit()
            today_word = random_word
    else:
        today_word = {
            "word": today_word[1],
            "pronunciation": today_word[2],
            "part_of_speech": today_word[3],
            "definition": today_word[4],
            "example": today_word[5],
            "audio_file": today_word[6].replace("audio/", "") if today_word[6] else None
        }

    cur.execute("""
        SELECT word, pronunciation, part_of_speech, definition, example, audio_file, date_selected
        FROM word_of_the_day ORDER BY date_selected DESC
    """)
    history = [{
        "word": w[0],
        "pronunciation": w[1],
        "part_of_speech": w[2],
        "definition": w[3],
        "example": w[4],
        "audio_file": w[5].replace("audio/", "") if w[5] else None,
        "date_selected": w[6]
    } for w in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('dashboard.html',
                           username=session['username'],
                           today_word=today_word,
                           history=history)

# -------------------------------
# Admin Dashboard
# -------------------------------
@app.route('/admin')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Users
    cur.execute("SELECT username, role FROM users ORDER BY username")
    users = cur.fetchall()

    # Words
    cur.execute("SELECT * FROM words ORDER BY word")
    words = cur.fetchall()

    # Quiz history
    cur.execute("""
        SELECT username, category, score, total_questions, time_taken, date_taken
        FROM quiz_history
        ORDER BY date_taken DESC
    """)
    all_quiz_history = cur.fetchall()

    # Contact messages
    cur.execute("SELECT * FROM contact_messages ORDER BY created_at DESC")
    messages = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'admin_dashboard.html',
        username=session['username'],
        users=users,
        words=words,
        quiz_history=all_quiz_history,
        messages=messages
    )

# -------------------------------
# Section 4: Admin Management of Users & Words & Quiz
# -------------------------------

# Change role
@app.route('/change_role/<username>', methods=['POST'])
@login_required
def change_role(username):
    if session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username=%s", (username,))
    user = cur.fetchone()
    if user:
        new_role = 'admin' if user[0] == 'user' else 'user'
        cur.execute("UPDATE users SET role=%s WHERE username=%s", (new_role, username))
        conn.commit()
        flash(f"Role of {username} updated to {new_role}.", "success")
    cur.close()
    conn.close()
    return redirect(url_for('admin_dashboard'))

# Delete user
@app.route('/delete_user/<username>', methods=['POST'])
@login_required
def delete_user(username):
    if session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))
    if username == session['username']:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE username=%s", (username,))
    conn.commit()
    cur.close()
    conn.close()
    flash(f"User {username} deleted successfully.", "success")
    return redirect(url_for('admin_dashboard'))


# Edit word
@app.route('/edit_word/<int:word_id>', methods=['GET', 'POST'])
@login_required
def edit_word(word_id):
    if session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM words WHERE id=%s", (word_id,))
    word_data = cur.fetchone()

    if not word_data:
        flash("Word not found.", "warning")
        cur.close()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        pronunciation = request.form.get('pronunciation', '').strip()
        part_of_speech = request.form.get('part_of_speech', '').strip()
        definition = request.form.get('definition', '').strip()
        example = request.form.get('example', '').strip()
        audio_file = request.form.get('audio_file', '').strip()

        cur.execute("""
            UPDATE words
            SET pronunciation=%s, part_of_speech=%s, definition=%s, example=%s, audio_file=%s
            WHERE id=%s
        """, (pronunciation, part_of_speech, definition, example, audio_file, word_id))
        conn.commit()
        cur.close()
        conn.close()

        flash(f"Word '{word_data['word']}' updated successfully.", "success")
        return redirect(url_for('admin_dashboard'))

    cur.close()
    conn.close()
    return render_template('edit_word.html', word=word_data)

# Delete word
@app.route('/delete_word/<int:word_id>', methods=['POST'])
@login_required
def delete_word(word_id):
    if session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM words WHERE id=%s", (word_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash("Word deleted successfully!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/twi_quiz/<topic>')
@login_required
def twi_quiz(topic):
    # Load questions for this topic
    questions = load_questions(topic)  # adjust to your function name

    if not questions:
        return redirect(url_for('twi_quiz_topics'))

    return render_template('twi_quiz.html', topic=topic, questions=questions)


@app.route('/twi_quiz_home')
@login_required
def twi_quiz_home():
    topics = get_all_twi_topics()

    topic_has_audio = {}
    topic_questions = {}

    # Loop through topics and check audio + question count
    for topic in topics:
        topic_has_audio[topic] = has_audio_for_topic(topic)  # returns True/False
        topic_questions[topic] = count_questions_for_topic(topic)  # returns integer

    return render_template(
        'twi_quiz_home.html',
        topics=topics,
        topic_has_audio=topic_has_audio,
        topic_questions=topic_questions
    )

@app.route('/score_dashboard')
@login_required
def score_dashboard():
    ...

# -------------------------------
# Dictionary
# -------------------------------
@app.route('/dictionary', methods=['GET', 'POST'])
def dictionary():
    if 'username' not in session:
        flash("Please log in to access the dictionary.", "warning")
        return redirect(url_for('login'))

    search_results = []
    search_word = None

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch all words for the main grid
    cur.execute("""
        SELECT id, word, pronunciation, part_of_speech, definition, example, audio_file
        FROM words
        ORDER BY word
    """)
    words = cur.fetchall()

    # Search logic
    if request.method == 'POST':
        search_word = request.form['word'].strip()
        cur.execute("""
            SELECT id, word, pronunciation, part_of_speech, definition, example, audio_file
            FROM words
            WHERE word ILIKE %s
            ORDER BY word
        """, (f"%{search_word}%",))
        search_results = cur.fetchall()

        if search_results:
            # Move exact match to the top
            exact_match = None
            other_results = []
            for w in search_results:
                if w['word'].lower() == search_word.lower():
                    exact_match = w
                else:
                    other_results.append(w)
            search_results = [exact_match] + other_results if exact_match else other_results
        else:
            flash(f"No results found for '{search_word}'", "warning")

    cur.close()
    conn.close()

    return render_template(
        'dictionary.html',
        words=words,
        search_results=search_results,
        search_word=search_word
    )

@app.route('/word/<int:word_id>')
def word_detail(word_id):
    if 'username' not in session:
        flash("Please log in to access the dictionary.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT word, pronunciation, part_of_speech, definition, example, audio_file
        FROM words
        WHERE id = %s
    """, (word_id,))
    word = cur.fetchone()
    cur.close()
    conn.close()

    if not word:
        flash("Word not found.", "warning")
        return redirect(url_for('dictionary'))

    return render_template('word_detail.html', word=word)

@app.route('/add_word', methods=['POST'])
def add_word():
    if session.get('role') != 'admin':
        flash("Only admins can add words.", "danger")
        return redirect(url_for('login'))

    word = request.form['word'].strip()
    pronunciation = request.form.get('pronunciation', '').strip()
    part_of_speech = request.form.get('part_of_speech', '').strip()
    definition = request.form.get('definition', '').strip()
    example = request.form.get('example', '').strip()
    audio_file = request.form.get('audio_file', '').strip()

    if not word or not definition:
        flash("Word and definition are required.", "warning")
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO words (word, pronunciation, part_of_speech, definition, example, audio_file)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (word, pronunciation, part_of_speech, definition, example, audio_file))
    conn.commit()
    cur.close()
    conn.close()

    flash(f"'{word}' added successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# -------------------------------
# Section 5: Public Routes
# -------------------------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not message:
        flash("All fields are required.", "error")
        return redirect(url_for('contact'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contact_messages (name, email, message) VALUES (%s, %s, %s)",
                (name, email, message)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash("Error sending message.", "error")
        print("DB insert error:", e)
    finally:
        conn.close()

    flash("Your message has been sent successfully!", "success")
    return redirect(url_for('contact'))

# -------------------------------
# Section 6: Run App
# -------------------------------
if __name__ == '__main__':
    # Use environment variables if set, otherwise default to localhost:5000
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True") == "True"

    app.run(host=host, port=port, debug=debug)

