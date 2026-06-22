"""
Flask app — proof checker + user account backend.

Replaces both checkproof.php and the Go backend (backend.go).

Endpoints (all previously at /backend/* via nginx):
  GET  /admins      — public; returns list of admin email addresses
  POST /saveproof   — auth required; insert/update a proof
  POST /proofs      — auth required; query proofs

Proof-checker endpoint (previously checkproof.php):
  POST /checkproof  — public; check a proof and return issues
"""

import json
from functools import wraps
from flask import Flask, request, jsonify, g

import store
from proofs import check_proof

app = Flask(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
# Admin emails. Move to a config file when deploying to other institutions.

ADMIN_USERS = {
    'abiblarz@csumb.edu',
    'sislam@csumb.edu',
    'gbruns@csumb.edu',
    'cohunter@csumb.edu',
    'ndoss@csumb.edu',
}

# ── Startup ──────────────────────────────────────────────────────────────────

with app.app_context():
    store.init_db(ADMIN_USERS)

# ── Auth ─────────────────────────────────────────────────────────────────────

def require_email(f):
    """Middleware: read X-Auth-Token header as a plain email (dev-only auth)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method != 'POST' or not request.data and not request.json:
            return 'Request not authorized.', 401
        email = request.headers.get('X-Auth-Token', '').strip()
        if not email:
            return 'Not authenticated.', 401
        g.email = email
        return f(*args, **kwargs)
    return decorated

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get('/admins')
def get_admins():
    return jsonify({'Admins': list(ADMIN_USERS)})


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
def get_proofs():
    body = request.get_json(silent=True)
    if body is None:
        return 'Unable to decode request body.', 400

    selection = body.get('selection', '')
    if not selection:
        return 'Selection required', 400

    email = g.email

    try:
        if selection == 'user':
            proofs = store.get_user_proofs(email)
        elif selection == 'repo':
            proofs = store.get_repo_proofs()
        elif selection == 'completedrepo':
            proofs = store.get_user_completed_proofs(email)
        elif selection == 'downloadrepo':
            if email not in ADMIN_USERS:
                return 'Insufficient privileges', 403
            proofs = store.get_all_attempted_repo_proofs()
        else:
            return 'Invalid selection', 400
    except Exception as e:
        app.logger.error('get_proofs error: %s', e)
        return 'Query error', 500

    return jsonify(proofs)


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


if __name__ == '__main__':
    app.run(debug=True, port=5000)
