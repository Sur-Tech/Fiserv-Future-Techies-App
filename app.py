from flask import Flask, render_template_string, send_from_directory
import os

app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/<path:filename>')
def serve_file(filename):
    """Serve HTML files and static assets"""
    if os.path.isfile(filename):
        if filename.endswith('.html'):
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return send_from_directory('.', filename)
    return "File not found", 404

if __name__ == '__main__':
    print("Starting Domus Application...")
    print("Open your browser to: http://localhost:8080")
    app.run(debug=True, host='0.0.0.0', port=8080)
