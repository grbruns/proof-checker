"""
Proof rule checker.
Port of frontend/proofs.php.
"""

import re
from syntax import (
    parse_it, same_wff, sub_term,
    is_var, is_mon_op, is_quantifier,
)

TFL_RULES = {
    '∧I', '∧E', '⊥I', '⊥E', '→I', '→E', 'RAA', 'TND', '∨I', '∨E',
    '↔I', '↔E', 'DS', 'Rep', 'MT', 'DNE', 'DeM', 'Pr', 'Hyp', 'X',
    'IP', 'LEM', 'Bicondition',
}
FOL_RULES = {'∀E', '∀I', '∃I', '∃E', '=I', '=E', 'CQ'}

# (required line citations, required subproof citations)
CITE_NUMS = {
    '∧I': (2, 0), '∧E': (1, 0),
    '⊥I': (2, 0), '⊥E': (1, 0),
    '¬I': (0, 1), '¬E': (2, 0),
    '→I': (0, 1), '→E': (2, 0),
    'RAA': (0, 1), 'TND': (0, 2), 'LEM': (0, 2),
    '∨I': (1, 0), '∨E': (1, 2),
    '↔I': (0, 2), '↔E': (2, 0),
    'DS': (2, 0), 'Rep': (1, 0), 'MT': (2, 0),
    'DNE': (1, 0), 'DeM': (1, 0),
    '∀E': (1, 0), '∀I': (1, 0),
    '∃I': (1, 0), '∃E': (1, 1),
    '=I': (0, 0), '=E': (2, 0),
    'CQ': (1, 0),
    'Hyp': (0, 0), 'Pr': (0, 0),
    'X': (1, 0), 'IP': (0, 1),
    'Bicondition': (2, 0),
}

RULE_DISPLAY_NAMES = {
    'DNE': 'Double Negation',
    '→E': 'Modus Ponens',
    'MT': 'Modus Tollens',
    'DS': 'Modus Tollendo Ponens',
    '∧E': 'Simplification',
    '∨I': 'Addition',
    '∧I': 'Adjunction',
    '↔E': 'Equivalence',
    '↔I': 'Bicondition',
    '=E': 'Substitution of identicals',
    '=I': 'Identity introduction',
    '∀E': 'Universal instantiation',
    '∀I': 'Universal derivation',
    '∃E': 'Existential instantiation',
    '∃I': 'Existential generalization',
    'Rep': 'Repeat',
}


def display_name(rule):
    return RULE_DISPLAY_NAMES.get(rule, rule)


# ── Justification parsing ────────────────────────────────────────────────────

class J:
    def __init__(self):
        self.rules = []
        self.lines = []
        self.subps = []    # list of {'spstart': int, 'spend': int}
        self.parsed_ok = True
        self.err_msg = ''


def parse_j(jstr, predicate_settings):
    j = J()
    jstr = re.sub(r'[;,\s]+', ',', jstr)
    jstr = re.sub(r'[-–]+', '-', jstr)

    for part in jstr.split(','):
        if part == '':
            j.parsed_ok = False
            j.err_msg = 'Justification left blank.'
            return j

        if re.match(r'^[0-9]+$', part):
            j.lines.append(int(part))
            continue

        if re.match(r'^[0-9]+-[0-9]+$', part):
            start, end = part.split('-')
            j.subps.append({'spstart': int(start), 'spend': int(end)})
            continue

        allowed = TFL_RULES | (FOL_RULES if predicate_settings else set())
        if part in allowed:
            j.rules.append(part)
        else:
            j.parsed_ok = False
            j.err_msg = f'Justification cites nonexistent rule ({part}) or is badly formed.'
            return j

    if len(j.rules) > 1:
        j.parsed_ok = False
        j.err_msg = 'More than one rule cited.'
    elif len(j.rules) < 1:
        j.parsed_ok = False
        j.err_msg = 'No rule cited.'

    return j


# ── Proof structure ──────────────────────────────────────────────────────────

class Line:
    def __init__(self, wffstr, jstr, location):
        self.wffstr = wffstr
        self.jstr = jstr
        self.location = location
        self.issues = []
        self.wff = None
        self.j = None
        self.can_be_checked = False


def flatten_proof(pr, depth_prefix):
    result = []
    for i, item in enumerate(pr):
        if isinstance(item, list):
            result.extend(flatten_proof(item, depth_prefix + [i]))
        else:
            result.append(Line(item['wffstr'], item['jstr'], depth_prefix + [i]))
    return result


# ── Rule predicate functions ─────────────────────────────────────────────────

def sw(a, b, ps):
    return same_wff(a, b, ps)


def follows_by_conj_intro(rw, a, b, ps):
    return (
        rw.main_op == '∧' and (
            (sw(rw.right_side, a, ps) and sw(rw.left_side, b, ps)) or
            (sw(rw.right_side, b, ps) and sw(rw.left_side, a, ps))
        )
    )


def follows_by_conj_elim(rw, a, ps):
    return (
        a.main_op == '∧' and
        (sw(a.right_side, rw, ps) or sw(a.left_side, rw, ps))
    )


def follows_by_contra_intro(c, a, b, ps):
    return (
        c.wff_type == 'splat' and (
            (b.main_op == '¬' and sw(a, b.right_side, ps)) or
            (a.main_op == '¬' and sw(b, a.right_side, ps))
        )
    )


def follows_by_mp(c, a, b, ps):
    def one_way(c, a, b):
        return a.main_op == '→' and sw(a.right_side, c, ps) and sw(a.left_side, b, ps)
    return one_way(c, a, b) or one_way(c, b, a)


def follows_by_cp(c, a, b, ps):
    return (
        c.main_op == '→' and
        sw(c.left_side, a, ps) and
        sw(c.right_side, b, ps)
    )


def follows_by_ip(c, a, b, ps):
    return a.main_op == '¬' and sw(a.right_side, c, ps) and b.wff_type == 'splat'


def follows_by_raa2(c, a, b, d, ps):
    def one_way(c, a, b, d):
        return (
            a.main_op == '¬' and sw(a.right_side, c, ps) and
            d.main_op == '¬' and sw(d.right_side, b, ps)
        )
    return one_way(c, a, b, d) or one_way(c, a, d, b)


def follows_by_mt(c, a, b, ps):
    def one_way(c, a, b):
        return (
            a.main_op == '→' and b.main_op == '¬' and c.main_op == '¬' and
            sw(a.right_side, b.right_side, ps) and sw(a.left_side, c.right_side, ps)
        )
    return one_way(c, a, b) or one_way(c, b, a)


def follows_by_ds(c, a, b, ps):
    def one_way(c, a, b):
        return (
            a.main_op == '∨' and b.main_op == '¬' and (
                (sw(b.right_side, a.right_side, ps) and sw(c, a.left_side, ps)) or
                (sw(b.right_side, a.left_side, ps) and sw(c, a.right_side, ps))
            )
        )
    return one_way(c, a, b) or one_way(c, b, a)


def follows_by_dne(c, a, ps):
    return (
        (a.main_op == '¬' and a.right_side is not None and
         a.right_side.main_op == '¬' and sw(c, a.right_side.right_side, ps))
        or
        (c.main_op == '¬' and c.right_side is not None and
         c.right_side.main_op == '¬' and sw(a, c.right_side.right_side, ps))
    )


def follows_by_dem(c, a, ps):
    def one_way(a, b):
        return (
            b.main_op == '¬' and
            (
                (a.main_op == '∧' and b.right_side.main_op == '∨') or
                (a.main_op == '∨' and b.right_side.main_op == '∧')
            ) and
            a.right_side.main_op == '¬' and a.left_side.main_op == '¬' and
            sw(a.right_side.right_side, b.right_side.right_side, ps) and
            sw(a.left_side.right_side, b.right_side.left_side, ps)
        )
    return one_way(c, a) or one_way(a, c)


def follows_by_add(c, a, ps):
    return c.main_op == '∨' and (sw(c.left_side, a, ps) or sw(c.right_side, a, ps))


def follows_by_disj_elim(c, m, i, j, k, l, ps):
    def one_way(c, m, i, j, k, l):
        return (
            m.main_op == '∨' and
            sw(m.left_side, i, ps) and sw(m.right_side, k, ps) and
            sw(j, l, ps) and sw(j, c, ps)
        )
    return one_way(c, m, i, j, k, l) or one_way(c, m, k, l, i, j)


def follows_by_bicon_intro(c, i, j, k, l, ps):
    def one_way(c, i, j, k, l):
        return (
            c.main_op == '↔' and
            sw(c.left_side, i, ps) and sw(c.right_side, j, ps) and
            sw(c.right_side, k, ps) and sw(c.left_side, l, ps)
        )
    return one_way(c, i, j, k, l) or one_way(c, k, l, i, j)


def follows_by_bicon_elim(c, a, b, ps):
    def one_way(c, a, b):
        return (
            a.main_op == '↔' and (
                (sw(a.left_side, b, ps) and sw(a.right_side, c, ps)) or
                (sw(a.left_side, c, ps) and sw(a.right_side, b, ps)) or
                (b.right_side is not None and c.right_side is not None and
                 sw(a.left_side, b.right_side, ps) and sw(a.right_side, c.right_side, ps)) or
                (b.right_side is not None and c.right_side is not None and
                 sw(a.left_side, c.right_side, ps) and sw(a.right_side, b.right_side, ps))
            )
        )
    return one_way(c, a, b) or one_way(c, b, a)


def bicondition(c, a, b, ps):
    return (
        a.main_op == '→' and b.main_op == '→' and c.main_op == '↔' and
        sw(a.left_side, b.right_side, ps) and sw(a.right_side, b.left_side, ps) and
        (
            (sw(a.left_side, c.left_side, ps) and sw(a.right_side, c.right_side, ps)) or
            (sw(b.left_side, c.left_side, ps) and sw(b.right_side, c.right_side, ps))
        )
    )


def follows_by_tnd(c, i, j, k, l, ps):
    def one_way(c, i, j, k, l):
        return (
            k.main_op == '¬' and sw(k.right_side, i, ps) and
            sw(j, l, ps) and sw(c, j, ps)
        )
    return one_way(c, i, j, k, l) or one_way(c, k, l, i, j)


def is_self_id(w):
    return (
        w.wff_type == 'identity' and
        not is_var(w.my_terms[0]) and
        w.my_terms[0] == w.my_terms[1]
    )


def differs_by_swapping_for(q, p, s, t, ps):
    if p.wff_type != q.wff_type:
        return False
    if p.wff_type == 'splat':
        return True
    if p.wff_type in ('atomic', 'identity'):
        if len(p.my_terms) != len(q.my_terms):
            return False
        if p.wff_type == 'atomic' and p.my_letter != q.my_letter:
            return False
        for i in range(len(p.my_terms)):
            if p.my_terms[i] != q.my_terms[i]:
                if not (p.my_terms[i] == t and q.my_terms[i] == s):
                    return False
        return True
    if p.main_op != q.main_op:
        return False
    if is_mon_op(p.main_op):
        return differs_by_swapping_for(q.right_side, p.right_side, s, t, ps)
    return (
        differs_by_swapping_for(q.right_side, p.right_side, s, t, ps) and
        differs_by_swapping_for(q.left_side, p.left_side, s, t, ps)
    )


def follows_by_ll(c, a, b, ps):
    def one_way(c, a, b):
        return (
            a.wff_type == 'identity' and (
                differs_by_swapping_for(c, b, a.my_terms[0], a.my_terms[1], ps) or
                differs_by_swapping_for(c, b, a.my_terms[1], a.my_terms[0], ps)
            )
        )
    return one_way(c, a, b) or one_way(c, b, a)


def follows_by_ui(c, a):
    if a.main_op != '∀':
        return False
    for t in c.my_terms:
        if not is_var(t):
            if same_wff(c, sub_term(a.right_side, t, a.my_letter), True):
                return True
    if a.my_letter not in a.right_side.all_free_vars:
        if same_wff(c, a.right_side, True):
            return True
    return False


def follows_by_eg(c, a):
    if c.main_op != '∃':
        return False
    if c.my_letter not in c.right_side.all_free_vars:
        return same_wff(c.right_side, a, True)
    if c.my_letter in a.my_terms:
        return False
    for t in a.my_terms:
        if not is_var(t):
            if same_wff(a, sub_term(c.right_side, t, c.my_letter), True):
                return True
    return False


def follows_by_ei(c, a):
    if a.main_op != '∃':
        return False
    for t in c.my_terms:
        if not is_var(t):
            if same_wff(c, sub_term(a.right_side, t, a.my_letter), True):
                return True
    if a.my_letter not in a.right_side.all_free_vars:
        if same_wff(c, a.right_side, True):
            return True
    return False


def follows_by_cq(a, b):
    def one_way(a, b):
        return (
            a.main_op == '¬' and
            b.right_side is not None and b.right_side.main_op == '¬' and
            (
                (a.right_side.main_op == '∀' and b.main_op == '∃') or
                (a.right_side.main_op == '∃' and b.main_op == '∀')
            ) and
            b.my_letter == a.right_side.my_letter and
            same_wff(a.right_side.right_side, b.right_side.right_side, True)
        )
    return one_way(a, b) or one_way(b, a)


# ── Scope helpers ────────────────────────────────────────────────────────────

def line_is_available(cited_loc, citing_loc):
    """Return True if a line at cited_loc is in scope for a line at citing_loc."""
    if len(cited_loc) > len(citing_loc):
        return False
    for d in range(len(cited_loc) - 1):
        if cited_loc[d] != citing_loc[d]:
            return False
    return True


def subproof_is_valid(start_loc, end_loc):
    """Return True if start and end locations form a valid subproof."""
    if len(start_loc) != len(end_loc):
        return False
    if start_loc[-1] != 0:
        return False
    for d in range(len(start_loc) - 1):
        if start_loc[d] != end_loc[d]:
            return False
    return True


def subproof_is_available(start_loc, citing_loc):
    """Return True if a subproof (given by start_loc) is in scope."""
    cloc = start_loc[:-1]
    if len(cloc) != len(citing_loc):
        return False
    for d in range(len(cloc) - 1):
        if cloc[d] != citing_loc[d]:
            return False
    return True


# ── ∀I helper: check if term t appears in any reachable Pr/Hyp ──────────────

def term_in_reachable_premise(t, i, fpr):
    for j in range(i):
        if fpr[j].j and fpr[j].j.rules and fpr[j].j.rules[0] in ('Pr', 'Hyp'):
            if line_is_available(fpr[j].location, fpr[i].location):
                if t in fpr[j].wff.my_terms:
                    return True
    return False


# ── Main proof checker ───────────────────────────────────────────────────────

def check_proof(pr_data, numprems, conc, predicate_settings=False):
    ps = predicate_settings
    issues = []
    conc_reached = False

    fpr = flatten_proof(pr_data, [])

    # Parse formula on each line
    for line in fpr:
        line.wff = parse_it(line.wffstr, ps)
        if not line.wff.is_well_formed:
            line.issues.append('Not well-formed: ' + line.wff.err_msg)

    # Parse justification on each line
    for line in fpr:
        line.j = parse_j(line.jstr, ps)
        if not line.j.parsed_ok:
            line.issues.append('Cannot parse justification: ' + line.j.err_msg)

    # Check citation counts
    for line in fpr:
        if not line.j.parsed_ok:
            continue
        rule = line.j.rules[0]
        good_lc, good_spc = CITE_NUMS[rule]
        act_lc = len(line.j.lines)
        act_spc = len(line.j.subps)
        if act_lc < good_lc:
            line.issues.append(f'Cites too few line numbers for the rule {display_name(rule)}.')
        if act_lc > good_lc:
            line.issues.append(f'Cites too many line numbers for the rule {display_name(rule)}.')
        if act_spc < good_spc:
            line.issues.append(f'Cites too few ranges of lines for the rule {display_name(rule)}.')
        if act_spc > good_spc:
            line.issues.append(f'Cites too many ranges of lines for the rule {display_name(rule)}.')

    # Check that cited lines exist and are in scope
    n_lines = len(fpr)
    for i, line in enumerate(fpr):
        if not line.j.parsed_ok:
            continue
        n = i + 1
        nloc = line.location

        for cited in line.j.lines:
            if cited < 1 or cited > n_lines:
                line.issues.append(f'Cites nonexistent line ({cited}).')
                continue
            if cited == n:
                line.issues.append(f'Cites itself.')
                continue
            if cited > n:
                line.issues.append(f'Cites a line ({cited}) that occurs after it.')
                continue
            cloc = fpr[cited - 1].location
            if not line_is_available(cloc, nloc):
                line.issues.append(f'Cites an unavailable line ({cited}).')

        for sp in line.j.subps:
            start, end = sp['spstart'], sp['spend']
            if start > end:
                line.issues.append(f'Cites a range of lines in the wrong order ({start}–{end}).')
                continue
            if start < 1 or end > n_lines:
                line.issues.append(f'Cites a line nonexistent range of lines ({start}–{end}).')
                continue
            if end >= n:
                line.issues.append(f'Cites a line range after or including itself ({start}–{end}).')
                continue
            start_loc = fpr[start - 1].location
            end_loc = fpr[end - 1].location
            if not subproof_is_valid(start_loc, end_loc):
                line.issues.append(f'Cites a range of lines which do not make up a subproof ({start}–{end}).')
                continue
            if not subproof_is_available(start_loc, nloc):
                line.issues.append(f'Cites an unavailable subproof ({start}–{end}).')

    # Mark lines that can be rule-checked (no prior issues, cited lines well-formed)
    for i, line in enumerate(fpr):
        line.can_be_checked = len(line.issues) == 0
        if not line.can_be_checked:
            continue
        for cl in line.j.lines:
            if not fpr[cl - 1].wff.is_well_formed:
                line.can_be_checked = False
                line.issues.append(f'Cites another line that is not well-formed ({cl}).')
        for sp in line.j.subps:
            for end in (sp['spstart'], sp['spend']):
                if not fpr[end - 1].wff.is_well_formed:
                    line.can_be_checked = False
                    line.issues.append(f'Cites another line that is not well-formed ({end}).')

    # Apply proof rules
    for i, line in enumerate(fpr):
        if not line.can_be_checked:
            continue
        rule = line.j.rules[0]
        c = line.wff

        def cited(k):
            return fpr[line.j.lines[k] - 1].wff

        def sp_start(k):
            return fpr[line.j.subps[k]['spstart'] - 1].wff

        def sp_end(k):
            return fpr[line.j.subps[k]['spend'] - 1].wff

        worked = False

        if rule == 'Pr':
            worked = (i + 1) <= numprems

        elif rule == 'Hyp':
            worked = (line.location[-1] == 0)

        elif rule == '∧I':
            worked = follows_by_conj_intro(c, cited(0), cited(1), ps)

        elif rule == '∧E':
            worked = follows_by_conj_elim(c, cited(0), ps)

        elif rule == '⊥E' or rule == 'X':
            worked = fpr[line.j.lines[0] - 1].wff.wff_type == 'splat'

        elif rule == '⊥I':
            worked = follows_by_contra_intro(c, cited(0), cited(1), ps)

        elif rule == '→E':
            worked = follows_by_mp(c, cited(0), cited(1), ps)

        elif rule == '→I':
            worked = follows_by_cp(c, sp_start(0), sp_end(0), ps)

        elif rule == 'IP':
            worked = follows_by_ip(c, sp_start(0), sp_end(0), ps)

        elif rule == 'RAA':
            sp = line.j.subps[0]
            hyp  = fpr[sp['spstart'] - 1].wff
            res1 = fpr[sp['spend'] - 2].wff
            res2 = fpr[sp['spend'] - 1].wff
            loc1 = fpr[sp['spend'] - 2].location
            loc2 = fpr[sp['spend'] - 1].location
            if len(loc1) != len(loc2):
                worked = False
            else:
                worked = follows_by_raa2(c, hyp, res1, res2, ps)

        elif rule in ('TND', 'LEM'):
            worked = follows_by_tnd(c, sp_start(0), sp_end(0), sp_start(1), sp_end(1), ps)

        elif rule == '∨I':
            worked = follows_by_add(c, cited(0), ps)

        elif rule == '∨E':
            worked = follows_by_disj_elim(
                c, cited(0),
                sp_start(0), sp_end(0),
                sp_start(1), sp_end(1), ps,
            )

        elif rule == '↔I':
            worked = follows_by_bicon_intro(
                c,
                sp_start(0), sp_end(0),
                sp_start(1), sp_end(1), ps,
            )

        elif rule == '↔E':
            worked = follows_by_bicon_elim(c, cited(0), cited(1), ps)

        elif rule == 'DS':
            worked = follows_by_ds(c, cited(0), cited(1), ps)

        elif rule == 'Rep':
            worked = same_wff(c, cited(0), ps)

        elif rule == 'MT':
            worked = follows_by_mt(c, cited(0), cited(1), ps)

        elif rule == 'Bicondition':
            worked = bicondition(c, cited(0), cited(1), ps)

        elif rule == 'DNE':
            worked = follows_by_dne(c, cited(0), ps)

        elif rule == 'DeM':
            worked = follows_by_dem(c, cited(0), ps)

        elif rule == '∀E':
            worked = follows_by_ui(c, cited(0))

        elif rule == '∃I':
            worked = follows_by_eg(c, cited(0))

        elif rule == '∀I':
            univ = c
            if univ.main_op != '∀':
                worked = False
            else:
                inst = cited(0)
                bound = univ.my_letter
                if bound in univ.right_side.all_free_vars:
                    worked = False
                    for t in inst.my_terms:
                        if t in univ.my_terms:
                            continue
                        if not is_var(t):
                            if same_wff(inst, sub_term(univ.right_side, t, bound), True):
                                if not term_in_reachable_premise(t, i, fpr):
                                    worked = True
                else:
                    worked = same_wff(univ.right_side, inst, True)

        elif rule == '∃E':
            exwff = cited(0)
            if exwff.main_op != '∃':
                worked = False
            else:
                sp_hyp_wff = sp_start(0)
                sp_res_wff = sp_end(0)
                res = c
                if not same_wff(sp_res_wff, res, True):
                    worked = False
                elif exwff.my_letter in exwff.right_side.all_free_vars:
                    worked = False
                    for t in sp_hyp_wff.my_terms:
                        if not is_var(t):
                            if same_wff(sp_hyp_wff, sub_term(exwff.right_side, t, exwff.my_letter), True):
                                if t in res.my_terms or t in exwff.my_terms:
                                    continue
                                if not term_in_reachable_premise(t, i, fpr):
                                    worked = True
                else:
                    worked = same_wff(exwff.right_side, sp_hyp_wff, True)

        elif rule == '=I':
            worked = is_self_id(c)

        elif rule == '=E':
            worked = follows_by_ll(c, cited(0), cited(1), ps)

        elif rule == 'CQ':
            worked = follows_by_cq(c, cited(0))

        elif rule in ('¬I',):
            # ¬I: assume P, derive ⊥, conclude ¬P (not used in DeLancey but kept for completeness)
            worked = (
                c.main_op == '¬' and
                same_wff(c.right_side, sp_start(0), ps) and
                sp_end(0).wff_type == 'splat'
            )

        elif rule == '¬E':
            worked = follows_by_contra_intro(c, cited(0), cited(1), ps)

        if not worked:
            line.issues.append(
                f'Is not a proper application of the rule {display_name(rule)} (for the line(s) cited).'
            )

    # Merge all per-line issues into the result
    for i, line in enumerate(fpr):
        for issue in line.issues:
            issues.append(f'Line {i + 1}: {issue}')

    # Check whether the conclusion was reached (only if no issues)
    if not issues:
        conc_wff = parse_it(conc, ps)
        if not conc_wff.is_well_formed:
            issues.append('Desired conclusion is not a wff. Oops!')
        else:
            for line in fpr:
                if len(line.location) == 1 and same_wff(line.wff, conc_wff, ps):
                    conc_reached = True

    return {'issues': issues, 'concReached': conc_reached}
