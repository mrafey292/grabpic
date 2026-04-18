from functools import wraps
from flask import request, current_app
from .response import err


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key")
        if not key or key != current_app.config["ADMIN_API_KEY"]:
            return err("Invalid or missing admin API key.", 401)
        return f(*args, **kwargs)
    return decorated
