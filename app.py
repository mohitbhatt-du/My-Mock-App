from flask import Flask, jsonify, request, send_from_directory
import os, json, re, hashlib
app = Flask(__name__, static_folder='static')

# Define the new path for your mock pages
MOCK_PAGES_DIR = os.path.join('static', 'Mock_Pages')
os.makedirs(MOCK_PAGES_DIR, exist_ok=True)

@app.route('/')
def home():
    # Serve index.html from static/Dashboard
    return send_from_directory(os.path.join('static', 'Dashboard'), 'index.html')

@app.route('/Mock_Pages/<path:filename>')
def serve_quiz(filename):
    # Serve the actual HTML files from the new location
    return send_from_directory(MOCK_PAGES_DIR, filename)

# API: Auto-Read Quizzes with Error Handling
@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
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
                        difficulty = diff_match.group(1) if diff_match else 'Unknown Level'
                        tags = tags_match.group(1) if tags_match else 'Balanced'
                        
                        quizzes.append({
                            "name": filename,
                            "title": title,
                            "difficulty": difficulty,
                            "tags": tags,
                            # URL remains the same so the frontend dashboard doesn't break
                            "url": f"/Mock_Pages/{filename}" 
                        })
                    except Exception as file_err:
                        print(f"Error reading {filename}: {file_err}")
            
            # Natural Sorting Function
            def extract_number(quiz):
                match = re.search(r'\d+', quiz['title'])
                return int(match.group()) if match else 0
            
            quizzes.sort(key=extract_number)

    except Exception as e:
        print(f"Error scanning Mock_Pages: {e}")
    return jsonify(quizzes)

# API: Simple Page View Counter (No IP Tracking)
@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    visitor_file = 'visitors.json'
    count = 0
    try:
        # Read the current count if the file exists
        if os.path.exists(visitor_file):
            with open(visitor_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    count = data.get('count', 0)
                except json.JSONDecodeError:
                    count = 0
                
        # Increment the count by 1 for every single reload
        count += 1
        
        # Save the new count back to the file
        with open(visitor_file, 'w', encoding='utf-8') as f:
            json.dump({"count": count}, f)
            
    except Exception as e:
        print(f"Visitor counter error: {e}")
        # Fallback in case of file write issues
        if count == 0: count = 1 
        
    return jsonify({"count": count})

if __name__ == '__main__':
    app.run(debug=False, port=5001)