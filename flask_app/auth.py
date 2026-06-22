from functools import wraps
from flask import request, g
import store
from config import APP_ADMINS


def _extract_email():
    return request.headers.get('X-Auth-Token', '').strip()


def require_email(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = _extract_email()
        if not email:
            return 'Not authenticated.', 401
        g.email = email
        return f(*args, **kwargs)
    return decorated


def require_instructor(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = _extract_email()
        if not email:
            return 'Not authenticated.', 401
        g.email = email
        if not store.is_instructor(email):
            return 'Instructor access required.', 403
        return f(*args, **kwargs)
    return decorated


def require_app_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = _extract_email()
        if not email:
            return 'Not authenticated.', 401
        g.email = email
        if email not in APP_ADMINS:
            return 'App admin access required.', 403
        return f(*args, **kwargs)
    return decorated
