"""Development server: python app.py → http://127.0.0.1:5000 (the app itself is app/web.py)."""
from app.web import app

if __name__ == "__main__":
    # Restarts by itself when a .py file changes
    app.run(debug=True)
