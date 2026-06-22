"""
Flask proof checker — drop-in replacement for checkproof.php.

Endpoints:
  POST /checkproof   accepts the same form fields as checkproof.php and
                     returns the same JSON: {"issues": [...], "concReached": bool}
"""

import json
from flask import Flask, request, jsonify
from proofs import check_proof

app = Flask(__name__)


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
