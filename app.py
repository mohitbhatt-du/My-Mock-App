from flask import Flask, jsonify, request, send_from_directory
import os, json, re, time

app = Flask(__name__, static_folder='.')

# Automatically create folders if they don't exist
os.makedirs('Mock_Pages', exist_ok=True)
os.makedirs('Result', exist_ok=True)

# 1. Serve the Dashboard
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# 2. Serve the Quiz HTML files
@app.route('/Mock_Pages/<path:filename>')
def serve_quiz(filename):
    return send_from_directory('Mock_Pages', filename)

# 3. API: Auto-Read Quizzes
@app.route('/api/quizzes', methods=['GET'])
def get_quizzes():
    quizzes = []
    for filename in os.listdir('Mock_Pages'):
        if filename.endswith('.html'):
            filepath = os.path.join('Mock_Pages', filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(2500) # Read top of file for metadata
                
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
    return jsonify(quizzes)

# 4. API: Auto-Read Results
@app.route('/api/results', methods=['GET'])
def get_results():
    results = []
    for filename in os.listdir('Result'):
        if filename.endswith('.json'):
            with open(os.path.join('Result', filename), 'r', encoding='utf-8') as f:
                try:
                    results.append(json.load(f))
                except json.JSONDecodeError:
                    pass
    return jsonify(results)

# 5. API: Auto-Save Result
@app.route('/api/save-result', methods=['POST'])
def save_result():
    data = request.json
    day = data.get('quizDay', 'unknown')
    filename = f"it-officer-mains-day-{day}-result-{int(time.time())}.json"
    filepath = os.path.join('Result', filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        
    return jsonify({"status": "success"})

# API: Unique Visitor Counter
@app.route('/api/visitors', methods=['GET'])
def visitor_count():
    visitor_file = 'visitors.json'
    
    # Create the file if it doesn't exist
    if not os.path.exists(visitor_file):
        with open(visitor_file, 'w') as f:
            json.dump({"unique_ips": []}, f)
            
    # Get the user's IP address
    # (Uses X-Forwarded-For if hosted on platforms like Render/Heroku)
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    with open(visitor_file, 'r') as f:
        data = json.load(f)
        
    # Add IP to the list if they are a new visitor
    if user_ip not in data['unique_ips']:
        data['unique_ips'].append(user_ip)
        with open(visitor_file, 'w') as f:
            json.dump(data, f)
            
    return jsonify({"count": len(data['unique_ips'])})

# 6. API: Reset / Clear All Results
@app.route('/api/reset-results', methods=['POST'])
def reset_results():
    try:
        # Loop through and delete all JSON files in the Result directory
        for filename in os.listdir('Result'):
            if filename.endswith('.json'):
                os.remove(os.path.join('Result', filename))
        return jsonify({"status": "success", "message": "All results cleared."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)