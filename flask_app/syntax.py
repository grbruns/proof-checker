"""
Formula parser for propositional and first-order logic.
Port of frontend/syntax.php (which itself was ported from frontend/syntax.js).
"""

import re

BIN_OPS = frozenset(['→', '∨', '∧', '↔'])
MON_OPS = frozenset(['¬', '∀', '∃'])
QUANTIFIERS = frozenset(['∀', '∃'])
VARS = frozenset(['x', 'y', 'z'])


class Wff:
    def __init__(self):
        self.is_well_formed = True
        self.err_msg = "none"
        self.wff_type = 'unknown'
        self.main_op = '?'
        self.my_letter = ''
        self.left_side = None
        self.right_side = None
        self.my_terms = []
        self.all_free_vars = []


def _err(msg):
    w = Wff()
    w.is_well_formed = False
    w.err_msg = msg
    return w


def is_bin_op(ch):
    return ch in BIN_OPS


def is_mon_op(ch):
    return ch in MON_OPS


def is_op(ch):
    return ch in BIN_OPS or ch in MON_OPS


def is_quantifier(ch):
    return ch in QUANTIFIERS


def is_var(ch):
    return ch in VARS


def list_union(a, b):
    seen = set(a)
    return list(a) + [x for x in b if x not in seen]


def has_stray_chars(s, predicate_settings):
    if predicate_settings:
        return bool(re.search(r'[^A-Za-z∀∃=¬∨∧↔→⊥\s()\[\]{}]', s))
    else:
        return bool(re.search(r'[^A-Z¬∨∧↔→⊥\s()\[\]{}]', s))


def regularize(s):
    s = s.replace('[', '(').replace('{', '(')
    s = s.replace(']', ')').replace('}', ')')
    s = re.sub(r'\s', '', s)
    return s


def parse_it(s, predicate_settings=False):
    s = regularize(s)

    if s == '':
        return _err("Formula or subformula is blank.")

    if has_stray_chars(s, predicate_settings):
        if predicate_settings:
            return _err(
                "Input field contains characters or punctuation not allowed in the language of FOL. "
                "A statement should contain only parentheses ( [ { } ] ), predicates A–Z and =, "
                "terms a–w, variables x–z, the contradiction symbol ⊥, and the operators "
                "¬, ∨, ∧, →, ↔, ∃, ∀ (or their alternatives)."
            )
        else:
            return _err(
                "Input field contains characters or punctuation not allowed in the language of TFL. "
                "A statement should contain only parentheses ( [ { } ] ), statement letters A–Z, "
                "the contradiction symbol ⊥, and the operators ¬, ∨, ∧, →, "
                "and ↔ (or their alternatives)."
            )

    # Build depth array and check paren balance
    depth = 0
    depth_array = []
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        depth_array.append(depth)

    if depth_array[-1] != 0:
        return _err("Parentheses are unbalanced.")

    # Strip matching outermost parens
    if depth_array[0] == 1:
        if all(d > 0 for d in depth_array[1:-1]):
            return parse_it(s[1:-1], predicate_settings)

    # Atomic family: string contains no operators
    if not re.search(r'[¬∧∨→↔∀∃]', s):
        if re.search(r'[()]', s):
            return _err("Misplaced parentheses.")

        if s == '⊥':
            w = Wff()
            w.wff_type = 'splat'
            return w

        if '⊥' in s:
            return _err("Formula contains ⊥ but not in isolation.")

        if '=' in s:
            if re.match(r'^[a-z]=[a-z]$', s):
                w = Wff()
                w.wff_type = 'identity'
                w.my_terms = s.split('=')
                w.all_free_vars = []
                if is_var(w.my_terms[0]):
                    w.all_free_vars.append(w.my_terms[0])
                if is_var(w.my_terms[1]) and w.my_terms[1] != w.my_terms[0]:
                    w.all_free_vars.append(w.my_terms[1])
                return w
            else:
                return _err(
                    "Poorly formed identity statement. "
                    "Identity statement should be of the form t = s."
                )

        if not predicate_settings:
            if re.match(r'^[A-Z]$', s):
                w = Wff()
                w.wff_type = 'atomic'
                w.my_letter = s
                return w
            else:
                return _err(
                    "Poorly formed atomic statement. "
                    "In TFL, an atomic statement should be a single statement letter."
                )

        # Predicate-logic atomic
        if not re.search(r'[A-Z]', s):
            return _err("An atomic formula must begin with a predicate.")
        if len(s) == 1:
            return _err("An atomic formula must have terms, not just a predicate.")
        if re.search(r'.+[A-Z]', s):
            return _err("Predicates may only appear at the beginning of an atomic formula.")
        if re.search(r'.+[^a-z]', s):
            return _err("An atomic formula should contain only predicates followed by terms.")
        w = Wff()
        w.wff_type = 'atomic'
        w.my_letter = s[0]
        w.my_terms = list(s[1:])
        seen = set()
        w.all_free_vars = []
        for t in w.my_terms:
            if is_var(t) and t not in seen:
                w.all_free_vars.append(t)
                seen.add(t)
        return w

    # Find main operator (scan left to right at depth 0)
    main_op = '?'
    main_op_pos = 0
    for i, ch in enumerate(s):
        if is_op(ch) and depth_array[i] == 0:
            if main_op == '?':
                main_op = ch
                main_op_pos = i
            elif is_bin_op(main_op) and is_bin_op(ch):
                return _err("Too many operators or too few parentheses to disambiguate.")
            elif is_mon_op(main_op) and is_bin_op(ch):
                main_op = ch
                main_op_pos = i

    if main_op == '?':
        return _err("Missing connective/operator or misplaced parentheses.")

    w = Wff()
    w.main_op = main_op

    # Quantified formula
    if is_quantifier(main_op):
        w.wff_type = 'quantified'
        if main_op_pos != 0:
            return _err("Misuse of a quantifier internally in a formula.")
        if len(s) < 2 or not is_var(s[1]):
            return _err("A quantifier is used without binding a variable.")
        w.my_letter = s[1]
        w.right_side = parse_it(s[2:], predicate_settings)
        if not w.right_side.is_well_formed:
            return _err(w.right_side.err_msg)
        w.my_terms = list(w.right_side.my_terms)
        if w.my_letter not in w.my_terms:
            w.my_terms.append(w.my_letter)
        w.all_free_vars = [v for v in w.right_side.all_free_vars if v != w.my_letter]
        return w

    w.wff_type = 'molecular'

    # Negation
    if main_op == '¬':
        if main_op_pos != 0:
            return _err("Misuse of negation internally in formula.")
        w.right_side = parse_it(s[1:], predicate_settings)
        if not w.right_side.is_well_formed:
            return _err(w.right_side.err_msg)
        if predicate_settings:
            w.my_terms = list(w.right_side.my_terms)
            w.all_free_vars = list(w.right_side.all_free_vars)
        return w

    # Binary molecular
    w.left_side = parse_it(s[:main_op_pos], predicate_settings)
    if not w.left_side.is_well_formed:
        return _err(w.left_side.err_msg)

    w.right_side = parse_it(s[main_op_pos + 1:], predicate_settings)
    if not w.right_side.is_well_formed:
        return _err(w.right_side.err_msg)

    if predicate_settings:
        w.my_terms = list_union(w.left_side.my_terms, w.right_side.my_terms)
        w.all_free_vars = list_union(w.left_side.all_free_vars, w.right_side.all_free_vars)

    return w


def same_wff(a, b, predicate_settings=False):
    if a.wff_type != b.wff_type:
        return False
    if a.wff_type == 'splat':
        return True
    if a.wff_type == 'identity':
        return a.my_terms[0] == b.my_terms[0] and a.my_terms[1] == b.my_terms[1]
    if a.wff_type == 'atomic':
        if predicate_settings:
            if a.my_letter != b.my_letter or len(a.my_terms) != len(b.my_terms):
                return False
            return all(a.my_terms[i] == b.my_terms[i] for i in range(len(a.my_terms)))
        return a.my_letter == b.my_letter
    if a.main_op != b.main_op:
        return False
    if is_quantifier(a.main_op) and a.my_letter != b.my_letter:
        return False
    if is_mon_op(a.main_op):
        return same_wff(a.right_side, b.right_side, predicate_settings)
    return (same_wff(a.left_side, b.left_side, predicate_settings) and
            same_wff(a.right_side, b.right_side, predicate_settings))


def sub_term(w, n, v):
    """Return w with every free occurrence of variable v replaced by term n."""
    if v not in w.all_free_vars:
        x = Wff()
        x.__dict__.update(w.__dict__)
        return x

    x = Wff()
    x.wff_type = w.wff_type
    x.main_op = w.main_op
    x.my_letter = w.my_letter
    x.all_free_vars = [nv for nv in w.all_free_vars if nv != v]

    if w.wff_type in ('atomic', 'identity'):
        x.my_terms = [n if t == v else t for t in w.my_terms]
        return x

    x.right_side = sub_term(w.right_side, n, v)
    x.my_terms = list(x.right_side.my_terms)

    if is_mon_op(x.main_op):
        return x

    x.left_side = sub_term(w.left_side, n, v)
    x.my_terms = list_union(x.my_terms, x.left_side.my_terms)
    return x
