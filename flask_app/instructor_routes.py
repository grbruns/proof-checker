"""
Instructor Blueprint — /instructor/* endpoints.

Authorization rules:
  - All routes require the caller to be in the instructors table.
  - Course-scoped routes additionally verify the caller owns the course.
  - TA-management and student-enrollment routes also accept TAs for the
    student-management subset (GET/POST/DELETE students).
"""

from flask import Blueprint, jsonify, request, g, abort
import store
from auth import require_instructor, require_email

instructor_bp = Blueprint('instructor', __name__, url_prefix='/instructor')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _own_course(course_id):
    """Return course dict or 404/403."""
    course = store.get_course(course_id)
    if not course:
        abort(404)
    if course['instructor_email'] != g.email:
        abort(403)
    return course


def _course_staff_or_403(course_id):
    """Return course if caller is instructor or TA, else 403."""
    course = store.get_course(course_id)
    if not course:
        abort(404)
    if course['instructor_email'] != g.email and not store.is_ta(course_id, g.email):
        abort(403)
    return course


def _own_problem_set(ps_id):
    """Return (course, ps) or 404/403."""
    ps = store.get_problem_set(ps_id)
    if not ps:
        abort(404)
    course = _own_course(ps['course_id'])
    return course, ps


def _own_problem(problem_id):
    """Return (course, problem) or 404/403."""
    problem = store.get_problem(problem_id)
    if not problem:
        abort(404)
    _, ps = _own_problem_set(problem['problem_set_id'])
    return problem


# ── Courses ───────────────────────────────────────────────────────────────────

@instructor_bp.get('/courses')
@require_instructor
def list_courses():
    return jsonify(store.get_instructor_courses(g.email))


@instructor_bp.post('/courses')
@require_instructor
def create_course():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    if not name:
        return 'Course name is required.', 400
    course_id = store.create_course(
        g.email, name,
        description=body.get('description', ''),
        max_students=int(body.get('max_students', 200)),
    )
    return jsonify(store.get_course(course_id)), 201


@instructor_bp.patch('/courses/<int:course_id>')
@require_instructor
def update_course(course_id):
    _own_course(course_id)
    body = request.get_json(silent=True) or {}
    store.update_course(course_id, **body)
    return jsonify(store.get_course(course_id))


@instructor_bp.delete('/courses/<int:course_id>')
@require_instructor
def delete_course(course_id):
    _own_course(course_id)
    store.delete_course(course_id)
    return '', 204


# ── TAs ───────────────────────────────────────────────────────────────────────

@instructor_bp.get('/courses/<int:course_id>/tas')
@require_instructor
def list_tas(course_id):
    _own_course(course_id)
    return jsonify(store.get_course_tas(course_id))


@instructor_bp.post('/courses/<int:course_id>/tas')
@require_instructor
def add_ta(course_id):
    _own_course(course_id)
    body = request.get_json(silent=True) or {}
    email = body.get('email', '').strip()
    if not email:
        return 'Email is required.', 400
    store.add_ta(course_id, email)
    return jsonify(store.get_course_tas(course_id)), 201


@instructor_bp.delete('/courses/<int:course_id>/tas/<ta_email>')
@require_instructor
def remove_ta(course_id, ta_email):
    _own_course(course_id)
    store.remove_ta(course_id, ta_email)
    return '', 204


# ── Students ──────────────────────────────────────────────────────────────────

@instructor_bp.get('/courses/<int:course_id>/students')
@require_email
def list_students(course_id):
    _course_staff_or_403(course_id)
    return jsonify(store.get_course_students(course_id))


@instructor_bp.post('/courses/<int:course_id>/students')
@require_email
def add_students(course_id):
    course = _course_staff_or_403(course_id)
    body = request.get_json(silent=True) or {}
    emails = body.get('emails', [])
    if isinstance(emails, str):
        emails = [e.strip() for e in emails.replace(',', '\n').splitlines() if e.strip()]
    if not emails:
        return 'No emails provided.', 400

    current_count = store.get_course_student_count(course_id)
    max_students = course['max_students']
    if current_count + len(emails) > max_students:
        return f'Would exceed course limit of {max_students} students.', 400

    for email in emails:
        store.enroll_student(course_id, email)
    return jsonify(store.get_course_students(course_id)), 201


@instructor_bp.delete('/courses/<int:course_id>/students/<student_email>')
@require_email
def remove_student(course_id, student_email):
    _course_staff_or_403(course_id)
    store.unenroll_student(course_id, student_email)
    return '', 204


# ── Problem sets ──────────────────────────────────────────────────────────────

@instructor_bp.get('/courses/<int:course_id>/problem_sets')
@require_instructor
def list_problem_sets(course_id):
    _own_course(course_id)
    return jsonify(store.get_course_problem_sets(course_id))


@instructor_bp.post('/courses/<int:course_id>/problem_sets')
@require_instructor
def create_problem_set(course_id):
    _own_course(course_id)
    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    if not name:
        return 'Problem set name is required.', 400
    attrs = {k: body[k] for k in (
        'published', 'available_from', 'due_date', 'until',
        'time_limit_minutes', 'max_attempts_per_problem', 'release_solutions_at'
    ) if k in body}
    ps_id = store.create_problem_set(course_id, name, **attrs)
    return jsonify(store.get_problem_set(ps_id)), 201


@instructor_bp.get('/problem_sets/<int:ps_id>')
@require_instructor
def get_problem_set(ps_id):
    _own_problem_set(ps_id)
    return jsonify(store.get_problem_set(ps_id))


@instructor_bp.patch('/problem_sets/<int:ps_id>')
@require_instructor
def update_problem_set(ps_id):
    _own_problem_set(ps_id)
    body = request.get_json(silent=True) or {}
    store.update_problem_set(ps_id, **body)
    return jsonify(store.get_problem_set(ps_id))


@instructor_bp.delete('/problem_sets/<int:ps_id>')
@require_instructor
def delete_problem_set(ps_id):
    _own_problem_set(ps_id)
    store.delete_problem_set(ps_id)
    return '', 204


# ── Problems ──────────────────────────────────────────────────────────────────

@instructor_bp.get('/problem_sets/<int:ps_id>/problems')
@require_instructor
def list_problems(ps_id):
    _own_problem_set(ps_id)
    return jsonify(store.get_problem_set_problems(ps_id))


@instructor_bp.post('/problem_sets/<int:ps_id>/problems')
@require_instructor
def add_problem(ps_id):
    _own_problem_set(ps_id)
    body = request.get_json(silent=True) or {}
    name       = body.get('name', '').strip()
    conclusion = body.get('conclusion', '').strip()
    premises   = body.get('premises', [])
    logic_type = body.get('logic_type', 'prop')
    points     = body.get('points')

    if not name or not conclusion:
        return 'name and conclusion are required.', 400

    problem_id = store.add_problem(ps_id, name, premises, conclusion, logic_type, points)
    return jsonify(store.get_problem(problem_id)), 201


@instructor_bp.get('/problems/<int:problem_id>')
@require_instructor
def get_problem(problem_id):
    _own_problem(problem_id)
    return jsonify(store.get_problem(problem_id))


@instructor_bp.patch('/problems/<int:problem_id>')
@require_instructor
def update_problem(problem_id):
    problem = _own_problem(problem_id)

    body = request.get_json(silent=True) or {}
    content_fields = {'premises', 'conclusion'}
    changing_content = any(k in body for k in content_fields)

    if changing_content and store.problem_has_student_attempts(problem_id, g.email):
        return ('Students have already attempted this problem. '
                'Remove it and add a corrected version instead.', 409)

    store.update_problem(problem_id, **body)
    return jsonify(store.get_problem(problem_id))


@instructor_bp.delete('/problems/<int:problem_id>')
@require_instructor
def delete_problem(problem_id):
    _own_problem(problem_id)
    store.delete_problem(problem_id)
    return '', 204


# ── Solutions ─────────────────────────────────────────────────────────────────

@instructor_bp.post('/problems/<int:problem_id>/solution')
@require_instructor
def save_solution(problem_id):
    _own_problem(problem_id)
    body = request.get_json(silent=True) or {}
    logic = body.get('logic')
    if logic is None:
        return 'logic is required.', 400
    store.save_solution(problem_id, g.email, logic)
    return jsonify({'saved': True})


@instructor_bp.get('/problems/<int:problem_id>/solution')
@require_email
def get_solution(problem_id):
    if not store.can_view_solution(g.email, problem_id):
        abort(403)
    solution = store.get_solution(problem_id)
    if not solution:
        return jsonify(None)
    store.log_solution_access(g.email, problem_id)
    return jsonify(solution)


# ── Attempt data download ─────────────────────────────────────────────────────

@instructor_bp.get('/problem_sets/<int:ps_id>/attempts')
@require_email
def download_attempts(ps_id):
    ps = store.get_problem_set(ps_id)
    if not ps:
        abort(404)
    course = store.get_course(ps['course_id'])
    if course['instructor_email'] != g.email and not store.is_ta(ps['course_id'], g.email):
        abort(403)
    return jsonify(store.get_problem_set_attempts(ps_id))
