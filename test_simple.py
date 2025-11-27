from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Hello World!"

@app.route('/health')
def health():
    return {"status": "healthy"}

if __name__ == '__main__':
    print("Starting simple server...")
    app.run(host='0.0.0.0', port=5000, debug=True)