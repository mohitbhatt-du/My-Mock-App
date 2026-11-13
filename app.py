from flask import Flask, jsonify, request, send_from_directory
import os, json, re
from datetime import datetime
from database import (
    init_db, db_session, Exam, Question, Attempt, SiteMetric, QuestionStat,
    increment_visitors, record_question_stat, generate_revision_mock,
    generate_topic_drill, get_topic_mastery_list, get_cutoff_prediction
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
        if clean_id == 'revision':
            limit = int(request.args.get('limit', 50))
            rev_mock = generate_revision_mock(session, limit=limit)
            return jsonify(rev_mock)
        
        if clean_id.startswith('drill'):
            topic = request.args.get('topic', 'Database Systems')
            count = int(request.args.get('count', 15))
            drill_mock = generate_topic_drill(session, topic, count=count)
            return jsonify(drill_mock)

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
    question_db_ids = payload.get('questionDbIds', []) # Optional list of Question.id for dynamic quizzes
    time_taken = payload.get('timeTakenSeconds', 0)
    drill_topic = payload.get('drillTopic', '')

    session = db_session()
    try:
        exam_title = ""
        exam_day = 0
        questions = []

        if question_db_ids:
            # Dynamic revision or drill quiz with specific question IDs
            questions = [session.query(Question).filter_by(id=qid).first() for qid in question_db_ids]
            questions = [q for q in questions if q is not None]
            if clean_id.startswith('drill'):
                exam_title = f"Topic Drill: {drill_topic or 'Targeted Practice'}"
            elif clean_id == 'revision':
                exam_title = "IT Officer Mains: Adaptive Revision Mock"
            else:
                exam_title = payload.get('quizTitle', 'Custom Assessment')
        else:
            exam = session.query(Exam).filter_by(id=clean_id).first()
            if not exam:
                match = re.search(r'\d+', clean_id)
                if match:
                    exam = session.query(Exam).filter_by(day=int(match.group())).first()

            if not exam and clean_id == 'revision':
                rev = generate_revision_mock(session, 50)
                q_ids = [q['db_id'] for q in rev['questions']]
                questions = [session.query(Question).filter_by(id=qid).first() for qid in q_ids]
                exam_title = "IT Officer Mains: Adaptive Revision Mock"
            elif exam:
                questions = exam.questions
                exam_title = exam.title
                exam_day = exam.day
            else:
                return jsonify({"error": f"Exam '{quiz_id}' not found."}), 404

        total_q = len(questions)

        # Pad or slice user_answers
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
                record_question_stat(session, q.id, 'skipped')
            elif u_ans == q.correct:
                correct_count += 1
                topic_stats[topic]["correct"] += 1
                record_question_stat(session, q.id, 'correct')
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
                record_question_stat(session, q.id, 'incorrect')

        # Official IBPS scoring: +2.0 for correct, -0.5 penalty for incorrect
        raw_score = (correct_count * 2.0) - (wrong_count * 0.5)
        score = max(0.0, round(raw_score, 2))
        attempted = correct_count + wrong_count
        accuracy = round((correct_count / attempted) * 100) if attempted > 0 else 0

        # Persist Attempt in SQLite Database
        attempt = Attempt(
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
        session.add(attempt)
        session.commit()

        response_data = attempt.to_dict()
        response_data["answerKeys"] = answer_keys
        return jsonify(response_data)

    except Exception as e:
        session.rollback()
        print(f"Error evaluating exam: {e}")
        return jsonify({"error": f"Evaluation error: {str(e)}"}), 500

# API: Topic Mastery Analytics & Drill Directory
@app.route('/api/topics/mastery', methods=['GET'])
def get_topic_mastery():
    session = db_session()
    try:
        data = get_topic_mastery_list(session)
        return jsonify(data)
    except Exception as e:
        return jsonify([]), 500

# API: Cutoff Predictor & Exam Intelligence
@app.route('/api/analytics/cutoff-predictor', methods=['GET'])
def get_cutoff_analytics():
    session = db_session()
    try:
        data = get_cutoff_prediction(session)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
