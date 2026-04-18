"""
@require_admin decorator.
Checks the X-Admin-Key header against the ADMIN_API_KEY config value.
"""

from functools import wraps
from flask import request, current_app
from .response import err


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-Admin-Key")
        if not api_key:
            return err("Missing X-Admin-Key header.", 401)
        if api_key != current_app.config["ADMIN_API_KEY"]:
            return err("Invalid admin API key.", 403)
        return f(*args, **kwargs)
    return decorated
