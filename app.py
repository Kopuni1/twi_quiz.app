import os
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ ERROR: DATABASE_URL is not set!")
        return None

    try:
        # Parse the Render Postgres URL
        result = urlparse(db_url)

        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
            sslmode="require",      # Render requires SSL
            cursor_factory=psycopg2.extras.DictCursor
        )

        print("✅ Connected to Render PostgreSQL")
        return conn

    except Exception as e:
        print("❌ Database connection FAILED:", e)
        return None

from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("You must log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


from flask import g

@app.context_processor
def inject_unread_count():
    unread_count = 0
    if session.get('username') == 'kwadwo':
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM contact_messages WHERE is_read = FALSE")
                unread_count = cur.fetchone()[0]
        finally:
            conn.close()
    return dict(unread_count=unread_count)

# ----------------------------
# SAVE QUIZ HISTORY FUNCTION
# ----------------------------
def save_quiz_history(username, category, score, total_questions, time_taken):
    """
    Saves one quiz result row into quiz_history.
    Assumes your table has columns:
      id, username, category, score, total_questions, date_played, date_taken, time_taken
    Writes:
      - date_played = current date
      - date_taken = current timestamp (NOW())
      - time_taken = integer seconds
    """
    conn = get_db_connection()
    if conn is None:
        print("Database connection failed.")
        return False

    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO quiz_history
            (username, category, score, total_questions, date_played, date_taken, time_taken)
            VALUES (%s, %s, %s, %s, CURRENT_DATE, NOW(), %s)
        """, (username, category, score, total_questions, time_taken))
        conn.commit()
        return True
    except Exception as e:
        # log for debugging but don't raise so user flow is not broken
        print("Error saving quiz history:", e)
        return False
    finally:
        cur.close()
        conn.close()


# -------------------------------
# Home Page
# -------------------------------
@app.route('/')
def home():
    return render_template('home.html')

# -------------------------------
# Sign-Up
# -------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing_user = cur.fetchone()
        if existing_user:
            flash("Username already exists.", "error")
            return redirect(url_for('signup'))

        cur.execute("INSERT INTO users (username, password, role) VALUES (%s,%s,%s)", (username, password, 'user'))
        conn.commit()
        cur.close()
        conn.close()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('signup.html')

# -------------------------------
# Login
# -------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
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

# -------------------------------
# Logout
# -------------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))

# -------------------------------
# User Dashboard
# -------------------------------
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    today = date.today()   # <-- FIXED

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
def admin_dashboard():
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT username, role FROM users ORDER BY username")
    users = cur.fetchall()

    cur.execute("SELECT word, pronunciation, part_of_speech, definition, example, audio_file FROM words ORDER BY word")
    words = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('admin_dashboard.html', username=session['username'], users=users, words=words)

# -------------------------------
# Admin User Management
# -------------------------------
@app.route('/change_role/<username>', methods=['POST'])
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

@app.route('/delete_user/<username>', methods=['POST'])
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

# -------------------------------
# Admin: Add Question
# -------------------------------
@app.route('/admin/questions/edit/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM quiz_questions WHERE id=%s", (question_id,))
    question = cur.fetchone()

    if not question:
        flash("Question not found.", "warning")
        cur.close()
        conn.close()
        return redirect(url_for('view_all_questions'))

    if request.method == 'POST':
        # Retrieve all fields safely
        category = request.form.get('category', '').strip()
        q_text = request.form.get('question', '').strip()
        option_a = request.form.get('option_a', '').strip()
        option_b = request.form.get('option_b', '').strip()
        option_c = request.form.get('option_c', '').strip()
        option_d = request.form.get('option_d', '').strip()
        correct_option = request.form.get('correct_option', '').strip().upper()
        difficulty = request.form.get('difficulty', 'medium').strip()
        audio_filename = request.form.get('audio_filename', '').strip()

        # Validate required fields
        if not category or not q_text or not option_a or not option_b or not option_c or not option_d:
            flash("Please fill in all required fields.", "danger")
            return redirect(request.url)

        # Validate correct_option
        if correct_option not in ['A', 'B', 'C', 'D']:
            flash("Please select a valid correct option (A, B, C, D).", "danger")
            return redirect(request.url)

        # Update the database
        cur.execute("""
            UPDATE quiz_questions
            SET category=%s, question=%s, option_a=%s, option_b=%s, option_c=%s, option_d=%s,
                correct_option=%s, difficulty=%s, audio_filename=%s
            WHERE id=%s
        """, (category, q_text, option_a, option_b, option_c, option_d,
              correct_option, difficulty, audio_filename, question_id))
        conn.commit()
        cur.close()
        conn.close()

        flash("Question updated successfully!", "success")
        return redirect(url_for('view_all_questions'))

    cur.close()
    conn.close()
    return render_template('admin/edit_question.html', question=question)


@app.route('/admin/questions/add', methods=['GET', 'POST'])
def add_question():
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get fields safely
        category = request.form.get('category', '').strip()
        q_text = request.form.get('question', '').strip()
        option_a = request.form.get('option_a', '').strip()
        option_b = request.form.get('option_b', '').strip()
        option_c = request.form.get('option_c', '').strip()
        option_d = request.form.get('option_d', '').strip()
        correct_option = request.form.get('correct_option', '').strip().upper()
        difficulty = request.form.get('difficulty', 'medium').strip()
        audio_filename = request.form.get('audio_filename', '').strip()

        # Validate required fields
        if not category or not q_text or not option_a or not option_b or not option_c or not option_d:
            flash("Please fill in all required fields.", "danger")
            return redirect(request.url)

        if correct_option not in ['A', 'B', 'C', 'D']:
            flash("Please select a valid correct option (A, B, C, D).", "danger")
            return redirect(request.url)

        # Insert into DB
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO quiz_questions
            (category, question, option_a, option_b, option_c, option_d, correct_option, difficulty, audio_filename)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (category, q_text, option_a, option_b, option_c, option_d, correct_option, difficulty, audio_filename))
        conn.commit()
        cur.close()
        conn.close()

        flash("Question added successfully!", "success")
        return redirect(url_for('view_all_questions'))

    return render_template('admin/add_question.html')

# -------------------------------
# Admin: Delete Question
# -------------------------------
@app.route('/admin/questions/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quiz_questions WHERE id=%s", (question_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash("Question deleted successfully!", "success")
    return redirect(url_for('view_all_questions'))

@app.route('/admin/manage_questions')
def manage_questions_all():
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch all categories
    cur.execute("SELECT DISTINCT category FROM quiz_questions ORDER BY category")
    categories = [row['category'] for row in cur.fetchall()]

    # Fetch questions grouped by category
    questions_by_category = {}
    for cat in categories:
        cur.execute("SELECT * FROM quiz_questions WHERE category=%s ORDER BY id ASC", (cat,))
        questions_by_category[cat] = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'admin/manage_questions_all.html',
        username=session['username'],
        questions_by_category=questions_by_category
    )

# -------------------------------
# Admin: View All Questions
# -------------------------------
@app.route('/admin/view_all_questions')
def view_all_questions():
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM quiz_questions ORDER BY category, id")
    questions = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('admin/view_all_questions.html', questions=questions)


@app.route('/score_dashboard')
@login_required
def score_dashboard():
    username = session['username']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT category, score, total_questions, date_taken, time_taken
        FROM quiz_history
        WHERE username = %s
        ORDER BY date_taken ASC, time_taken ASC
    """, (username,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Convert tuples → dictionaries for easier use in Jinja
    records = []
    for row in rows:
        records.append({
            "category": row[0],
            "score": row[1],
            "total_questions": row[2],
            "date_taken": row[3].strftime("%Y-%m-%d"),
            "time_taken": str(row[4])
        })

    return render_template("score_dashboard.html", records=records)

# -------------------------------
# Gamezone and Quizzes
# -------------------------------
@app.route('/gamezone')
def gamezone():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('gamezone.html')

# Scrabble
@app.route('/scrabble')
@login_required
def scrabble():
    return render_template("scrabble.html")

# ------------------------
# ONE-BY-ONE QUIZ ROUTE
# ------------------------
from flask import session, flash, redirect, url_for, render_template, request
from datetime import datetime
import random
import psycopg2.extras

def normalize(text):
    """Normalize text for comparison."""
    if not text:
        return ""
    return text.strip().lower().replace("\u200b", "")  # remove zero-width space

@app.route('/quiz/<category>', methods=['GET', 'POST'])
@login_required
def quiz(category):
    """
    One-by-one quiz with audio support and shuffled options.
    """
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for('gamezone'))

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, question, option_a, option_b, option_c, option_d, correct_option, audio_filename
        FROM quiz_questions
        WHERE category=%s
        ORDER BY id ASC
    """, (category,))
    questions_db = cur.fetchall()
    cur.close()
    conn.close()

    if not questions_db:
        flash(f"No questions available for '{category}'.", "warning")
        return redirect(url_for('twi_quiz_home'))

    # Initialize quiz session if new or category changed
    if 'quiz_questions' not in session or session.get('current_category') != category:
        prepared = []
        for q in questions_db:
            options = [
                {"key": "A", "text": q["option_a"]},
                {"key": "B", "text": q["option_b"]},
                {"key": "C", "text": q["option_c"]},
                {"key": "D", "text": q["option_d"]}
            ]

            # Determine correct answer text
            correct_letter = (q.get('correct_option') or 'A').strip().upper()
            correct_text = q.get(f"option_{correct_letter.lower()}", "").strip()

            # Shuffle options
            random.shuffle(options)

            prepared.append({
                "id": q["id"],
                "question": q["question"],
                "options": options,
                "answer_text": correct_text,  # For checking
                "audio_file": q.get("audio_filename")  # Audio
            })

        session['quiz_questions'] = prepared
        session['q_index'] = 0
        session['score'] = 0
        session['current_category'] = category
        session['quiz_start_time'] = datetime.now().isoformat()

    # Load current question
    questions = session['quiz_questions']
    q_index = session['q_index']
    score = session['score']
    total_questions = len(questions)

    # Safety: if index out-of-range, redirect home
    if q_index >= total_questions:
        session.pop('quiz_questions', None)
        session.pop('q_index', None)
        session.pop('score', None)
        session.pop('current_category', None)
        session.pop('quiz_start_time', None)
        return redirect(url_for('twi_quiz_home'))

    question = questions[q_index]

    if request.method == 'POST':
        selected_text = request.form.get(f"question-{question['id']}")
        if selected_text and question['answer_text'] and \
           normalize(selected_text) == normalize(question['answer_text']):
            score += 1

        session['score'] = score
        session['q_index'] = q_index + 1

        if session['q_index'] >= total_questions:
            # Quiz finished
            start_time = datetime.fromisoformat(session.get('quiz_start_time'))
            time_taken = (datetime.now() - start_time).seconds
            final_score = session.pop('score', 0)
            session.pop('q_index', None)
            session.pop('quiz_questions', None)
            session.pop('quiz_start_time', None)
            session.pop('current_category', None)

            completed = session.get('completed_quizzes', [])
            if category not in completed:
                completed.append(category)
            session['completed_quizzes'] = completed

            save_quiz_history(session.get('username'), category, final_score, total_questions, time_taken)

            flash(f"You completed the '{category}' quiz! Score: {final_score}/{total_questions}", "success")
            return redirect(url_for('twi_quiz_home'))

        else:
            return redirect(url_for('quiz', category=category))

    # GET: render current question
    return render_template(
        "quiz_one_by_one.html",
        question=question,
        q_index=q_index,
        total_questions=total_questions,
        category=category
    )

# -------------------------------
# Twi Quiz Home (List of Topics)
# -------------------------------
@app.route('/twi_quiz')
@login_required
def twi_quiz_home():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch all categories
    cur.execute("SELECT DISTINCT category FROM quiz_questions")
    categories_db = cur.fetchall()
    categories = [row['category'] for row in categories_db]

    topic_questions = {}
    topic_has_audio = {}

    for category in categories:
        # Count questions
        cur.execute("SELECT COUNT(*) FROM quiz_questions WHERE category=%s", (category,))
        topic_questions[category] = cur.fetchone()[0]

        # Check if category has at least one audio question
        cur.execute("""
            SELECT COUNT(*) FROM quiz_questions
            WHERE category=%s AND audio_filename IS NOT NULL AND audio_filename <> ''
        """, (category,))
        topic_has_audio[category] = cur.fetchone()[0] > 0

    cur.close()
    conn.close()

    return render_template(
        'twi_quiz_home.html',
        topics=categories,
        topic_questions=topic_questions,
        topic_has_audio=topic_has_audio
    )


@app.route('/quiz/<topic>', methods=['GET', 'POST'])
def twi_quiz(topic):
    if 'username' not in session:
        flash("Please log in to access the quiz.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT id, question, option_a, option_b, option_c, option_d, 
               correct_option, audio_filename
        FROM quiz_questions
        WHERE category = %s
        ORDER BY id
    """, (topic,))
    rows = cur.fetchall()

    # Convert to normal Python dicts
    questions = [dict(q) for q in rows]

    # Debug print (check terminal!)
    print("\n--- QUESTIONS LOADED ---")
    for q in questions:
        print(f"ID {q['id']} | audio = {q.get('audio_filename')}")

    cur.close()
    conn.close()

    return render_template('twi_quiz.html', questions=questions, topic=topic)


@app.route('/quiz_history')
def quiz_history():
    if 'username' not in session:
        flash("Please log in to view your quiz history.", "warning")
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for('gamezone'))

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch quiz history for this user
    try:
        cur.execute("""
            SELECT category, score, total_questions, time_taken, date_taken
            FROM quiz_history
            WHERE username = %s
            ORDER BY date_taken DESC
        """, (username,))
        history_db = cur.fetchall()
    except psycopg2.errors.UndefinedColumn:
        # If the table has no date_taken column yet, fetch without it
        cur.execute("""
            SELECT category, score, total_questions, time_taken
            FROM quiz_history
            WHERE username = %s
            ORDER BY id DESC
        """, (username,))
        history_db = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    # Convert to list of dicts to work with template
    history = []
    for row in history_db:
        history.append({
            "category": row.get("category", "N/A"),
            "score": row.get("score", 0),
            "total_questions": row.get("total_questions", 0),
            "time_taken": row.get("time_taken", "N/A"),
            "date_taken": row.get("date_taken")  # can be None
        })

    return render_template("quiz_history.html", history=history)

# ============================
# ADMIN VIEW QUIZ HISTORY
# ============================
@app.route('/admin/quiz_history')
def admin_view_quiz_history():
    # Only admin (kwadwo) can access
    if session.get('username') != 'kwadwo':
        flash("Access denied.", "danger")
        return redirect(url_for('home'))

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 12
    offset = (page - 1) * per_page

    # Sorting
    sort = request.args.get('sort', 'date_taken')
    order = request.args.get('order', 'desc')

    allowed_cols = ["username", "category", "score",
                    "total_questions", "date_taken", "date_played"]

    # Prevent injection by validating column list
    if sort not in allowed_cols:
        sort = "date_taken"
    if order not in ["asc", "desc"]:
        order = "desc"

    # Filtering
    filter_user = request.args.get('user', '').strip()
    filter_category = request.args.get('category', '').strip()

    filters = []
    values = []

    if filter_user:
        filters.append("username ILIKE %s")
        values.append(f"%{filter_user}%")

    if filter_category:
        filters.append("category ILIKE %s")
        values.append(f"%{filter_category}%")

    where = " AND ".join(filters)
    if where:
        where = "WHERE " + where

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Count total
    cur.execute(f"SELECT COUNT(*) FROM quiz_history {where}", values)
    total_records = cur.fetchone()[0]

    # Main fetch query
    query = f"""
        SELECT id, username, category, score, total_questions,
               date_played, date_taken, time_taken
        FROM quiz_history
        {where}
        ORDER BY {sort} {order}
        LIMIT %s OFFSET %s
    """
    values.extend([per_page, offset])
    cur.execute(query, values)
    records = cur.fetchall()

    # =======================
    # Chart Data Preparation
    # =======================

    # 1. Score distribution
    cur.execute("SELECT score FROM quiz_history")
    all_scores = [row["score"] for row in cur.fetchall()]

    # 2. Category popularity
    cur.execute("""
        SELECT category, COUNT(*) AS count
        FROM quiz_history
        GROUP BY category ORDER BY count DESC
    """)
    category_rows = cur.fetchall()
    categories = [row["category"] for row in category_rows]
    category_counts = [row["count"] for row in category_rows]

    # 3. Average score per category
    cur.execute("""
        SELECT category, AVG(score)::numeric(10,2) AS avg_score
        FROM quiz_history
        GROUP BY category ORDER BY avg_score DESC
    """)
    avg_rows = cur.fetchall()
    avg_categories = [row["category"] for row in avg_rows]
    avg_scores = [float(row["avg_score"]) for row in avg_rows]

    # 4. Quizzes taken per day
    cur.execute("""
        SELECT date(date_taken) AS day, COUNT(*) AS count
        FROM quiz_history
        GROUP BY day ORDER BY day ASC
    """)
    day_rows = cur.fetchall()
    days = [row["day"].strftime("%Y-%m-%d") for row in day_rows]
    day_counts = [row["count"] for row in day_rows]

    cur.close()
    conn.close()

    total_pages = (total_records + per_page - 1) // per_page

    return render_template(
        "admin_quiz_history.html",
        records=records,
        page=page,
        total_pages=total_pages,
        sort=sort,
        order=order,
        filter_user=filter_user,
        filter_category=filter_category,
        # Chart data
        all_scores=all_scores,
        categories=categories,
        category_counts=category_counts,
        avg_categories=avg_categories,
        avg_scores=avg_scores,
        days=days,
        day_counts=day_counts
    )

@app.route('/delete_quiz_records', methods=['POST'])
def delete_quiz_records():
    # Single delete
    single_id = request.form.get('single_delete')
    if single_id:
        record = QuizRecord.query.get(single_id)
        if record:
            db.session.delete(record)
            db.session.commit()
            flash("Record deleted successfully.", "success")
        return redirect(url_for('admin_view_quiz_history'))

    # Multi-delete
    record_ids = request.form.getlist('record_ids')
    if record_ids:
        for rid in record_ids:
            record = QuizRecord.query.get(rid)
            if record:
                db.session.delete(record)
        db.session.commit()
        flash(f"{len(record_ids)} record(s) deleted successfully.", "success")
    else:
        flash("No records selected.", "warning")
    return redirect(url_for('admin_view_quiz_history'))

from flask import request, flash, redirect, url_for

from flask import request, flash, redirect, url_for, render_template
import psycopg2
import psycopg2.extras

@app.route('/send_message', methods=['POST'])
def send_message():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not message:
        flash("All fields are required.", "error")
        return redirect(url_for('contact'))

    conn = get_db_connection()         # your helper that returns psycopg2 connection
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contact_messages (name, email, message)
                VALUES (%s, %s, %s)
                """,
                (name, email, message)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Log the error as appropriate
        flash("An error occurred while sending your message. Please try again later.", "error")
        print("DB insert error:", e)
    finally:
        conn.close()

    flash("Your message has been sent successfully!", "success")
    return redirect(url_for('contact'))

import psycopg2
from psycopg2.extras import RealDictCursor

@app.route('/admin/messages')
def admin_messages():
    if session.get('username') != 'kwadwo':
        flash("Access denied.", "error")
        return redirect(url_for('home'))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM contact_messages ORDER BY created_at DESC")
            messages = cur.fetchall()  # each row is a dict now
    finally:
        conn.close()

    return render_template('admin_messages.html', messages=messages)

# ----------------------------
# Optional: Delete Message
# ----------------------------
@app.route('/admin/messages/delete/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    if session.get('username') != 'kwadwo':
        return redirect(url_for('home'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        conn.commit()
    finally:
        conn.close()

    flash("Message deleted successfully.", "success")
    return redirect(url_for('admin_messages'))

from flask import jsonify

@app.route('/admin/messages/mark_read/<int:message_id>', methods=['POST'])
def mark_read_ajax(message_id):
    if session.get('username') != 'kwadwo':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE contact_messages SET is_read = TRUE WHERE id = %s", (message_id,))
        conn.commit()

        # Return new unread count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM contact_messages WHERE is_read = FALSE")
            unread_count = cur.fetchone()[0]

    finally:
        conn.close()

    return jsonify({'unread_count': unread_count})

@app.route('/admin/messages/mark_unread/<int:message_id>', methods=['POST'])
def mark_unread_ajax(message_id):
    if session.get('username') != 'kwadwo':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE contact_messages SET is_read = FALSE WHERE id = %s", (message_id,))
        conn.commit()

        # Return new unread count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM contact_messages WHERE is_read = FALSE")
            unread_count = cur.fetchone()[0]

    finally:
        conn.close()

    return jsonify({'unread_count': unread_count})

@app.route('/admin/messages/delete_all', methods=['POST'])
def delete_all_messages():
    if session.get('username') != 'kwadwo':
        flash("Access denied.", "error")
        return redirect(url_for('home'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contact_messages")
        conn.commit()
    finally:
        conn.close()

    flash("All messages have been deleted.", "success")
    return redirect(url_for('admin_messages'))

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
# Edit Word
# -------------------------------
@app.route('/edit_word/<word>', methods=['GET', 'POST'])
def edit_word(word):
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch the word record
    cur.execute("SELECT * FROM words WHERE word=%s", (word,))
    word_data = cur.fetchone()

    if not word_data:
        flash("Word not found.", "warning")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        pronunciation = request.form.get('pronunciation')
        part_of_speech = request.form.get('part_of_speech')
        definition = request.form.get('definition')
        example = request.form.get('example')
        audio_file = request.form.get('audio_file')

        cur.execute("""
            UPDATE words
            SET pronunciation=%s, part_of_speech=%s, definition=%s, example=%s, audio_file=%s
            WHERE word=%s
        """, (pronunciation, part_of_speech, definition, example, audio_file, word))
        conn.commit()

        flash(f"Word '{word}' updated successfully.", "success")
        cur.close()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    cur.close()
    conn.close()
    return render_template('edit_word.html', word=word_data)

# -------------------------------
# Delete Word
# -------------------------------
@app.route('/delete_word/<word>', methods=['POST'])
def delete_word(word):
    if 'username' not in session or session.get('role') != 'admin':
        flash("Admins only.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM words WHERE word=%s", (word,))
    conn.commit()
    cur.close()
    conn.close()

    flash(f"Word '{word}' deleted successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# -------------------------------
# About
# -------------------------------
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# -------------------------------
# Run App
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True)








