from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
import os, json, re, urllib.request, urllib.parse, secrets
from datetime import datetime
from functools import wraps
from database import (
    init_db, db_session, Exam, Question, Attempt, SiteMetric, QuestionStat, User,
    increment_visitors, record_question_stat, generate_revision_mock,
    generate_topic_drill, get_topic_mastery_list, get_cutoff_prediction,
    get_or_create_user, create_or_update_mock, update_mock_metadata,
    delete_mock_by_id, get_admin_dashboard_stats
)

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'exammatrix-secret-key-prod-2026')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_PAGES_DIR = os.path.join(BASE_DIR, 'static', 'Mock_Pages')
ADMIN_DIR = os.path.join(BASE_DIR, 'static', 'admin')
os.makedirs(MOCK_PAGES_DIR, exist_ok=True)
os.makedirs(ADMIN_DIR, exist_ok=True)

# Admin & OAuth Configuration
ADMIN_SECRET_KEY = os.environ.get('EXAMMATRIX_ADMIN_KEY', 'admin123')
ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', 'admin@exammatrix.com,mohit@exammatrix.com').split(',') if e.strip()]
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Initialize database on application start
init_db()

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

def is_admin_authorized():
    """Checks if request is authorized as admin via session, secret key header, or payload."""
    if session.get('is_admin') is True:
        return True
    header_key = request.headers.get('X-Admin-Key')
    if header_key and header_key.strip() == ADMIN_SECRET_KEY:
        return True
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if payload.get('adminKey') and str(payload.get('adminKey')).strip() == ADMIN_SECRET_KEY:
            return True
    return False

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_authorized():
            return jsonify({"error": "Admin access required. Please authenticate with admin credentials."}), 403
        return f(*args, **kwargs)
    return decorated_function

def extract_questions_from_payload(payload):
    """
    Intelligently extracts the list of questions whether passed as:
    1. A raw JSON string in payload['questionsJson']
    2. A list in payload['questions']
    3. An object with a nested list: {"questions": [...]} or {"exam": ..., "questions": [...]}
    """
    raw = payload.get('questionsJson') or payload.get('questions')
    if isinstance(raw, str):
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
        except Exception as e:
            raise ValueError(f"Invalid JSON syntax in questions set: {str(e)}")
    else:
        parsed = raw

    if isinstance(parsed, dict):
        if 'questions' in parsed and isinstance(parsed['questions'], list):
            return parsed['questions']
        elif 'data' in parsed and isinstance(parsed['data'], list):
            return parsed['data']
        else:
            raise ValueError("Pasted JSON object must contain a 'questions' array.")
    elif isinstance(parsed, list):
        return parsed
    else:
        raise ValueError("Provided questions must be a JSON array of questions or an object with a 'questions' key.")

# ==================== PUBLIC & PAGE ROUTES ====================

@app.route('/')
def home():
    """Serve main ExamMatrix IT Dashboard"""
    return send_from_directory(os.path.join('static', 'Dashboard'), 'index.html')

@app.route('/player')
def exam_player():
    """Serve Unified Exam Player Engine"""
    return send_from_directory(os.path.join('static', 'player'), 'index.html')

@app.route('/admin')
def admin_page():
    """Serve Admin Management Portal"""
    return send_from_directory(os.path.join('static', 'admin'), 'index.html')

@app.route('/Mock_Pages/<path:filename>')
def serve_quiz(filename):
    """Legacy route for backwards compatibility"""
    return send_from_directory(MOCK_PAGES_DIR, filename)

# ==================== AUTHENTICATION & OAUTH ====================

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Returns current user's anonymous profile (never leaks email to frontend)"""
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    if not user_id:
        return jsonify({"authenticated": False, "user": None, "isAdmin": False})

    session_db = db_session()
    user = session_db.query(User).filter_by(id=user_id).first()
    if not user:
        session.clear()
        return jsonify({"authenticated": False, "user": None, "isAdmin": False})

    user_dict = user.to_dict(include_private=False)
    return jsonify({
        "authenticated": True,
        "user": user_dict,
        "isAdmin": bool(user.is_admin or is_admin)
    })

@app.route('/api/auth/logout', methods=['POST', 'GET'])
def logout_user():
    session.clear()
    return jsonify({"success": True, "message": "Successfully signed out."})

@app.route('/api/auth/demo-login', methods=['POST'])
def demo_login():
    """
    Seamless One-Click Login for immediate local testing & evaluation.
    Provides instant anonymous candidate sign-in or admin credential verification.
    """
    payload = request.get_json(silent=True) or {}
    role = payload.get('role', 'candidate').lower()
    session_db = db_session()

    if role == 'admin':
        admin_key = payload.get('adminKey', '')
        if str(admin_key).strip() != ADMIN_SECRET_KEY:
            return jsonify({"error": "Invalid Admin Secret Key."}), 401
        
        admin_user = get_or_create_user(session_db, 'admin@exammatrix.com', is_admin=True)
        session['user_id'] = admin_user.id
        session['is_admin'] = True
        return jsonify({
            "authenticated": True,
            "user": admin_user.to_dict(include_private=False),
            "isAdmin": True,
            "message": "Authenticated as Admin."
        })

    # Default: Anonymous Candidate
    candidate_id = payload.get('candidateId') or secrets.token_hex(4)
    email = f"candidate_{candidate_id}@exammatrix.local"
    user = get_or_create_user(session_db, email, is_admin=False)
    session['user_id'] = user.id
    session['is_admin'] = bool(user.is_admin)

    return jsonify({
        "authenticated": True,
        "user": user.to_dict(include_private=False),
        "isAdmin": bool(user.is_admin),
        "message": f"Welcome, {user.anonymous_name}! Your identity is 100% anonymous."
    })

@app.route('/api/auth/verify-admin-key', methods=['POST'])
def verify_admin_key_endpoint():
    """Elevates current session to Admin if valid Admin Secret Key is provided."""
    payload = request.get_json(silent=True) or {}
    key = str(payload.get('adminKey', '')).strip()
    if key != ADMIN_SECRET_KEY:
        return jsonify({"success": False, "error": "Invalid Admin Secret Key."}), 401

    session['is_admin'] = True
    user_id = session.get('user_id')
    if user_id:
        session_db = db_session()
        user = session_db.query(User).filter_by(id=user_id).first()
        if user:
            user.is_admin = True
            session_db.commit()

    return jsonify({"success": True, "isAdmin": True, "message": "Admin privileges granted."})

@app.route('/auth/google', methods=['GET'])
def google_oauth_login():
    """Initiates Google OAuth 2.0 Web Flow"""
    if not GOOGLE_CLIENT_ID:
        return redirect('/?auth_notice=gauth_unconfigured')

    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    redirect_uri = url_for('google_oauth_callback', _external=True)

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?" +
        urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "access_type": "offline",
            "prompt": "select_account"
        })
    )
    return redirect(google_auth_url)

@app.route('/auth/google/callback', methods=['GET'])
def google_oauth_callback():
    """Handles Google OAuth 2.0 Token Exchange and Anonymous User Assignment"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        return redirect('/?auth_error=cancelled')

    redirect_uri = url_for('google_oauth_callback', _external=True)
    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_payload = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }).encode('utf-8')

        req = urllib.request.Request(token_url, data=token_payload, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read().decode('utf-8'))

        access_token = token_data.get("access_token")
        if not access_token:
            return redirect('/?auth_error=token_failed')

        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        u_req = urllib.request.Request(userinfo_url)
        u_req.add_header("Authorization", f"Bearer {access_token}")
        with urllib.request.urlopen(u_req, timeout=10) as u_resp:
            user_info = json.loads(u_resp.read().decode('utf-8'))

        email = user_info.get('email', '').lower()
        sub = user_info.get('sub')
        if not email:
            return redirect('/?auth_error=no_email')

        is_admin = email in ADMIN_EMAILS
        session_db = db_session()
        user = get_or_create_user(session_db, email, google_id=sub, is_admin=is_admin)

        session['user_id'] = user.id
        session['is_admin'] = bool(user.is_admin)

        return redirect('/?login_success=1')
    except Exception as e:
        print(f"Google OAuth Callback Error: {e}")
        return redirect('/?auth_error=server_error')

# ==================== ADMIN MANAGEMENT PORTAL API ====================

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats():
    """Returns overview statistics across all exams, questions, users and attempts."""
    session_db = db_session()
    try:
        data = get_admin_dashboard_stats(session_db)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/exams', methods=['GET'])
@admin_required
def get_admin_exams():
    """Returns detailed mock ledger for admin management."""
    session_db = db_session()
    try:
        exams = session_db.query(Exam).order_by(Exam.day.asc()).all()
        result = []
        for ex in exams:
            att_count = session_db.query(Attempt).filter_by(exam_id=ex.id).count()
            d = ex.to_dict()
            d["attemptsCount"] = att_count
            result.append(d)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/exams/create', methods=['POST'])
@admin_required
def create_mock_from_admin():
    """
    Accepts mock metadata + 50-Question JSON set.
    Automatically parses, validates, and creates:
    1. SQLite Exam and 50 Question records in app.db
    2. Synchronized data/quizzes/day_X.json file
    3. Updated manifest.json registry
    """
    payload = request.get_json(silent=True) or {}
    session_db = db_session()

    try:
        day = payload.get('day')
        if day is None:
            # Auto-assign next day
            max_day = session_db.query(Exam.day).order_by(Exam.day.desc()).first()
            day = (max_day[0] + 1) if max_day else 1
        day = int(day)

        title = payload.get('title') or f"IT Officer Mains: Day {day}"
        difficulty = payload.get('difficulty') or "Moderate"
        difficulty_level = int(payload.get('difficultyLevel', 2))
        tags = payload.get('tags') or "Balanced"
        time_limit = int(payload.get('timeLimitMinutes', 40))

        questions = extract_questions_from_payload(payload)
        if not questions:
            return jsonify({"error": "No questions were found in the provided JSON."}), 400

        mock_data = {
            "day": day,
            "title": title,
            "difficulty": difficulty,
            "difficultyLevel": difficulty_level,
            "tags": tags,
            "timeLimitMinutes": time_limit,
            "questions": questions
        }

        created_exam = create_or_update_mock(session_db, mock_data)

        return jsonify({
            "success": True,
            "message": f"Mock Day {day} published successfully with {len(questions)} questions!",
            "exam": created_exam
        })

    except ValueError as ve:
        return jsonify({"error": f"Validation Error: {str(ve)}"}), 400
    except Exception as e:
        session_db.rollback()
        print(f"Error creating mock: {e}")
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

@app.route('/api/admin/exams/<exam_id>', methods=['PUT', 'POST', 'DELETE'])
@admin_required
def modify_mock(exam_id):
    """Admin endpoint to edit metadata or delete a mock."""
    session_db = db_session()
    clean_id = exam_id.replace('.html', '').replace('.json', '').lower()

    if request.method == 'DELETE':
        success = delete_mock_by_id(session_db, clean_id)
        if success:
            return jsonify({"success": True, "message": f"Exam '{clean_id}' deleted successfully."})
        return jsonify({"error": f"Exam '{clean_id}' not found."}), 404

    # Update metadata
    payload = request.get_json(silent=True) or {}
    updated = update_mock_metadata(session_db, clean_id, payload)
    if updated:
        return jsonify({"success": True, "exam": updated, "message": "Mock details updated."})
    return jsonify({"error": f"Exam '{clean_id}' not found."}), 404

# ==================== QUIZ & PLAYER APIS ====================

@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
    session_db = db_session()
    try:
        exams = session_db.query(Exam).order_by(Exam.day).all()
        return jsonify([exam.to_dict() for exam in exams])
    except Exception as e:
        print(f"Error fetching quizzes from DB: {e}")
        return jsonify([]), 500

@app.route('/api/quizzes/<quiz_id>', methods=['GET'])
def get_quiz_detail(quiz_id):
    clean_id = quiz_id.replace('.html', '').replace('.json', '').lower()
    include_answers = request.args.get('include_answers', 'true').lower() == 'true'
    
    session_db = db_session()
    try:
        if clean_id == 'revision':
            limit = int(request.args.get('limit', 50))
            rev_mock = generate_revision_mock(session_db, limit=limit)
            return jsonify(rev_mock)
        
        if clean_id.startswith('drill'):
            topic = request.args.get('topic', 'Database Systems')
            count = int(request.args.get('count', 15))
            drill_mock = generate_topic_drill(session_db, topic, count=count)
            return jsonify(drill_mock)

        exam = session_db.query(Exam).filter_by(id=clean_id).first()
        if not exam:
            match = re.search(r'\d+', clean_id)
            if match:
                day_num = int(match.group())
                exam = session_db.query(Exam).filter_by(day=day_num).first()

        if exam:
            return jsonify(exam.to_dict(include_questions=True, include_answers=include_answers))
        
        return jsonify({"error": f"Exam '{quiz_id}' not found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/quizzes/<quiz_id>/submit', methods=['POST'])
def submit_quiz_evaluation(quiz_id):
    clean_id = quiz_id.replace('.html', '').replace('.json', '').lower()
    payload = request.get_json(silent=True) or {}
    user_answers = payload.get('answers', [])
    question_db_ids = payload.get('questionDbIds', [])
    time_taken = payload.get('timeTakenSeconds', 0)
    drill_topic = payload.get('drillTopic', '')
    user_id = session.get('user_id')

    session_db = db_session()
    try:
        exam_title = ""
        exam_day = 0
        questions = []

        if question_db_ids:
            questions = [session_db.query(Question).filter_by(id=qid).first() for qid in question_db_ids]
            questions = [q for q in questions if q is not None]
            if clean_id.startswith('drill'):
                exam_title = f"Topic Drill: {drill_topic or 'Targeted Practice'}"
            elif clean_id == 'revision':
                exam_title = "IT Officer Mains: Adaptive Revision Mock"
            else:
                exam_title = payload.get('quizTitle', 'Custom Assessment')
        else:
            exam = session_db.query(Exam).filter_by(id=clean_id).first()
            if not exam:
                match = re.search(r'\d+', clean_id)
                if match:
                    exam = session_db.query(Exam).filter_by(day=int(match.group())).first()

            if not exam and clean_id == 'revision':
                rev = generate_revision_mock(session_db, 50)
                q_ids = [q['db_id'] for q in rev['questions']]
                questions = [session_db.query(Question).filter_by(id=qid).first() for qid in q_ids]
                exam_title = "IT Officer Mains: Adaptive Revision Mock"
            elif exam:
                questions = exam.questions
                exam_title = exam.title
                exam_day = exam.day
            else:
                return jsonify({"error": f"Exam '{quiz_id}' not found."}), 404

        total_q = len(questions)

        if isinstance(user_answers, dict):
            raw_answers = [None] * total_q
            for k, v in user_answers.items():
                try:
                    idx = int(k)
                    if 0 <= idx < total_q:
                        raw_answers[idx] = v
                except Exception:
                    pass
            user_answers = raw_answers
        elif len(user_answers) < total_q:
            user_answers = list(user_answers) + [None] * (total_q - len(user_answers))
        else:
            user_answers = list(user_answers)[:total_q]

        correct_count = 0
        wrong_count = 0
        skipped_count = 0
        topic_stats = {}
        wrong_log = []
        skipped_log = []
        playable_mistakes = []
        answer_keys = []

        for idx, q in enumerate(questions):
            topic = q.topic or 'General'
            if topic not in topic_stats:
                topic_stats[topic] = {"total": 0, "correct": 0, "wrong": 0, "skipped": 0}
            topic_stats[topic]["total"] += 1

            u_ans = user_answers[idx]
            opts = json.loads(q.options_json)

            q_full_data = {
                "id": idx + 1,
                "db_id": q.id,
                "topic": q.topic,
                "text": q.text,
                "options": opts,
                "correct": q.correct,
                "explanation": q.explanation
            }
            answer_keys.append({
                "qNum": idx + 1,
                "correct": q.correct,
                "explanation": q.explanation
            })

            if u_ans is None:
                skipped_count += 1
                topic_stats[topic]["skipped"] += 1
                skipped_log.append({"qNum": idx + 1, "topic": topic, "text": q.text})
                playable_mistakes.append(q_full_data)
                record_question_stat(session_db, q.id, 'skipped')
            elif u_ans == q.correct:
                correct_count += 1
                topic_stats[topic]["correct"] += 1
                record_question_stat(session_db, q.id, 'correct')
            else:
                wrong_count += 1
                topic_stats[topic]["wrong"] += 1
                user_ans_text = opts[u_ans] if (0 <= u_ans < len(opts)) else "Invalid"
                correct_ans_text = opts[q.correct] if (0 <= q.correct < len(opts)) else ""
                wrong_log.append({
                    "qNum": idx + 1,
                    "topic": topic,
                    "text": q.text,
                    "userAnswer": user_ans_text,
                    "correctAnswer": correct_ans_text
                })
                playable_mistakes.append(q_full_data)
                record_question_stat(session_db, q.id, 'incorrect')

        raw_score = (correct_count * 2.0) - (wrong_count * 0.5)
        score = max(0.0, round(raw_score, 2))
        attempted = correct_count + wrong_count
        accuracy = round((correct_count / attempted) * 100) if attempted > 0 else 0

        attempt = Attempt(
            user_id=user_id,
            exam_id=clean_id,
            exam_title=exam_title,
            exam_day=exam_day,
            score=score,
            correct_count=correct_count,
            incorrect_count=wrong_count,
            skipped_count=skipped_count,
            total_questions=total_q,
            accuracy=accuracy,
            time_taken_seconds=time_taken,
            date=datetime.utcnow(),
            answers_json=json.dumps(user_answers),
            topic_breakdown_json=json.dumps(topic_stats),
            wrong_questions_json=json.dumps(wrong_log),
            skipped_questions_json=json.dumps(skipped_log),
            playable_mistakes_json=json.dumps(playable_mistakes)
        )
        session_db.add(attempt)
        session_db.commit()

        response_data = attempt.to_dict()
        response_data["answerKeys"] = answer_keys
        return jsonify(response_data)

    except Exception as e:
        session_db.rollback()
        print(f"Error evaluating exam: {e}")
        return jsonify({"error": f"Evaluation error: {str(e)}"}), 500

@app.route('/api/topics/mastery', methods=['GET'])
def get_topic_mastery():
    session_db = db_session()
    try:
        data = get_topic_mastery_list(session_db)
        return jsonify(data)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/analytics/cutoff-predictor', methods=['GET'])
def get_cutoff_analytics():
    session_db = db_session()
    try:
        data = get_cutoff_prediction(session_db)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attempts', methods=['GET', 'DELETE'])
def manage_attempts():
    session_db = db_session()
    if request.method == 'DELETE':
        try:
            session_db.query(Attempt).delete()
            session_db.commit()
            return jsonify({"message": "All attempts deleted successfully."})
        except Exception as e:
            session_db.rollback()
            return jsonify({"error": str(e)}), 500

    try:
        attempts = session_db.query(Attempt).order_by(Attempt.date.asc()).all()
        return jsonify([a.to_dict() for a in attempts])
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    count = increment_visitors()
    return jsonify({"count": count})

if __name__ == '__main__':
    app.run(debug=False, port=5001)
