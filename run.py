from app import create_app
from flask import redirect, jsonify
import sys
import traceback

app = create_app()

@app.get("/")
def index():
    # Redirect root to Swagger UI for easy endpoint testing
    return redirect("/apidocs")

# Health check — Railway pings this to confirm the app is alive
@app.get("/health")
def health():
    return {"status": "ok"}, 200

# Catch-all error handler for 500 errors to expose tracebacks in json instead of html
@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({
        "success": False,
        "error": "Internal Server Error",
        "traceback": traceback.format_exc()
    }), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if hasattr(e, 'code'):
        return e
    # Now you're handling non-HTTP exceptions only
    return jsonify({
        "success": False,
        "error": str(e),
        "traceback": traceback.format_exc()
    }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
