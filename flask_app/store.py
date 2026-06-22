"""
SQLite datastore — legacy proof table + new course/problem/attempt schema.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), '..', 'backend', 'db.sqlite3')
DB_PATH = os.environ.get('DB_PATH', _DEFAULT_DB)


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db(admin_emails):
    """Create all tables and rebuild the legacy admins table."""
    with _db() as conn:
        # Legacy tables (kept for backward compatibility)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS proofs (
                id             INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                entryType      TEXT,
                userSubmitted  TEXT,
                proofName      TEXT,
                proofType      TEXT,
                Premise        TEXT,
                Logic          TEXT,
                Rules          TEXT,
                proofCompleted TEXT,
                timeSubmitted  DATETIME,
                Conclusion     TEXT,
                repoProblem    TEXT
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

        # Instructors
        conn.execute('''
            CREATE TABLE IF NOT EXISTS instructors (
                email TEXT PRIMARY KEY
            )
        ''')

        # Courses
        conn.execute('''
            CREATE TABLE IF NOT EXISTS courses (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                instructor_email       TEXT NOT NULL,
                name                   TEXT NOT NULL,
                description            TEXT DEFAULT '',
                max_students           INTEGER DEFAULT 200,
                tas_can_view_solutions INTEGER DEFAULT 0
            )
        ''')

        # Teaching assistants (per course)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS course_tas (
                course_id INTEGER NOT NULL,
                ta_email  TEXT NOT NULL,
                PRIMARY KEY (course_id, ta_email)
            )
        ''')

        # Student enrollment
        conn.execute('''
            CREATE TABLE IF NOT EXISTS enrollments (
                course_id     INTEGER NOT NULL,
                student_email TEXT NOT NULL,
                enrolled_at   DATETIME DEFAULT (datetime('now')),
                PRIMARY KEY (course_id, student_email)
            )
        ''')

        # Problem sets
        conn.execute('''
            CREATE TABLE IF NOT EXISTS problem_sets (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id                INTEGER NOT NULL,
                name                     TEXT NOT NULL,
                published                INTEGER DEFAULT 0,
                available_from           DATETIME,
                due_date                 DATETIME,
                until                    DATETIME,
                time_limit_minutes       INTEGER,
                max_attempts_per_problem INTEGER,
                release_solutions_at     DATETIME
            )
        ''')

        # Problems (embedded in problem sets)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS problems (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_set_id INTEGER NOT NULL,
                position       INTEGER NOT NULL DEFAULT 0,
                name           TEXT NOT NULL,
                premises       TEXT NOT NULL DEFAULT '[]',
                conclusion     TEXT NOT NULL DEFAULT '',
                logic_type     TEXT NOT NULL DEFAULT 'prop',
                points         INTEGER
            )
        ''')

        # Solutions (one per problem, instructor-only)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS solutions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id   INTEGER NOT NULL UNIQUE,
                author_email TEXT NOT NULL,
                logic        TEXT NOT NULL,
                created_at   DATETIME DEFAULT (datetime('now')),
                updated_at   DATETIME DEFAULT (datetime('now'))
            )
        ''')

        # Current student attempt state (one row per student+problem)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS attempts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                student_email TEXT NOT NULL,
                problem_id    INTEGER NOT NULL,
                current_logic TEXT DEFAULT '[]',
                solved        INTEGER DEFAULT 0,
                solve_count   INTEGER DEFAULT 0,
                started_at    DATETIME DEFAULT (datetime('now')),
                last_modified DATETIME DEFAULT (datetime('now')),
                UNIQUE (student_email, problem_id)
            )
        ''')

        # Append-only attempt log (one row per check-proof click)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS attempt_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_email   TEXT NOT NULL,
                problem_id      INTEGER NOT NULL,
                checked_at      DATETIME DEFAULT (datetime('now')),
                logic_snapshot  TEXT DEFAULT '[]',
                proof_completed INTEGER DEFAULT 0
            )
        ''')

        # Audit log for solution access
        conn.execute('''
            CREATE TABLE IF NOT EXISTS solution_access_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                accessor_email TEXT NOT NULL,
                problem_id     INTEGER NOT NULL,
                accessed_at    DATETIME DEFAULT (datetime('now'))
            )
        ''')


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate_legacy_proofs():
    """
    Migrate repo problems from the legacy proofs table into the new schema.
    Creates one course + problem set per legacy admin who has repo problems.
    Idempotent: skips any instructor who already has a course.
    """
    with _db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT userSubmitted FROM proofs WHERE repoProblem = 'true'"
        ).fetchall()

        for row in rows:
            submitter = row['userSubmitted']

            # Skip if this instructor already has courses (already migrated)
            exists = conn.execute(
                'SELECT 1 FROM courses WHERE instructor_email = ?', (submitter,)
            ).fetchone()
            if exists:
                continue

            conn.execute('INSERT OR IGNORE INTO instructors (email) VALUES (?)',
                         (submitter,))

            conn.execute(
                'INSERT INTO courses (instructor_email, name) VALUES (?, ?)',
                (submitter, 'Logic Course')
            )
            course_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            conn.execute(
                'INSERT INTO problem_sets (course_id, name, published) VALUES (?, ?, 1)',
                (course_id, 'Repository Problems')
            )
            ps_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            probs = conn.execute(
                """SELECT proofName, Premise, Conclusion, proofType FROM proofs
                   WHERE repoProblem = 'true' AND userSubmitted = ?""",
                (submitter,)
            ).fetchall()

            for pos, p in enumerate(probs, start=1):
                conn.execute(
                    '''INSERT INTO problems
                           (problem_set_id, position, name, premises, conclusion, logic_type)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (ps_id, pos, p['proofName'],
                     p['Premise'] or '[]', p['Conclusion'] or '',
                     p['proofType'] or 'prop')
                )


# ── Legacy proof operations (kept for existing frontend) ──────────────────────

def _rows_to_proofs(rows):
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
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM proofs
               WHERE repoProblem = 'true'
                 AND userSubmitted IN (SELECT email FROM admins)
               ORDER BY userSubmitted"""
        ).fetchall()
    return _rows_to_proofs(rows)


def get_user_completed_proofs(email):
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM proofs
               WHERE userSubmitted = ?
                 AND proofCompleted = 'true'""",
            (email,)
        ).fetchall()
    return _rows_to_proofs(rows)


def get_all_attempted_repo_proofs():
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
    premise_json = json.dumps(proof.get('Premise') or proof.get('premise') or [])
    logic_json   = json.dumps(proof.get('Logic')   or proof.get('logic')   or [])
    rules_json   = json.dumps(proof.get('Rules')   or proof.get('rules')   or [])

    entry_type      = proof.get('entryType')      or proof.get('EntryType', '')
    proof_name      = proof.get('proofName')      or proof.get('ProofName', '')
    proof_type      = proof.get('proofType')      or proof.get('ProofType', '')
    proof_completed = proof.get('proofCompleted') or proof.get('ProofCompleted', 'false')
    conclusion      = proof.get('conclusion')     or proof.get('Conclusion', '')
    repo_problem    = proof.get('repoProblem')    or proof.get('RepoProblem', 'false')

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


# ── Instructors ───────────────────────────────────────────────────────────────

def is_instructor(email):
    with _db() as conn:
        return bool(conn.execute(
            'SELECT 1 FROM instructors WHERE email = ?', (email,)
        ).fetchone())


def get_instructors():
    with _db() as conn:
        return [r['email'] for r in
                conn.execute('SELECT email FROM instructors ORDER BY email').fetchall()]


def add_instructor(email):
    with _db() as conn:
        conn.execute('INSERT OR IGNORE INTO instructors (email) VALUES (?)', (email,))


def remove_instructor(email):
    with _db() as conn:
        conn.execute('DELETE FROM instructors WHERE email = ?', (email,))


# ── Courses ───────────────────────────────────────────────────────────────────

def _row_to_course(row):
    return {
        'id':                     row['id'],
        'instructor_email':       row['instructor_email'],
        'name':                   row['name'],
        'description':            row['description'],
        'max_students':           row['max_students'],
        'tas_can_view_solutions': bool(row['tas_can_view_solutions']),
    }


def create_course(instructor_email, name, description='', max_students=200):
    with _db() as conn:
        conn.execute(
            '''INSERT INTO courses (instructor_email, name, description, max_students)
               VALUES (?, ?, ?, ?)''',
            (instructor_email, name, description, max_students)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_course(course_id):
    with _db() as conn:
        row = conn.execute(
            'SELECT * FROM courses WHERE id = ?', (course_id,)
        ).fetchone()
    return _row_to_course(row) if row else None


def get_instructor_courses(instructor_email):
    with _db() as conn:
        rows = conn.execute(
            'SELECT * FROM courses WHERE instructor_email = ? ORDER BY name',
            (instructor_email,)
        ).fetchall()
    return [_row_to_course(r) for r in rows]


def get_all_courses():
    with _db() as conn:
        rows = conn.execute('SELECT * FROM courses ORDER BY instructor_email, name').fetchall()
    return [_row_to_course(r) for r in rows]


def update_course(course_id, **fields):
    allowed = {'name', 'description', 'max_students', 'tas_can_view_solutions'}
    sets = ', '.join(f'{k} = ?' for k in fields if k in allowed)
    vals = [v for k, v in fields.items() if k in allowed]
    if not sets:
        return
    with _db() as conn:
        conn.execute(f'UPDATE courses SET {sets} WHERE id = ?', vals + [course_id])


def delete_course(course_id):
    with _db() as conn:
        conn.execute('DELETE FROM courses WHERE id = ?', (course_id,))


# ── TAs ───────────────────────────────────────────────────────────────────────

def get_course_tas(course_id):
    with _db() as conn:
        return [r['ta_email'] for r in conn.execute(
            'SELECT ta_email FROM course_tas WHERE course_id = ? ORDER BY ta_email',
            (course_id,)
        ).fetchall()]


def add_ta(course_id, ta_email):
    with _db() as conn:
        conn.execute('INSERT OR IGNORE INTO course_tas VALUES (?, ?)',
                     (course_id, ta_email))


def remove_ta(course_id, ta_email):
    with _db() as conn:
        conn.execute('DELETE FROM course_tas WHERE course_id = ? AND ta_email = ?',
                     (course_id, ta_email))


def is_ta(course_id, email):
    with _db() as conn:
        return bool(conn.execute(
            'SELECT 1 FROM course_tas WHERE course_id = ? AND ta_email = ?',
            (course_id, email)
        ).fetchone())


# ── Enrollments ───────────────────────────────────────────────────────────────

def enroll_student(course_id, student_email):
    with _db() as conn:
        conn.execute('INSERT OR IGNORE INTO enrollments (course_id, student_email) VALUES (?, ?)',
                     (course_id, student_email))


def unenroll_student(course_id, student_email):
    with _db() as conn:
        conn.execute('DELETE FROM enrollments WHERE course_id = ? AND student_email = ?',
                     (course_id, student_email))


def get_course_students(course_id):
    with _db() as conn:
        return [r['student_email'] for r in conn.execute(
            'SELECT student_email FROM enrollments WHERE course_id = ? ORDER BY student_email',
            (course_id,)
        ).fetchall()]


def get_student_courses(student_email):
    with _db() as conn:
        rows = conn.execute(
            '''SELECT c.* FROM courses c
               JOIN enrollments e ON e.course_id = c.id
               WHERE e.student_email = ?
               ORDER BY c.name''',
            (student_email,)
        ).fetchall()
    return [_row_to_course(r) for r in rows]


def is_enrolled(course_id, student_email):
    with _db() as conn:
        return bool(conn.execute(
            'SELECT 1 FROM enrollments WHERE course_id = ? AND student_email = ?',
            (course_id, student_email)
        ).fetchone())


def get_course_student_count(course_id):
    with _db() as conn:
        return conn.execute(
            'SELECT COUNT(*) FROM enrollments WHERE course_id = ?', (course_id,)
        ).fetchone()[0]


# ── Problem sets ──────────────────────────────────────────────────────────────

def _row_to_problem_set(row):
    return {
        'id':                       row['id'],
        'course_id':                row['course_id'],
        'name':                     row['name'],
        'published':                bool(row['published']),
        'available_from':           row['available_from'],
        'due_date':                 row['due_date'],
        'until':                    row['until'],
        'time_limit_minutes':       row['time_limit_minutes'],
        'max_attempts_per_problem': row['max_attempts_per_problem'],
        'release_solutions_at':     row['release_solutions_at'],
    }


def create_problem_set(course_id, name, **attrs):
    allowed = {'published', 'available_from', 'due_date', 'until',
               'time_limit_minutes', 'max_attempts_per_problem', 'release_solutions_at'}
    cols = ['course_id', 'name'] + [k for k in attrs if k in allowed]
    vals = [course_id, name] + [attrs[k] for k in attrs if k in allowed]
    placeholders = ', '.join('?' * len(cols))
    with _db() as conn:
        conn.execute(
            f'INSERT INTO problem_sets ({", ".join(cols)}) VALUES ({placeholders})',
            vals
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_problem_set(ps_id):
    with _db() as conn:
        row = conn.execute('SELECT * FROM problem_sets WHERE id = ?', (ps_id,)).fetchone()
    return _row_to_problem_set(row) if row else None


def get_course_problem_sets(course_id):
    with _db() as conn:
        rows = conn.execute(
            'SELECT * FROM problem_sets WHERE course_id = ? ORDER BY name',
            (course_id,)
        ).fetchall()
    return [_row_to_problem_set(r) for r in rows]


def get_visible_problem_sets(course_id):
    """Problem sets visible to students: published and within time window."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM problem_sets
               WHERE course_id = ?
                 AND published = 1
                 AND (available_from IS NULL OR available_from <= datetime('now'))
               ORDER BY name""",
            (course_id,)
        ).fetchall()
    return [_row_to_problem_set(r) for r in rows]


def update_problem_set(ps_id, **fields):
    allowed = {'name', 'published', 'available_from', 'due_date', 'until',
               'time_limit_minutes', 'max_attempts_per_problem', 'release_solutions_at'}
    sets = ', '.join(f'{k} = ?' for k in fields if k in allowed)
    vals = [v for k, v in fields.items() if k in allowed]
    if not sets:
        return
    with _db() as conn:
        conn.execute(f'UPDATE problem_sets SET {sets} WHERE id = ?', vals + [ps_id])


def delete_problem_set(ps_id):
    with _db() as conn:
        conn.execute('DELETE FROM problem_sets WHERE id = ?', (ps_id,))


def get_problem_set_course_id(ps_id):
    with _db() as conn:
        row = conn.execute(
            'SELECT course_id FROM problem_sets WHERE id = ?', (ps_id,)
        ).fetchone()
    return row['course_id'] if row else None


# ── Problems ──────────────────────────────────────────────────────────────────

def _row_to_problem(row):
    return {
        'id':             row['id'],
        'problem_set_id': row['problem_set_id'],
        'position':       row['position'],
        'name':           row['name'],
        'premises':       json.loads(row['premises'] or '[]'),
        'conclusion':     row['conclusion'],
        'logic_type':     row['logic_type'],
        'points':         row['points'],
    }


def _next_position(conn, ps_id):
    row = conn.execute(
        'SELECT COALESCE(MAX(position), 0) + 1 FROM problems WHERE problem_set_id = ?',
        (ps_id,)
    ).fetchone()
    return row[0]


def add_problem(ps_id, name, premises, conclusion, logic_type='prop', points=None):
    premises_json = json.dumps(premises) if not isinstance(premises, str) else premises
    with _db() as conn:
        pos = _next_position(conn, ps_id)
        conn.execute(
            '''INSERT INTO problems
                   (problem_set_id, position, name, premises, conclusion, logic_type, points)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (ps_id, pos, name, premises_json, conclusion, logic_type, points)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_problem(problem_id):
    with _db() as conn:
        row = conn.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    return _row_to_problem(row) if row else None


def get_problem_set_problems(ps_id):
    with _db() as conn:
        rows = conn.execute(
            'SELECT * FROM problems WHERE problem_set_id = ? ORDER BY position',
            (ps_id,)
        ).fetchall()
    return [_row_to_problem(r) for r in rows]


def update_problem(problem_id, **fields):
    allowed = {'position', 'name', 'premises', 'conclusion', 'logic_type', 'points'}
    updates = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == 'premises' and not isinstance(v, str):
            v = json.dumps(v)
        updates[k] = v
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values())
    with _db() as conn:
        conn.execute(f'UPDATE problems SET {sets} WHERE id = ?', vals + [problem_id])


def delete_problem(problem_id):
    with _db() as conn:
        conn.execute('DELETE FROM problems WHERE id = ?', (problem_id,))


def problem_has_student_attempts(problem_id, instructor_email):
    """True if any non-instructor student has an attempt on this problem."""
    with _db() as conn:
        return bool(conn.execute(
            '''SELECT 1 FROM attempt_log
               WHERE problem_id = ? AND student_email != ?
               LIMIT 1''',
            (problem_id, instructor_email)
        ).fetchone())


def get_problem_course_instructor(problem_id):
    """Return the instructor_email for the course that owns this problem."""
    with _db() as conn:
        row = conn.execute(
            '''SELECT c.instructor_email FROM courses c
               JOIN problem_sets ps ON ps.course_id = c.id
               JOIN problems p ON p.problem_set_id = ps.id
               WHERE p.id = ?''',
            (problem_id,)
        ).fetchone()
    return row['instructor_email'] if row else None


# ── Solutions ─────────────────────────────────────────────────────────────────

def save_solution(problem_id, author_email, logic):
    logic_json = json.dumps(logic) if not isinstance(logic, str) else logic
    with _db() as conn:
        conn.execute(
            '''INSERT INTO solutions (problem_id, author_email, logic)
               VALUES (?, ?, ?)
               ON CONFLICT (problem_id) DO UPDATE SET
                   logic      = excluded.logic,
                   updated_at = datetime('now')''',
            (problem_id, author_email, logic_json)
        )


def get_solution(problem_id):
    with _db() as conn:
        row = conn.execute(
            'SELECT * FROM solutions WHERE problem_id = ?', (problem_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'problem_id':   row['problem_id'],
        'author_email': row['author_email'],
        'logic':        json.loads(row['logic'] or '[]'),
        'created_at':   row['created_at'],
        'updated_at':   row['updated_at'],
    }


def log_solution_access(accessor_email, problem_id):
    with _db() as conn:
        conn.execute(
            'INSERT INTO solution_access_log (accessor_email, problem_id) VALUES (?, ?)',
            (accessor_email, problem_id)
        )


def can_view_solution(email, problem_id):
    """True if email is the course instructor, or a permitted TA."""
    with _db() as conn:
        row = conn.execute(
            '''SELECT c.instructor_email, c.tas_can_view_solutions
               FROM courses c
               JOIN problem_sets ps ON ps.course_id = c.id
               JOIN problems p      ON p.problem_set_id = ps.id
               WHERE p.id = ?''',
            (problem_id,)
        ).fetchone()
    if not row:
        return False
    if row['instructor_email'] == email:
        return True
    if row['tas_can_view_solutions']:
        course_id_row = None
        with _db() as conn:
            course_id_row = conn.execute(
                '''SELECT ps.course_id FROM problem_sets ps
                   JOIN problems p ON p.problem_set_id = ps.id
                   WHERE p.id = ?''',
                (problem_id,)
            ).fetchone()
        if course_id_row:
            return is_ta(course_id_row['course_id'], email)
    return False


# ── Attempts ──────────────────────────────────────────────────────────────────

def get_attempt(student_email, problem_id):
    with _db() as conn:
        row = conn.execute(
            'SELECT * FROM attempts WHERE student_email = ? AND problem_id = ?',
            (student_email, problem_id)
        ).fetchone()
    if not row:
        return None
    return {
        'student_email': row['student_email'],
        'problem_id':    row['problem_id'],
        'current_logic': json.loads(row['current_logic'] or '[]'),
        'solved':        bool(row['solved']),
        'solve_count':   row['solve_count'],
        'started_at':    row['started_at'],
        'last_modified': row['last_modified'],
    }


def save_attempt(student_email, problem_id, logic, proof_completed):
    logic_json = json.dumps(logic) if not isinstance(logic, str) else logic
    solved = 1 if proof_completed else 0
    with _db() as conn:
        conn.execute(
            '''INSERT INTO attempts
                   (student_email, problem_id, current_logic, solved, solve_count, last_modified)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT (student_email, problem_id) DO UPDATE SET
                   current_logic = excluded.current_logic,
                   solved        = CASE WHEN excluded.solved = 1 THEN 1 ELSE solved END,
                   solve_count   = CASE WHEN excluded.solved = 1
                                        THEN solve_count + 1 ELSE solve_count END,
                   last_modified = datetime('now')''',
            (student_email, problem_id, logic_json, solved, solved)
        )


def log_attempt(student_email, problem_id, logic, proof_completed):
    logic_json = json.dumps(logic) if not isinstance(logic, str) else logic
    with _db() as conn:
        conn.execute(
            '''INSERT INTO attempt_log
                   (student_email, problem_id, logic_snapshot, proof_completed)
               VALUES (?, ?, ?, ?)''',
            (student_email, problem_id, logic_json, 1 if proof_completed else 0)
        )


def count_attempts_today(student_email, problem_id):
    with _db() as conn:
        return conn.execute(
            """SELECT COUNT(*) FROM attempt_log
               WHERE student_email = ?
                 AND problem_id = ?
                 AND date(checked_at) = date('now')""",
            (student_email, problem_id)
        ).fetchone()[0]


def get_problem_set_attempts(ps_id):
    """All student attempts for a problem set (for instructor download)."""
    with _db() as conn:
        rows = conn.execute(
            '''SELECT a.student_email, p.name AS problem_name, p.position,
                      p.points, a.solved, a.solve_count, a.last_modified,
                      a.current_logic
               FROM attempts a
               JOIN problems p ON p.id = a.problem_id
               WHERE p.problem_set_id = ?
               ORDER BY p.position, a.student_email''',
            (ps_id,)
        ).fetchall()
    return [{
        'student_email':  r['student_email'],
        'problem_name':   r['problem_name'],
        'position':       r['position'],
        'points':         r['points'],
        'solved':         bool(r['solved']),
        'solve_count':    r['solve_count'],
        'last_modified':  r['last_modified'],
        'current_logic':  json.loads(r['current_logic'] or '[]'),
    } for r in rows]
