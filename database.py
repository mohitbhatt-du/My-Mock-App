import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, Text, DateTime, ForeignKey, select, update
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

def init_db():
    Base.metadata.create_all(bind=engine)
    seed_database_if_empty()

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
