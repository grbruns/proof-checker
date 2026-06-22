"""
App admin Blueprint — /admin/* endpoints.

Only users listed in config.APP_ADMINS may call these.
"""

from flask import Blueprint, jsonify, request, abort
import store
from auth import require_app_admin

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.get('/instructors')
@require_app_admin
def list_instructors():
    return jsonify(store.get_instructors())


@admin_bp.post('/instructors')
@require_app_admin
def add_instructor():
    body = request.get_json(silent=True) or {}
    email = body.get('email', '').strip()
    if not email:
        return 'Email is required.', 400
    store.add_instructor(email)
    return jsonify(store.get_instructors()), 201


@admin_bp.delete('/instructors/<email>')
@require_app_admin
def remove_instructor(email):
    store.remove_instructor(email)
    return '', 204


@admin_bp.get('/courses')
@require_app_admin
def list_all_courses():
    return jsonify(store.get_all_courses())
