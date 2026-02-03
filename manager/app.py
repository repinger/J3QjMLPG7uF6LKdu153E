from flask import Flask
from config import Config
from database import init_db
from routes import bp

app = Flask(__name__)
app.config.from_object(Config)

# Anti-cache Header
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Register Blueprint
app.register_blueprint(bp)

# Initialize Database
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
