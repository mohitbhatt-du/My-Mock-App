from flask import Flask, jsonify, request, send_from_directory
import os, json, re
from datetime import datetime
from database import (
    init_db, db_session, Exam, Question, Attempt, SiteMetric, increment_visitors
)

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_PAGES_DIR = os.path.join(BASE_DIR, 'static', 'Mock_Pages')
os.makedirs(MOCK_PAGES_DIR, exist_ok=True)

# Initialize database on application start
init_db()

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

@app.route('/')
def home():
    """Serve main ExamMatrix IT Dashboard"""
    return send_from_directory(os.path.join('static', 'Dashboard'), 'index.html')

@app.route('/player')
def exam_player():
    """Serve Unified Exam Player Engine"""
    return send_from_directory(os.path.join('static', 'player'), 'index.html')

@app.route('/Mock_Pages/<path:filename>')
def serve_quiz(filename):
    """Legacy route for backwards compatibility"""
    return send_from_directory(MOCK_PAGES_DIR, filename)

# API: List all exams
@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
    session = db_session()
    try:
        exams = session.query(Exam).order_by(Exam.day).all()
        return jsonify([exam.to_dict() for exam in exams])
    except Exception as e:
        print(f"Error fetching quizzes from DB: {e}")
        return jsonify([]), 500

# API: Get single exam with questions
@app.route('/api/quizzes/<quiz_id>', methods=['GET'])
def get_quiz_detail(quiz_id):
    clean_id = quiz_id.replace('.html', '').replace('.json', '').lower()
    include_answers = request.args.get('include_answers', 'true').lower() == 'true'
    
    session = db_session()
    try:
        exam = session.query(Exam).filter_by(id=clean_id).first()
        if not exam:
            # Fallback by day number
            match = re.search(r'\d+', clean_id)
            if match:
                day_num = int(match.group())
                exam = session.query(Exam).filter_by(day=day_num).first()

        if exam:
            return jsonify(exam.to_dict(include_questions=True, include_answers=include_answers))
        
        return jsonify({"error": f"Exam '{quiz_id}' not found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Secure Server-Side Exam Submission & Evaluation
@app.route('/api/quizzes/<quiz_id>/submit', methods=['POST'])
def submit_quiz_evaluation(quiz_id):
    clean_id = quiz_id.replace('.html', '').replace('.json', '').lower()
    payload = request.get_json(silent=True) or {}
    user_answers = payload.get('answers', []) # Array of 0-based option index or null
    time_taken = payload.get('timeTakenSeconds', 0)

    session = db_session()
    try:
        exam = session.query(Exam).filter_by(id=clean_id).first()
        if not exam:
            match = re.search(r'\d+', clean_id)
            if match:
                exam = session.query(Exam).filter_by(day=int(match.group())).first()

        if not exam:
            return jsonify({"error": f"Exam '{quiz_id}' not found."}), 404

        questions = exam.questions
        total_q = len(questions)

        # Pad or slice user_answers
        if isinstance(user_answers, dict):
            # Format: {"0": 1, "1": 3, ...}
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
                "id": q.q_num,
                "topic": q.topic,
                "text": q.text,
                "options": opts,
                "correct": q.correct,
                "explanation": q.explanation
            }
            answer_keys.append({
                "qNum": q.q_num,
                "correct": q.correct,
                "explanation": q.explanation
            })

            if u_ans is None:
                skipped_count += 1
                topic_stats[topic]["skipped"] += 1
                skipped_log.append({"qNum": idx + 1, "topic": topic, "text": q.text})
                playable_mistakes.append(q_full_data)
            elif u_ans == q.correct:
                correct_count += 1
                topic_stats[topic]["correct"] += 1
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

        # Official IBPS scoring: +2.0 for correct, -0.5 penalty for incorrect
        raw_score = (correct_count * 2.0) - (wrong_count * 0.5)
        score = max(0.0, round(raw_score, 2))
        attempted = correct_count + wrong_count
        accuracy = round((correct_count / attempted) * 100) if attempted > 0 else 0

        # Persist Attempt in SQLite Database
        attempt = Attempt(
            exam_id=exam.id,
            exam_title=exam.title,
            exam_day=exam.day,
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
        session.add(attempt)
        session.commit()

        response_data = attempt.to_dict()
        response_data["answerKeys"] = answer_keys
        return jsonify(response_data)

    except Exception as e:
        session.rollback()
        print(f"Error evaluating exam: {e}")
        return jsonify({"error": f"Evaluation error: {str(e)}"}), 500

# API: Get All Attempts History (For Dashboard Persistence)
@app.route('/api/attempts', methods=['GET', 'DELETE'])
def manage_attempts():
    session = db_session()
    if request.method == 'DELETE':
        try:
            session.query(Attempt).delete()
            session.commit()
            return jsonify({"message": "All attempts deleted successfully."})
        except Exception as e:
            session.rollback()
            return jsonify({"error": str(e)}), 500

    # GET attempts
    try:
        attempts = session.query(Attempt).order_by(Attempt.date.asc()).all()
        return jsonify([a.to_dict() for a in attempts])
    except Exception as e:
        return jsonify([]), 500

# API: Atomic Visitor Counter
@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    count = increment_visitors()
    return jsonify({"count": count})

if __name__ == '__main__':
    app.run(debug=False, port=5001)
