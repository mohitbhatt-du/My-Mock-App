from flask import Flask, jsonify, request, send_from_directory
import os, json, re

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_QUIZZES_DIR = os.path.join(BASE_DIR, 'data', 'quizzes')
MOCK_PAGES_DIR = os.path.join(BASE_DIR, 'static', 'Mock_Pages')
os.makedirs(MOCK_PAGES_DIR, exist_ok=True)
os.makedirs(DATA_QUIZZES_DIR, exist_ok=True)

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

# API: List all quizzes
@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
    manifest_path = os.path.join(DATA_QUIZZES_DIR, 'manifest.json')
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            quizzes = []
            for item in manifest:
                quizzes.append({
                    "id": item.get("id"),
                    "name": item.get("legacyHtml") or f"{item.get('id')}.html",
                    "title": item.get("title"),
                    "difficulty": item.get("difficulty", "Standard"),
                    "tags": item.get("tags", "Balanced"),
                    # New unified player URL with query param
                    "url": f"/player?quiz={item.get('id')}",
                    "totalQuestions": item.get("totalQuestions", 50)
                })
            
            # Natural sort by day / number
            def extract_number(q):
                match = re.search(r'\d+', q['title'])
                return int(match.group()) if match else 0
            
            quizzes.sort(key=extract_number)
            return jsonify(quizzes)
        except Exception as e:
            print(f"Error reading manifest: {e}")

    # Fallback to legacy scan if manifest is missing
    quizzes = []
    try:
        if os.path.exists(MOCK_PAGES_DIR):
            for filename in os.listdir(MOCK_PAGES_DIR):
                if filename.endswith('.html'):
                    filepath = os.path.join(MOCK_PAGES_DIR, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(2500)
                        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                        diff_match = re.search(r'<meta name="quiz-difficulty" content="(.*?)">', content, re.IGNORECASE)
                        tags_match = re.search(r'<meta name="quiz-tags" content="(.*?)">', content, re.IGNORECASE)
                        title = title_match.group(1) if title_match else filename.replace('.html', '')
                        quizzes.append({
                            "name": filename,
                            "title": title,
                            "difficulty": diff_match.group(1) if diff_match else 'Unknown Level',
                            "tags": tags_match.group(1) if tags_match else 'Balanced',
                            "url": f"/Mock_Pages/{filename}"
                        })
                    except Exception as err:
                        print(f"Error reading {filename}: {err}")
            quizzes.sort(key=lambda q: int(re.search(r'\d+', q['title']).group()) if re.search(r'\d+', q['title']) else 0)
    except Exception as e:
        print(f"Fallback scan error: {e}")

    return jsonify(quizzes)

# API: Get individual quiz data by ID
@app.route('/api/quizzes/<quiz_id>', methods=['GET'])
def get_quiz_detail(quiz_id):
    # Normalize ID (e.g., "Day_1.html" or "day_1")
    clean_id = quiz_id.replace('.html', '').replace('.json', '').lower()
    json_path = os.path.join(DATA_QUIZZES_DIR, f"{clean_id}.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": f"Failed to load quiz data: {str(e)}"}), 500
    
    return jsonify({"error": f"Quiz '{quiz_id}' not found."}), 404

# API: Page View Counter
@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    visitor_file = os.path.join(BASE_DIR, 'visitors.json')
    count = 0
    try:
        if os.path.exists(visitor_file):
            with open(visitor_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    count = data.get('count', 0)
                except json.JSONDecodeError:
                    count = 0
        count += 1
        with open(visitor_file, 'w', encoding='utf-8') as f:
            json.dump({"count": count}, f)
    except Exception as e:
        print(f"Visitor counter error: {e}")
        if count == 0: count = 1
        
    return jsonify({"count": count})

if __name__ == '__main__':
    app.run(debug=False, port=5001)
