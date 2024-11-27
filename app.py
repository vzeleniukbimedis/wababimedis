from flask import Flask
from config.settings import init_app
from tracking.click_tracker import track_blueprint
from sendpulse.api import sendpulse_blueprint
from mailer.email_service import email_blueprint
from interactive import interactive_blueprint

app = Flask(__name__)

# Ініціалізація налаштувань
init_app(app)

# Реєстрація blueprints
app.register_blueprint(track_blueprint)
app.register_blueprint(sendpulse_blueprint)
app.register_blueprint(email_blueprint)
app.register_blueprint(interactive_blueprint)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
