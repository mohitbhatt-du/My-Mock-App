from flask import Flask, jsonify, request, send_from_directory
import os, json, re

app = Flask(__name__, static_folder='.')

os.makedirs('Mock_Pages', exist_ok=True)

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/Mock_Pages/<path:filename>')
def serve_quiz(filename):
    return send_from_directory('Mock_Pages', filename)

# API: Auto-Read Quizzes with Error Handling
@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
    quizzes = []
    try:
        if os.path.exists('Mock_Pages'):
            for filename in os.listdir('Mock_Pages'):
                if filename.endswith('.html'):
                    filepath = os.path.join('Mock_Pages', filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(2500)
                            
                        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                        diff_match = re.search(r'<meta name="quiz-difficulty" content="(.*?)">', content, re.IGNORECASE)
                        
                        title = title_match.group(1) if title_match else filename.replace('.html', '')
                        difficulty = diff_match.group(1) if diff_match else 'Unknown Level'
                        
                        quizzes.append({
                            "name": filename,
                            "title": title,
                            "difficulty": difficulty,
                            "url": f"/Mock_Pages/{filename}"
                        })
                    except Exception as file_err:
                        print(f"Error reading {filename}: {file_err}")
    except Exception as e:
        print(f"Error scanning Mock_Pages: {e}")
    return jsonify(quizzes)

# API: Safe Unique Visitor Counter
@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    visitor_file = 'visitors.json'
    count = 1
    try:
        if not os.path.exists(visitor_file):
            with open(visitor_file, 'w', encoding='utf-8') as f:
                json.dump({"unique_ips": []}, f)
                
        user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        with open(visitor_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if user_ip not in data.get('unique_ips', []):
            data['unique_ips'].append(user_ip)
            with open(visitor_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
                
        count = len(data['unique_ips'])
    except Exception as e:
        print(f"Visitor counter error: {e}")
        
    return jsonify({"count": count})

if __name__ == '__main__':
    app.run(debug=False, port=5000)