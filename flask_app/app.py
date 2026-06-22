"""
Flask app — proof checker + user account backend.

Replaces both checkproof.php and the Go backend (backend.go).
"""

import json
from flask import Flask, request, jsonify, g

import store
from proofs import check_proof
from config import APP_ADMINS
from auth import require_email
from instructor_routes import instructor_bp
from admin_routes import admin_bp

app = Flask(__name__)
app.register_blueprint(instructor_bp)
app.register_blueprint(admin_bp)

# ── Legacy admin users (kept for old /admins endpoint and legacy init) ─────────
LEGACY_ADMIN_USERS = {
    'abiblarz@csumb.edu',
    'sislam@csumb.edu',
    'gbruns@csumb.edu',
    'cohunter@csumb.edu',
    'ndoss@csumb.edu',
}

# ── Startup ───────────────────────────────────────────────────────────────────

with app.app_context():
    store.init_db(LEGACY_ADMIN_USERS)
    store.migrate_legacy_proofs()

# ── Legacy endpoints (existing frontend) ─────────────────────────────────────

@app.get('/admins')
def get_admins():
    return jsonify({'Admins': list(LEGACY_ADMIN_USERS)})


@app.post('/saveproof')
@require_email
def save_proof():
    proof = request.get_json(silent=True)
    if proof is None:
        return 'Could not parse request body.', 400
    try:
        store.save_proof(proof, g.email)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        app.logger.error('save_proof error: %s', e)
        return 'Database error.', 500
    return jsonify({'success': 'true'})


@app.post('/proofs')
@require_email
def get_legacy_proofs():
    body = request.get_json(silent=True)
    if body is None:
        return 'Unable to decode request body.', 400

    selection = body.get('selection', '')
    email = g.email

    try:
        if selection == 'user':
            proofs = store.get_user_proofs(email)
        elif selection == 'repo':
            proofs = store.get_repo_proofs()
        elif selection == 'completedrepo':
            proofs = store.get_user_completed_proofs(email)
        elif selection == 'downloadrepo':
            if email not in LEGACY_ADMIN_USERS:
                return 'Insufficient privileges', 403
            proofs = store.get_all_attempted_repo_proofs()
        else:
            return 'Invalid selection', 400
    except Exception as e:
        app.logger.error('get_legacy_proofs error: %s', e)
        return 'Query error', 500

    return jsonify(proofs)


# ── Proof checker ─────────────────────────────────────────────────────────────

@app.post('/checkproof')
def checkproof():
    proof_data_json = request.form.get('proofData', '')
    num_prems_str   = request.form.get('numPrems', '0')
    wanted_conc     = request.form.get('wantedConc', '')
    predicate_str   = request.form.get('predicateSettings', 'false')

    try:
        pr_data = json.loads(proof_data_json)
    except (json.JSONDecodeError, ValueError):
        return jsonify({'issues': ['Could not parse proofData.'], 'concReached': False}), 400

    try:
        numprems = int(num_prems_str)
    except ValueError:
        numprems = 0

    predicate_settings = predicate_str.lower() == 'true'
    result = check_proof(pr_data, numprems, wanted_conc, predicate_settings)
    return jsonify(result)


# ── Student endpoints ─────────────────────────────────────────────────────────

@app.get('/student/courses')
@require_email
def student_courses():
    return jsonify(store.get_student_courses(g.email))


@app.get('/student/courses/<int:course_id>/problem_sets')
@require_email
def student_problem_sets(course_id):
    if not store.is_enrolled(course_id, g.email):
        return 'Not enrolled in this course.', 403
    return jsonify(store.get_visible_problem_sets(course_id))


@app.get('/student/problem_sets/<int:ps_id>/problems')
@require_email
def student_problems(ps_id):
    ps = store.get_problem_set(ps_id)
    if not ps or not ps['published']:
        return 'Problem set not found.', 404
    if not store.is_enrolled(ps['course_id'], g.email):
        return 'Not enrolled in this course.', 403

    problems = store.get_problem_set_problems(ps_id)
    # Attach attempt status to each problem
    for p in problems:
        attempt = store.get_attempt(g.email, p['id'])
        p['solved']      = attempt['solved']      if attempt else False
        p['solve_count'] = attempt['solve_count'] if attempt else 0
        p['in_progress'] = (attempt is not None and not attempt['solved'])
    return jsonify(problems)


@app.get('/student/problems/<int:problem_id>/attempt')
@require_email
def student_attempt(problem_id):
    problem = store.get_problem(problem_id)
    if not problem:
        return 'Problem not found.', 404
    ps = store.get_problem_set(problem['problem_set_id'])
    if not store.is_enrolled(ps['course_id'], g.email):
        return 'Not enrolled in this course.', 403
    attempt = store.get_attempt(g.email, problem_id)
    return jsonify(attempt)


@app.post('/student/problems/<int:problem_id>/attempt')
@require_email
def save_student_attempt(problem_id):
    problem = store.get_problem(problem_id)
    if not problem:
        return 'Problem not found.', 404
    ps = store.get_problem_set(problem['problem_set_id'])
    if not store.is_enrolled(ps['course_id'], g.email):
        return 'Not enrolled in this course.', 403

    # Enforce until (hard cutoff)
    if ps['until']:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        if now > ps['until']:
            return 'This problem set is closed.', 403

    # Enforce max attempts per problem
    max_attempts = ps['max_attempts_per_problem']
    if max_attempts:
        total = store.count_attempts_today(g.email, problem_id)
        if total >= max_attempts:
            return f'Maximum of {max_attempts} attempts reached.', 429

    body = request.get_json(silent=True) or {}
    logic = body.get('logic', [])
    proof_completed = bool(body.get('proof_completed', False))

    store.save_attempt(g.email, problem_id, logic, proof_completed)
    store.log_attempt(g.email, problem_id, logic, proof_completed)
    return jsonify(store.get_attempt(g.email, problem_id))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
