import os
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, Float, String, Text, DateTime, ForeignKey, select, update, or_, func, desc
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, relationship

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'app.db')

DATABASE_URL = f"sqlite:///{DB_PATH}?check_same_thread=False"

engine = create_engine(DATABASE_URL, echo=False)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

class Exam(Base):
    __tablename__ = 'exams'

    id = Column(String(50), primary_key=True) # e.g. "day_1", "day_17"
    day = Column(Integer, nullable=False)
    title = Column(String(150), nullable=False)
    difficulty = Column(String(50), default="Easy to Moderate")
    difficulty_level = Column(Integer, default=2)
    tags = Column(String(100), default="Balanced")
    time_limit_minutes = Column(Integer, default=40)
    total_questions = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)

    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan", order_by="Question.q_num")

    def to_dict(self, include_questions=False, include_answers=False):
        data = {
            "id": self.id,
            "day": self.day,
            "title": self.title,
            "difficulty": self.difficulty,
            "difficultyLevel": self.difficulty_level,
            "tags": self.tags,
            "timeLimitMinutes": self.time_limit_minutes,
            "totalQuestions": self.total_questions,
            "url": f"/player?quiz={self.id}",
            "name": f"Day_{self.day}.html"
        }
        if include_questions:
            data["questions"] = [q.to_dict(include_answer=include_answers) for q in self.questions]
        return data

class Question(Base):
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(50), ForeignKey('exams.id'), nullable=False)
    q_num = Column(Integer, nullable=False) # 1 to 50
    topic = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    options_json = Column(Text, nullable=False) # JSON array of string options
    correct = Column(Integer, nullable=False) # 0 to 4
    explanation = Column(Text, default="")

    exam = relationship("Exam", back_populates="questions")

    def to_dict(self, include_answer=True):
        opts = []
        try:
            opts = json.loads(self.options_json)
        except Exception:
            opts = []
        
        q_data = {
            "id": self.q_num,
            "topic": self.topic,
            "text": self.text,
            "options": opts
        }
        if include_answer:
            q_data["correct"] = self.correct
            q_data["explanation"] = self.explanation
        return q_data

class Attempt(Base):
    __tablename__ = 'attempts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(String(50), nullable=False)
    exam_title = Column(String(150), nullable=False)
    exam_day = Column(Integer, default=1)
    score = Column(Float, nullable=False)
    correct_count = Column(Integer, default=0)
    incorrect_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    total_questions = Column(Integer, default=50)
    accuracy = Column(Integer, default=0)
    time_taken_seconds = Column(Integer, default=0)
    date = Column(DateTime, default=datetime.utcnow)
    
    # Detailed payloads
    answers_json = Column(Text, default="[]")
    topic_breakdown_json = Column(Text, default="{}")
    wrong_questions_json = Column(Text, default="[]")
    skipped_questions_json = Column(Text, default="[]")
    playable_mistakes_json = Column(Text, default="[]")

    def to_dict(self):
        try:
            topic_stats = json.loads(self.topic_breakdown_json)
        except Exception:
            topic_stats = {}
        try:
            wrong_log = json.loads(self.wrong_questions_json)
        except Exception:
            wrong_log = []
        try:
            skipped_log = json.loads(self.skipped_questions_json)
        except Exception:
            skipped_log = []
        try:
            playable_mistakes = json.loads(self.playable_mistakes_json)
        except Exception:
            playable_mistakes = []
        try:
            user_answers = json.loads(self.answers_json)
        except Exception:
            user_answers = []

        return {
            "id": self.id,
            "quizDay": self.exam_day,
            "quizTitle": self.exam_title,
            "score": round(self.score, 2),
            "correct": self.correct_count,
            "incorrect": self.incorrect_count,
            "unattempted": self.skipped_count,
            "totalQuestions": self.total_questions,
            "accuracy": self.accuracy,
            "timeTakenSeconds": self.time_taken_seconds,
            "date": self.date.isoformat() if self.date else None,
            "topicBreakdown": topic_stats,
            "wrongQuestions": wrong_log,
            "skippedQuestions": skipped_log,
            "playableMistakes": playable_mistakes,
            "userAnswersArray": user_answers
        }

class SiteMetric(Base):
    __tablename__ = 'site_metrics'

    key = Column(String(50), primary_key=True)
    value = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class QuestionStat(Base):
    __tablename__ = 'question_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False, unique=True, index=True)
    times_seen = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)
    times_incorrect = Column(Integer, default=0)
    times_skipped = Column(Integer, default=0)
    box_level = Column(Integer, default=1)  # Leitner Box 1 (frequent) to 5 (mastered)
    last_attempted_at = Column(DateTime, default=datetime.utcnow)
    next_review_at = Column(DateTime, default=datetime.utcnow)

    question = relationship("Question", backref="stats")

    def to_dict(self):
        return {
            "questionId": self.question_id,
            "timesSeen": self.times_seen,
            "timesCorrect": self.times_correct,
            "timesIncorrect": self.times_incorrect,
            "timesSkipped": self.times_skipped,
            "boxLevel": self.box_level,
            "lastAttemptedAt": self.last_attempted_at.isoformat() if self.last_attempted_at else None,
            "nextReviewAt": self.next_review_at.isoformat() if self.next_review_at else None
        }

def record_question_stat(session, question_id, result_status):
    """
    result_status: 'correct', 'incorrect', 'skipped'
    Implements Leitner Spaced Repetition Box System:
    - Box 1: Interval 1 day
    - Box 2: Interval 2 days
    - Box 3: Interval 4 days
    - Box 4: Interval 8 days
    - Box 5: Interval 16 days (Mastered)
    Incorrect drops back to Box 1 immediately.
    """
    stat = session.query(QuestionStat).filter_by(question_id=question_id).first()
    now = datetime.utcnow()
    if not stat:
        stat = QuestionStat(question_id=question_id, times_seen=0, times_correct=0, times_incorrect=0, times_skipped=0, box_level=1)
        session.add(stat)
        session.flush()

    stat.times_seen += 1
    stat.last_attempted_at = now

    if result_status == 'correct':
        stat.times_correct += 1
        stat.box_level = min(5, stat.box_level + 1)
        stat.next_review_at = now + timedelta(days=2 ** (stat.box_level - 1))
    elif result_status == 'incorrect':
        stat.times_incorrect += 1
        stat.box_level = 1  # Demote to Box 1
        stat.next_review_at = now
    elif result_status == 'skipped':
        stat.times_skipped += 1
        stat.box_level = max(1, stat.box_level - 1)
        stat.next_review_at = now
    
    return stat

def sync_stats_from_existing_attempts():
    """Sync historical attempts into question_stats table on startup if empty."""
    session = db_session()
    try:
        count = session.query(QuestionStat).count()
        if count > 0:
            return  # already initialized

        attempts = session.query(Attempt).order_by(Attempt.date.asc()).all()
        for att in attempts:
            if not att.exam_id:
                continue
            exam = session.query(Exam).filter_by(id=att.exam_id).first()
            if not exam:
                continue
            try:
                user_answers = json.loads(att.answers_json)
            except Exception:
                continue
            for idx, q in enumerate(exam.questions):
                if idx >= len(user_answers):
                    break
                u_ans = user_answers[idx]
                if u_ans is None:
                    record_question_stat(session, q.id, 'skipped')
                elif u_ans == q.correct:
                    record_question_stat(session, q.id, 'correct')
                else:
                    record_question_stat(session, q.id, 'incorrect')
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error syncing historical stats: {e}")
    finally:
        session.close()

def generate_revision_mock(session, limit=50):
    """
    Spaced Repetition Algorithm:
    Selects up to `limit` questions prioritizing:
    1. Highest failure rate (Box 1, times_incorrect > 0)
    2. Overdue review (next_review_at <= now)
    3. Skipped questions
    Pads with unattempted questions if fewer than `limit` mistakes exist.
    """
    now = datetime.utcnow()
    
    # 1. Questions with mistakes or overdue reviews
    overdue_stats = (
        session.query(QuestionStat)
        .filter((QuestionStat.times_incorrect > 0) | (QuestionStat.times_skipped > 0))
        .order_by(QuestionStat.box_level.asc(), (QuestionStat.times_incorrect + QuestionStat.times_skipped).desc(), QuestionStat.next_review_at.asc())
        .limit(limit)
        .all()
    )
    
    selected_question_ids = [s.question_id for s in overdue_stats]
    selected_questions = []
    
    if selected_question_ids:
        q_map = {q.id: q for q in session.query(Question).filter(Question.id.in_(selected_question_ids)).all()}
        for q_id in selected_question_ids:
            if q_id in q_map:
                selected_questions.append(q_map[q_id])
                
    # If not enough, pad with unattempted questions
    if len(selected_questions) < limit:
        needed = limit - len(selected_questions)
        already_picked = set(selected_question_ids)
        
        unseen_q = (
            session.query(Question)
            .filter(~Question.id.in_(already_picked))
            .order_by(Question.id.asc())
            .limit(needed)
            .all()
        )
        selected_questions.extend(unseen_q)

    q_list = []
    for idx, q in enumerate(selected_questions):
        opts = []
        try:
            opts = json.loads(q.options_json)
        except Exception:
            opts = []
        q_list.append({
            "id": idx + 1,
            "db_id": q.id,
            "topic": q.topic,
            "text": q.text,
            "options": opts,
            "correct": q.correct,
            "explanation": q.explanation
        })

    return {
        "id": "revision",
        "day": 0,
        "title": "IT Officer Mains: Adaptive Revision Mock",
        "difficulty": "Adaptive Leitner",
        "difficultyLevel": 3,
        "tags": f"Spaced Repetition ({len(q_list)} Questions)",
        "timeLimitMinutes": 40 if len(q_list) >= 40 else max(15, len(q_list)),
        "totalQuestions": len(q_list),
        "questions": q_list
    }

CORE_TOPIC_GROUPS = [
    {"name": "Database Systems", "keywords": ["Database", "SQL", "DBMS", "Normalization", "Transaction", "Relational", "ER "]},
    {"name": "Computer Networks", "keywords": ["Network", "Subnet", "TCP", "IP", "OSI", "Routing", "Socket"]},
    {"name": "Operating Systems", "keywords": ["Operating System", "Process", "Deadlock", "Memory", "Paging", "Thread", "Semaphore"]},
    {"name": "Data Structures & Algorithms", "keywords": ["Data Structure", "Algorithm", "Tree", "Graph", "Stack", "Queue", "Sorting", "Complexity"]},
    {"name": "Software Engineering & SDLC", "keywords": ["Software Engineering", "SDLC", "Agile", "Testing", "UML", "Design Pattern"]},
    {"name": "Cyber Security & IT Act", "keywords": ["Cyber", "Security", "Cryptography", "Firewall", "IT Act", "Attack", "Malware"]},
    {"name": "Programming & OOPs", "keywords": ["Java", "Python", "C++", "C Programming", "OOP", "Compiler", "Object Oriented"]},
    {"name": "Digital Logic & Architecture", "keywords": ["Architecture", "Digital Logic", "Microprocessor", "Pipeline", "Boolean", "K-Map"]},
    {"name": "Linux & Administration", "keywords": ["Linux", "Unix", "Shell", "Bash", "Command", "Permissions"]}
]

def generate_topic_drill(session, topic_keyword, count=15):
    """Generates a targeted drill quiz for a specific topic or keyword."""
    # Find matching questions
    matching = (
        session.query(Question)
        .filter(Question.topic.ilike(f"%{topic_keyword}%") | Question.text.ilike(f"%{topic_keyword}%"))
        .all()
    )
    if not matching:
        matching = session.query(Question).limit(count * 2).all()

    # Prioritize questions candidate struggled with
    matching_ids = [q.id for q in matching]
    stats_map = {s.question_id: s for s in session.query(QuestionStat).filter(QuestionStat.question_id.in_(matching_ids)).all()}

    def sort_key(q):
        s = stats_map.get(q.id)
        if not s:
            return 2 # unattempted
        if s.times_incorrect > 0:
            return 0 # struggled
        if s.times_skipped > 0:
            return 1 # skipped
        return 3 # mastered

    sorted_questions = sorted(matching, key=sort_key)[:count]

    q_list = []
    for idx, q in enumerate(sorted_questions):
        opts = []
        try:
            opts = json.loads(q.options_json)
        except Exception:
            opts = []
        q_list.append({
            "id": idx + 1,
            "db_id": q.id,
            "topic": q.topic,
            "text": q.text,
            "options": opts,
            "correct": q.correct,
            "explanation": q.explanation
        })

    clean_title = topic_keyword.title()
    return {
        "id": f"drill_{topic_keyword.lower().replace(' ', '_')[:20]}",
        "day": 0,
        "title": f"Targeted Drill: {clean_title}",
        "difficulty": "Topic Focus",
        "difficultyLevel": 2,
        "tags": f"{len(q_list)} Questions",
        "timeLimitMinutes": max(10, round(len(q_list) * 0.8)),
        "totalQuestions": len(q_list),
        "questions": q_list
    }

def get_topic_mastery_list(session):
    """Returns analytics and question counts for core technical topics."""
    topics_data = []
    for group in CORE_TOPIC_GROUPS:
        name = group["name"]
        keywords = group["keywords"]
        
        conds = [Question.topic.ilike(f"%{kw}%") for kw in keywords]
        matching_questions = session.query(Question).filter(or_(*conds)).all()
        q_ids = [q.id for q in matching_questions]
        total_q = len(q_ids)

        if total_q == 0:
            continue

        stats = session.query(QuestionStat).filter(QuestionStat.question_id.in_(q_ids)).all()
        seen = sum(s.times_seen for s in stats)
        correct = sum(s.times_correct for s in stats)
        incorrect = sum(s.times_incorrect for s in stats)
        skipped = sum(s.times_skipped for s in stats)

        attempted = correct + incorrect
        accuracy = round((correct / attempted) * 100) if attempted > 0 else 0
        
        if accuracy >= 75 and attempted >= 10:
            mastery = "Mastered"
            badge_class = "badge-mastered"
        elif accuracy >= 50 or (attempted > 0 and attempted < 10):
            mastery = "Moderate"
            badge_class = "badge-moderate"
        else:
            mastery = "Needs Drill"
            badge_class = "badge-needs-drill"

        topics_data.append({
            "topic": name,
            "totalQuestions": total_q,
            "seen": seen,
            "attempted": attempted,
            "correct": correct,
            "incorrect": incorrect,
            "skipped": skipped,
            "accuracy": accuracy,
            "mastery": mastery,
            "badgeClass": badge_class
        })

    return topics_data

def get_cutoff_prediction(session):
    """Calculates candidate standing vs official IBPS SO Scale-I cutoff."""
    attempts = session.query(Attempt).order_by(Attempt.date.asc()).all()
    total_attempts = len(attempts)
    
    target = 65.0
    qualifying = 12.0

    if total_attempts == 0:
        return {
            "totalAttempts": 0,
            "averageScore": 0.0,
            "latestScore": 0.0,
            "highestScore": 0.0,
            "targetCutoff": target,
            "qualifyingCutoff": qualifying,
            "status": "No Attempts Yet",
            "statusClass": "status-neutral",
            "message": "Attempt at least 1 mock to activate your cutoff projection.",
            "totalMarksLostToNegative": 0.0,
            "avgNegativeLoss": 0.0,
            "avgPacingSeconds": 0
        }

    scores = [a.score for a in attempts]
    avg_score = round(sum(scores) / total_attempts, 2)
    latest_score = round(scores[-1], 2)
    highest_score = round(max(scores), 2)
    
    total_wrong = sum(a.incorrect_count for a in attempts)
    total_lost_neg = round(total_wrong * 0.5, 2)
    avg_neg_loss = round(total_lost_neg / total_attempts, 2)

    total_time = sum(a.time_taken_seconds for a in attempts if a.time_taken_seconds > 0)
    total_q_taken = sum(a.total_questions for a in attempts if a.time_taken_seconds > 0)
    avg_pacing = round(total_time / total_q_taken, 1) if total_q_taken > 0 else 40.0

    diff = round(avg_score - target, 2)

    if avg_score >= target:
        status = "Likely Shortlist"
        status_class = "status-green"
        msg = f"Outperforming cutoff target by +{diff} marks. Maintain consistency!"
    elif avg_score >= 50.0:
        status = "Competitive (Borderline)"
        status_class = "status-amber"
        msg = f"Within striking distance ({abs(diff)} marks to target). Reducing negative marking will push you through."
    elif avg_score >= qualifying:
        status = "Qualifying Only"
        status_class = "status-amber"
        msg = f"Clears sectional minimum ({qualifying}), but needs +{abs(diff)} marks for final merit shortlist."
    else:
        status = "Needs Practice"
        status_class = "status-red"
        msg = f"Currently below sectional cutoff. Focus on high-yield topic drills."

    return {
        "totalAttempts": total_attempts,
        "averageScore": avg_score,
        "latestScore": latest_score,
        "highestScore": highest_score,
        "targetCutoff": target,
        "qualifyingCutoff": qualifying,
        "status": status,
        "statusClass": status_class,
        "message": msg,
        "totalMarksLostToNegative": total_lost_neg,
        "avgNegativeLoss": avg_neg_loss,
        "avgPacingSeconds": avg_pacing
    }

def init_db():
    Base.metadata.create_all(bind=engine)
    seed_database_if_empty()
    sync_stats_from_existing_attempts()

def increment_visitors():
    """Atomically increment the visitor counter using database transactions."""
    session = db_session()
    try:
        metric = session.query(SiteMetric).filter_by(key='visitor_count').with_for_update().first()
        if not metric:
            # Sync with existing visitors.json if present
            initial_count = 0
            json_file = os.path.join(BASE_DIR, 'visitors.json')
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        initial_count = data.get('count', 0)
                except Exception:
                    pass
            metric = SiteMetric(key='visitor_count', value=initial_count + 1)
            session.add(metric)
        else:
            metric.value += 1
            metric.updated_at = datetime.utcnow()
        session.commit()
        return metric.value
    except Exception as e:
        session.rollback()
        print(f"Database visitor counter error: {e}")
        return 1
    finally:
        session.close()

def seed_database_if_empty():
    """Seeds the SQLite database from data/quizzes/*.json if exams table is empty."""
    session = db_session()
    try:
        count = session.query(Exam).count()
        if count > 0:
            return # Already seeded

        quizzes_dir = os.path.join(DATA_DIR, 'quizzes')
        manifest_file = os.path.join(quizzes_dir, 'manifest.json')
        if not os.path.exists(manifest_file):
            return

        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        for item in manifest:
            quiz_file = os.path.join(quizzes_dir, item['file'])
            if not os.path.exists(quiz_file):
                continue

            with open(quiz_file, 'r', encoding='utf-8') as qf:
                quiz_data = json.load(qf)

            exam = Exam(
                id=quiz_data['id'],
                day=quiz_data.get('day', 1),
                title=quiz_data['title'],
                difficulty=quiz_data.get('difficulty', 'Easy to Moderate'),
                difficulty_level=quiz_data.get('difficultyLevel', 2),
                tags=quiz_data.get('tags', 'Balanced'),
                time_limit_minutes=quiz_data.get('timeLimitMinutes', 40),
                total_questions=quiz_data.get('totalQuestions', len(quiz_data.get('questions', [])))
            )
            session.add(exam)

            for idx, q in enumerate(quiz_data.get('questions', [])):
                question = Question(
                    exam_id=exam.id,
                    q_num=idx + 1,
                    topic=q.get('topic', 'General'),
                    text=q.get('text', ''),
                    options_json=json.dumps(q.get('options', [])),
                    correct=q.get('correct', 0),
                    explanation=q.get('explanation', '')
                )
                session.add(question)

        session.commit()
        print(f"Database successfully seeded with {len(manifest)} exams.")
    except Exception as e:
        session.rollback()
        print(f"Database seeding error: {e}")
    finally:
        session.close()
