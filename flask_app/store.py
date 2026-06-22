"""
SQLite datastore — port of backend/datastore/datastore.go + sqlite.go.

The database schema is identical to the one created by the Go backend so
the same db.sqlite3 file can be used without migration.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

# Default: reuse the existing database file from the Go backend.
# Override with the DB_PATH environment variable.
_DEFAULT_DB = os.path.join(os.path.dirname(__file__), '..', 'backend', 'db.sqlite3')
DB_PATH = os.environ.get('DB_PATH', _DEFAULT_DB)


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(admin_emails):
    """Create tables if they don't exist and rebuild the admins table."""
    with _db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS proofs (
                id            INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                entryType     TEXT,
                userSubmitted TEXT,
                proofName     TEXT,
                proofType     TEXT,
                Premise       TEXT,
                Logic         TEXT,
                Rules         TEXT,
                proofCompleted TEXT,
                timeSubmitted DATETIME,
                Conclusion    TEXT,
                repoProblem   TEXT
            )
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_proof
            ON proofs (userSubmitted, proofName)
        ''')
        conn.execute('DROP TABLE IF EXISTS admins')
        conn.execute('CREATE TABLE admins (email TEXT)')
        conn.executemany('INSERT INTO admins VALUES (?)',
                         [(e,) for e in admin_emails])


def _rows_to_proofs(rows):
    """Convert raw sqlite3 rows to the same JSON-serialisable dicts that
    the Go backend produced (field names match the Go struct)."""
    proofs = []
    for row in rows:
        proofs.append({
            'Id':             str(row['id']),
            'EntryType':      row['entryType'],
            'UserSubmitted':  row['userSubmitted'],
            'ProofName':      row['proofName'],
            'ProofType':      row['proofType'],
            'Premise':        json.loads(row['Premise'] or '[]'),
            'Logic':          json.loads(row['Logic']  or '[]'),
            'Rules':          json.loads(row['Rules']  or '[]'),
            'ProofCompleted': row['proofCompleted'],
            'TimeSubmitted':  row['timeSubmitted'],
            'Conclusion':     row['Conclusion'],
            'RepoProblem':    row['repoProblem'],
        })
    return proofs


def get_user_proofs(email):
    """Incomplete proofs belonging to this user."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM proofs
               WHERE userSubmitted = ?
                 AND proofCompleted != 'true'
                 AND proofName != 'n/a'""",
            (email,)
        ).fetchall()
    return _rows_to_proofs(rows)


def get_repo_proofs():
    """Repository problems published by admins."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM proofs
               WHERE repoProblem = 'true'
                 AND userSubmitted IN (SELECT email FROM admins)
               ORDER BY userSubmitted""",
        ).fetchall()
    return _rows_to_proofs(rows)


def get_user_completed_proofs(email):
    """Completed repository problems for this user."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM proofs
               WHERE userSubmitted = ?
                 AND proofCompleted = 'true'""",
            (email,)
        ).fetchall()
    return _rows_to_proofs(rows)


def get_all_attempted_repo_proofs():
    """All student attempts at admin-published problems (admin CSV download)."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT p.* FROM proofs p
               WHERE EXISTS (
                   SELECT 1 FROM proofs a
                   WHERE a.userSubmitted IN (SELECT email FROM admins)
                     AND a.Premise    = p.Premise
                     AND a.Conclusion = p.Conclusion
               )"""
        ).fetchall()
    return _rows_to_proofs(rows)


def save_proof(proof, email):
    """Insert or update a proof (upsert on userSubmitted + proofName)."""
    premise_json = json.dumps(proof.get('Premise') or proof.get('premise') or [])
    logic_json   = json.dumps(proof.get('Logic')   or proof.get('logic')   or [])
    rules_json   = json.dumps(proof.get('Rules')   or proof.get('rules')   or [])

    # The JS Proof class uses lowercase field names for some fields
    entry_type      = proof.get('entryType')   or proof.get('EntryType', '')
    proof_name      = proof.get('proofName')   or proof.get('ProofName', '')
    proof_type      = proof.get('proofType')   or proof.get('ProofType', '')
    proof_completed = proof.get('proofCompleted') or proof.get('ProofCompleted', 'false')
    conclusion      = proof.get('conclusion')  or proof.get('Conclusion', '')
    repo_problem    = proof.get('repoProblem') or proof.get('RepoProblem', 'false')

    if not proof_name:
        raise ValueError('Proof name is empty')

    with _db() as conn:
        conn.execute(
            """INSERT INTO proofs
                   (entryType, userSubmitted, proofName, proofType,
                    Premise, Logic, Rules, proofCompleted,
                    timeSubmitted, Conclusion, repoProblem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
               ON CONFLICT (userSubmitted, proofName) DO UPDATE SET
                   entryType      = excluded.entryType,
                   proofType      = excluded.proofType,
                   Premise        = excluded.Premise,
                   Logic          = excluded.Logic,
                   Rules          = excluded.Rules,
                   proofCompleted = excluded.proofCompleted,
                   timeSubmitted  = datetime('now'),
                   Conclusion     = excluded.Conclusion,
                   repoProblem    = excluded.repoProblem""",
            (entry_type, email, proof_name, proof_type,
             premise_json, logic_json, rules_json, proof_completed,
             conclusion, repo_problem)
        )
