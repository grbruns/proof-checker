"""
Regression tests for checkproof.php (and eventually its Flask replacement).

Organization:
  - TestFormulaParsing   — malformed wffstr inputs
  - TestJustificationParsing — malformed jstr inputs
  - TestScope            — subproof scope rules
  - TestPr               — Pr (premise)
  - TestRep              — Rep (repeat)
  - TestConjunction      — ∧I and ∧E
  - TestModusPonens      — →E
  - TestConditional      — →I (conditional derivation)
  - TestModusTollens     — MT
  - TestDisjunction      — ∨I, ∨E, DS
  - TestBiconditional    — ↔I, ↔E, Bicondition
  - TestNegation         — DNE, DeM, ⊥I, ⊥E
  - TestReductio         — RAA, IP, TND
  - TestFOL              — First-order rules: ∀E, ∃I, =I, =E, CQ

How to read the proof_data format:
  A list of items.  Each item is either:
    {"wffstr": "P ∧ Q", "jstr": "Pr"}   — a single proof line
    [{...}, {...}]                        — a subproof (nested list)
  Line numbers are 1-indexed in jstr citations, e.g. "→E,1,2" or "→I,2-3".
"""

import pytest
from conftest import assert_valid, assert_invalid, assert_issue_contains


# ═══════════════════════════════════════════════════════════════
# Formula parsing
# ═══════════════════════════════════════════════════════════════

class TestFormulaParsing:

    def test_simple_atomic(self, check_proof):
        result = check_proof(
            [{"wffstr": "P", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_empty_wffstr(self, check_proof):
        result = check_proof(
            [{"wffstr": "", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)
        assert_issue_contains(result, "blank")

    def test_stray_character(self, check_proof):
        # "+" is not a valid logic operator
        result = check_proof(
            [{"wffstr": "P + Q", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)

    def test_ascii_operator_rejected(self, check_proof):
        # "^" is accepted by the UI (converted to ∧) but PHP needs Unicode
        result = check_proof(
            [{"wffstr": "P ^ Q", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)

    def test_unbalanced_left_paren(self, check_proof):
        result = check_proof(
            [{"wffstr": "(P ∧ Q", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P ∧ Q"
        )
        assert_invalid(result)

    def test_unbalanced_right_paren(self, check_proof):
        result = check_proof(
            [{"wffstr": "P ∧ Q)", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P ∧ Q"
        )
        assert_invalid(result)

    def test_ambiguous_without_parens(self, check_proof):
        # P ∧ Q ∨ R is ambiguous (two binary operators at top level)
        result = check_proof(
            [{"wffstr": "P ∧ Q ∨ R", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P ∧ Q ∨ R"
        )
        assert_invalid(result)

    def test_parenthesized_binary(self, check_proof):
        # Same formula becomes unambiguous with parens
        result = check_proof(
            [{"wffstr": "(P ∧ Q) ∨ R", "jstr": "Pr"}],
            num_prems=1, wanted_conc="(P ∧ Q) ∨ R"
        )
        assert_valid(result)

    def test_negation_of_compound(self, check_proof):
        result = check_proof(
            [{"wffstr": "¬(P ∨ Q)", "jstr": "Pr"}],
            num_prems=1, wanted_conc="¬(P ∨ Q)"
        )
        assert_valid(result)

    def test_double_negation_formula(self, check_proof):
        result = check_proof(
            [{"wffstr": "¬¬P", "jstr": "Pr"}],
            num_prems=1, wanted_conc="¬¬P"
        )
        assert_valid(result)

    def test_contradiction_symbol(self, check_proof):
        result = check_proof(
            [{"wffstr": "⊥", "jstr": "Pr"}],
            num_prems=1, wanted_conc="⊥"
        )
        assert_valid(result)


# ═══════════════════════════════════════════════════════════════
# Justification parsing
# ═══════════════════════════════════════════════════════════════

class TestJustificationParsing:

    def test_blank_justification(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": ""},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)
        assert_issue_contains(result, "blank")

    def test_unknown_rule_name(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "XYZ,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)

    def test_too_few_line_citations(self, check_proof):
        # ∧I requires 2 cited lines; providing only 1 should fail
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "P ∧ Q", "jstr": "∧I,1"},
            ],
            num_prems=2, wanted_conc="P ∧ Q"
        )
        assert_invalid(result)
        assert_issue_contains(result, "too few line numbers")

    def test_too_many_line_citations(self, check_proof):
        # ∧E requires 1 cited line; providing 2 should fail
        result = check_proof(
            [
                {"wffstr": "P ∧ Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "∧E,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_invalid(result)
        assert_issue_contains(result, "too many line numbers")

    def test_nonexistent_line_citation(self, check_proof):
        # Citing line 99 when there are only 2 lines
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Rep,99"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)

    def test_forward_citation_rejected(self, check_proof):
        # A line cannot cite a line that comes after it
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Rep,3"},
                {"wffstr": "P", "jstr": "Rep,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# Subproof scope rules
# ═══════════════════════════════════════════════════════════════

class TestScope:

    def test_cannot_cite_line_inside_closed_subproof(self, check_proof):
        """
        After a subproof closes, its lines are no longer in scope.
        Line 1 (P, Hyp) is inside the subproof; line 3 cannot cite it.
        """
        result = check_proof(
            [
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "Rep,1"},
                ],
                {"wffstr": "P", "jstr": "Rep,1"},   # line 1 is out of scope here
            ],
            num_prems=0, wanted_conc="P"
        )
        assert_invalid(result)
        assert_issue_contains(result, "unavailable")

    def test_subproof_can_cite_outer_line(self, check_proof):
        """
        A line inside a subproof CAN cite lines from an enclosing scope.
        """
        result = check_proof(
            [
                {"wffstr": "P ∧ Q", "jstr": "Pr"},
                [
                    {"wffstr": "R", "jstr": "Hyp"},
                    {"wffstr": "P ∧ Q", "jstr": "Rep,1"},   # line 1 is in outer scope
                ],
                {"wffstr": "R → (P ∧ Q)", "jstr": "→I,2-3"},
            ],
            num_prems=1, wanted_conc="R → (P ∧ Q)"
        )
        assert_valid(result)

    def test_conclusion_inside_subproof_does_not_count(self, check_proof):
        """
        A formula that appears only inside a subproof does not satisfy the
        top-level conclusion requirement.
        """
        result = check_proof(
            [
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "Rep,1"},
                ]
            ],
            num_prems=0, wanted_conc="P"
        )
        assert result["concReached"] is False


# ═══════════════════════════════════════════════════════════════
# Pr — Premise
# ═══════════════════════════════════════════════════════════════

class TestPr:

    def test_single_premise(self, check_proof):
        result = check_proof(
            [{"wffstr": "P", "jstr": "Pr"}],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_two_premises(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_valid(result)

    def test_pr_beyond_num_prems_rejected(self, check_proof):
        # numPrems=1 but line 2 also claims to be a premise
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
            ],
            num_prems=1, wanted_conc="Q"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# Rep — Repeat
# ═══════════════════════════════════════════════════════════════

class TestRep:

    def test_valid_repeat(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Rep,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_repeat_different_formula_rejected(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Rep,1"},
            ],
            num_prems=1, wanted_conc="Q"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# ∧I and ∧E — Conjunction introduction and elimination
# ═══════════════════════════════════════════════════════════════

class TestConjunction:

    def test_conjunction_intro(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "P ∧ Q", "jstr": "∧I,1,2"},
            ],
            num_prems=2, wanted_conc="P ∧ Q"
        )
        assert_valid(result)

    def test_conjunction_intro_reversed_conjuncts(self, check_proof):
        # Can form Q ∧ P from lines P and Q in either order
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "Q ∧ P", "jstr": "∧I,1,2"},
            ],
            num_prems=2, wanted_conc="Q ∧ P"
        )
        assert_valid(result)

    def test_conjunction_intro_wrong_connective(self, check_proof):
        # ∨ is not ∧
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "P ∨ Q", "jstr": "∧I,1,2"},
            ],
            num_prems=2, wanted_conc="P ∨ Q"
        )
        assert_invalid(result)

    def test_conjunction_elim_left(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P ∧ Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "∧E,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_conjunction_elim_right(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P ∧ Q", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "∧E,1"},
            ],
            num_prems=1, wanted_conc="Q"
        )
        assert_valid(result)

    def test_conjunction_elim_wrong_formula(self, check_proof):
        # P → Q cannot be extracted from P ∧ Q
        result = check_proof(
            [
                {"wffstr": "P ∧ Q", "jstr": "Pr"},
                {"wffstr": "P → Q", "jstr": "∧E,1"},
            ],
            num_prems=1, wanted_conc="P → Q"
        )
        assert_invalid(result)

    def test_conjunction_elim_from_non_conjunction(self, check_proof):
        # P ∨ Q is not a conjunction
        result = check_proof(
            [
                {"wffstr": "P ∨ Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "∧E,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# →E — Modus Ponens
# ═══════════════════════════════════════════════════════════════

class TestModusPonens:

    def test_valid_mp(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "→E,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_valid(result)

    def test_mp_lines_cited_in_either_order(self, check_proof):
        # →E should work regardless of which line is the conditional
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "→E,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_valid(result)

    def test_mp_wrong_conclusion(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "→E,1,2"},   # should be Q
            ],
            num_prems=2, wanted_conc="P"
        )
        assert_invalid(result)

    def test_mp_antecedent_not_present(self, check_proof):
        # P → Q and R: the antecedent doesn't match
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "R", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "→E,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# →I — Conditional Derivation
# ═══════════════════════════════════════════════════════════════

class TestConditional:

    def test_trivial_self_conditional(self, check_proof):
        """P → P: assume P, derive P by Rep, discharge."""
        result = check_proof(
            [
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "Rep,1"},
                ],
                {"wffstr": "P → P", "jstr": "→I,1-2"},
            ],
            num_prems=0, wanted_conc="P → P"
        )
        assert_valid(result)

    def test_cd_using_outer_premise(self, check_proof):
        """R → (P → Q): assume P → Q from outside, assume R, use Rep, discharge."""
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                [
                    {"wffstr": "R", "jstr": "Hyp"},
                    {"wffstr": "P → Q", "jstr": "Rep,1"},   # cites outer line
                ],
                {"wffstr": "R → (P → Q)", "jstr": "→I,2-3"},
            ],
            num_prems=1, wanted_conc="R → (P → Q)"
        )
        assert_valid(result)

    def test_cd_wrong_antecedent(self, check_proof):
        # Subproof assumes P but conclusion says Q → P
        result = check_proof(
            [
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "Rep,1"},
                ],
                {"wffstr": "Q → P", "jstr": "→I,1-2"},   # antecedent should be P, not Q
            ],
            num_prems=0, wanted_conc="Q → P"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# MT — Modus Tollens
# ═══════════════════════════════════════════════════════════════

class TestModusTollens:

    def test_valid_mt(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "¬Q", "jstr": "Pr"},
                {"wffstr": "¬P", "jstr": "MT,1,2"},
            ],
            num_prems=2, wanted_conc="¬P"
        )
        assert_valid(result)

    def test_mt_wrong_negation(self, check_proof):
        # From P → Q and ¬Q we get ¬P, not ¬Q
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "¬Q", "jstr": "Pr"},
                {"wffstr": "¬Q", "jstr": "MT,1,2"},
            ],
            num_prems=2, wanted_conc="¬Q"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# ∨I, DS, ∨E — Disjunction
# ═══════════════════════════════════════════════════════════════

class TestDisjunction:

    def test_addition_left_disjunct(self, check_proof):
        # P ⊢ P ∨ Q
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P ∨ Q", "jstr": "∨I,1"},
            ],
            num_prems=1, wanted_conc="P ∨ Q"
        )
        assert_valid(result)

    def test_addition_right_disjunct(self, check_proof):
        # Q ⊢ P ∨ Q  (cited formula is the right disjunct)
        result = check_proof(
            [
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "P ∨ Q", "jstr": "∨I,1"},
            ],
            num_prems=1, wanted_conc="P ∨ Q"
        )
        assert_valid(result)

    def test_addition_formula_not_a_disjunct(self, check_proof):
        # P cannot justify P ∨ Q ∨ R without brackets if cited formula doesn't match either disjunct
        result = check_proof(
            [
                {"wffstr": "R", "jstr": "Pr"},
                {"wffstr": "P ∨ Q", "jstr": "∨I,1"},   # R is not P or Q
            ],
            num_prems=1, wanted_conc="P ∨ Q"
        )
        assert_invalid(result)

    def test_addition_wrong_connective(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P ∧ Q", "jstr": "∨I,1"},
            ],
            num_prems=1, wanted_conc="P ∧ Q"
        )
        assert_invalid(result)

    def test_disjunctive_syllogism_left(self, check_proof):
        # P ∨ Q, ¬P ⊢ Q
        result = check_proof(
            [
                {"wffstr": "P ∨ Q", "jstr": "Pr"},
                {"wffstr": "¬P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "DS,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_valid(result)

    def test_disjunctive_syllogism_right(self, check_proof):
        # P ∨ Q, ¬Q ⊢ P
        result = check_proof(
            [
                {"wffstr": "P ∨ Q", "jstr": "Pr"},
                {"wffstr": "¬Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "DS,1,2"},
            ],
            num_prems=2, wanted_conc="P"
        )
        assert_valid(result)

    def test_disjunction_elimination(self, check_proof):
        """
        P ∨ Q, P → R, Q → R ⊢ R

        Proof (line numbers in flattened order):
          1. P ∨ Q   Pr
          2. P → R   Pr
          3. Q → R   Pr
          [ 4. P     Hyp
            5. R     →E,2,4 ]
          [ 6. Q     Hyp
            7. R     →E,3,6 ]
          8. R       ∨E,1,4-5,6-7
        """
        result = check_proof(
            [
                {"wffstr": "P ∨ Q", "jstr": "Pr"},
                {"wffstr": "P → R", "jstr": "Pr"},
                {"wffstr": "Q → R", "jstr": "Pr"},
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "R", "jstr": "→E,2,4"},
                ],
                [
                    {"wffstr": "Q", "jstr": "Hyp"},
                    {"wffstr": "R", "jstr": "→E,3,6"},
                ],
                {"wffstr": "R", "jstr": "∨E,1,4-5,6-7"},
            ],
            num_prems=3, wanted_conc="R"
        )
        assert_valid(result)


# ═══════════════════════════════════════════════════════════════
# ↔I, ↔E, Bicondition — Biconditional
# ═══════════════════════════════════════════════════════════════

class TestBiconditional:

    def test_biconditional_intro(self, check_proof):
        """
        P → Q, Q → P ⊢ P ↔ Q  (using two subproofs)

          1. P → Q   Pr
          2. Q → P   Pr
          [ 3. P     Hyp
            4. Q     →E,1,3 ]
          [ 5. Q     Hyp
            6. P     →E,2,5 ]
          7. P ↔ Q   ↔I,3-4,5-6
        """
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "Q → P", "jstr": "Pr"},
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "Q", "jstr": "→E,1,3"},
                ],
                [
                    {"wffstr": "Q", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "→E,2,5"},
                ],
                {"wffstr": "P ↔ Q", "jstr": "↔I,3-4,5-6"},
            ],
            num_prems=2, wanted_conc="P ↔ Q"
        )
        assert_valid(result)

    def test_biconditional_elim_left_to_right(self, check_proof):
        # P ↔ Q, P ⊢ Q
        result = check_proof(
            [
                {"wffstr": "P ↔ Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "↔E,1,2"},
            ],
            num_prems=2, wanted_conc="Q"
        )
        assert_valid(result)

    def test_biconditional_elim_right_to_left(self, check_proof):
        # P ↔ Q, Q ⊢ P
        result = check_proof(
            [
                {"wffstr": "P ↔ Q", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "↔E,1,2"},
            ],
            num_prems=2, wanted_conc="P"
        )
        assert_valid(result)

    def test_biconditional_elim_wrong_conclusion(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "P ↔ Q", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "↔E,1,2"},   # should be Q
            ],
            num_prems=2, wanted_conc="P"
        )
        assert_invalid(result)

    def test_bicondition_from_two_conditionals(self, check_proof):
        # Bicondition rule: P → Q and Q → P directly yield P ↔ Q (no subproof)
        result = check_proof(
            [
                {"wffstr": "P → Q", "jstr": "Pr"},
                {"wffstr": "Q → P", "jstr": "Pr"},
                {"wffstr": "P ↔ Q", "jstr": "Bicondition,1,2"},
            ],
            num_prems=2, wanted_conc="P ↔ Q"
        )
        assert_valid(result)


# ═══════════════════════════════════════════════════════════════
# DNE, DeM, ⊥I, ⊥E — Negation rules
# ═══════════════════════════════════════════════════════════════

class TestNegation:

    def test_double_negation_elimination(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "¬¬P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "DNE,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_double_negation_introduction(self, check_proof):
        # DNE is bidirectional: P → ¬¬P
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "¬¬P", "jstr": "DNE,1"},
            ],
            num_prems=1, wanted_conc="¬¬P"
        )
        assert_valid(result)

    def test_dne_wrong_formula(self, check_proof):
        result = check_proof(
            [
                {"wffstr": "¬¬P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "DNE,1"},
            ],
            num_prems=1, wanted_conc="Q"
        )
        assert_invalid(result)

    def test_demorgan_not_or_to_and_not(self, check_proof):
        # ¬(P ∨ Q) ⊣⊢ ¬P ∧ ¬Q
        result = check_proof(
            [
                {"wffstr": "¬(P ∨ Q)", "jstr": "Pr"},
                {"wffstr": "¬P ∧ ¬Q", "jstr": "DeM,1"},
            ],
            num_prems=1, wanted_conc="¬P ∧ ¬Q"
        )
        assert_valid(result)

    def test_demorgan_and_not_to_not_or(self, check_proof):
        # Reverse direction
        result = check_proof(
            [
                {"wffstr": "¬P ∧ ¬Q", "jstr": "Pr"},
                {"wffstr": "¬(P ∨ Q)", "jstr": "DeM,1"},
            ],
            num_prems=1, wanted_conc="¬(P ∨ Q)"
        )
        assert_valid(result)

    def test_demorgan_not_and_to_or_not(self, check_proof):
        # ¬(P ∧ Q) ⊣⊢ ¬P ∨ ¬Q
        result = check_proof(
            [
                {"wffstr": "¬(P ∧ Q)", "jstr": "Pr"},
                {"wffstr": "¬P ∨ ¬Q", "jstr": "DeM,1"},
            ],
            num_prems=1, wanted_conc="¬P ∨ ¬Q"
        )
        assert_valid(result)

    def test_contradiction_intro(self, check_proof):
        # P, ¬P ⊢ ⊥
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "¬P", "jstr": "Pr"},
                {"wffstr": "⊥", "jstr": "⊥I,1,2"},
            ],
            num_prems=2, wanted_conc="⊥"
        )
        assert_valid(result)

    def test_contradiction_intro_order_invariant(self, check_proof):
        # ⊥I should work regardless of which cited line is the negation
        result = check_proof(
            [
                {"wffstr": "¬P", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "⊥", "jstr": "⊥I,1,2"},
            ],
            num_prems=2, wanted_conc="⊥"
        )
        assert_valid(result)

    def test_contradiction_intro_no_genuine_contradiction(self, check_proof):
        # P and Q are not a contradiction
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                {"wffstr": "Q", "jstr": "Pr"},
                {"wffstr": "⊥", "jstr": "⊥I,1,2"},
            ],
            num_prems=2, wanted_conc="⊥"
        )
        assert_invalid(result)

    def test_contradiction_elim(self, check_proof):
        # ⊥ ⊢ P  (ex falso)
        result = check_proof(
            [
                {"wffstr": "⊥", "jstr": "Pr"},
                {"wffstr": "P", "jstr": "⊥E,1"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)


# ═══════════════════════════════════════════════════════════════
# RAA, IP, TND — Reductio and tertium non datur
# ═══════════════════════════════════════════════════════════════

class TestReductio:

    def test_raa(self, check_proof):
        """
        RAA (DeLancey style): assume ¬P, derive Q and ¬Q, conclude P.

          1. Q ∧ ¬Q   Pr
          [ 2. ¬P     Hyp
            3. Q      ∧E,1
            4. ¬Q     ∧E,1 ]
          5. P        RAA,2-4
        """
        result = check_proof(
            [
                {"wffstr": "Q ∧ ¬Q", "jstr": "Pr"},
                [
                    {"wffstr": "¬P", "jstr": "Hyp"},
                    {"wffstr": "Q", "jstr": "∧E,1"},
                    {"wffstr": "¬Q", "jstr": "∧E,1"},
                ],
                {"wffstr": "P", "jstr": "RAA,2-4"},
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_valid(result)

    def test_ip_indirect_proof(self, check_proof):
        """
        IP: assume ¬Q, derive ⊥, conclude Q.

          1. P ∧ ¬P   Pr
          [ 2. ¬Q     Hyp
            3. P      ∧E,1
            4. ¬P     ∧E,1
            5. ⊥      ⊥I,3,4 ]
          6. Q        IP,2-5
        """
        result = check_proof(
            [
                {"wffstr": "P ∧ ¬P", "jstr": "Pr"},
                [
                    {"wffstr": "¬Q", "jstr": "Hyp"},
                    {"wffstr": "P", "jstr": "∧E,1"},
                    {"wffstr": "¬P", "jstr": "∧E,1"},
                    {"wffstr": "⊥", "jstr": "⊥I,3,4"},
                ],
                {"wffstr": "Q", "jstr": "IP,2-5"},
            ],
            num_prems=1, wanted_conc="Q"
        )
        assert_valid(result)

    def test_tnd_law_of_excluded_middle(self, check_proof):
        """
        TND: two subproofs (one assuming P, one assuming ¬P) both derive the
        same formula; that formula follows unconditionally.

          [ 1. P      Hyp
            2. P ∨ ¬P ∨I,1 ]
          [ 3. ¬P     Hyp
            4. P ∨ ¬P ∨I,3 ]
          5. P ∨ ¬P   TND,1-2,3-4
        """
        result = check_proof(
            [
                [
                    {"wffstr": "P", "jstr": "Hyp"},
                    {"wffstr": "P ∨ ¬P", "jstr": "∨I,1"},
                ],
                [
                    {"wffstr": "¬P", "jstr": "Hyp"},
                    {"wffstr": "P ∨ ¬P", "jstr": "∨I,3"},
                ],
                {"wffstr": "P ∨ ¬P", "jstr": "TND,1-2,3-4"},
            ],
            num_prems=0, wanted_conc="P ∨ ¬P"
        )
        assert_valid(result)

    def test_hyp_must_be_first_line_of_subproof(self, check_proof):
        """A Hyp that is not the first line of its subproof is invalid."""
        result = check_proof(
            [
                {"wffstr": "P", "jstr": "Pr"},
                [
                    {"wffstr": "P", "jstr": "Rep,1"},
                    {"wffstr": "Q", "jstr": "Hyp"},   # Hyp must be first
                ],
            ],
            num_prems=1, wanted_conc="P"
        )
        assert_invalid(result)


# ═══════════════════════════════════════════════════════════════
# First-order logic rules (predicateSettings=True required)
# ═══════════════════════════════════════════════════════════════

class TestFOL:

    def test_universal_instantiation(self, check_proof):
        # ∀xPx ⊢ Pa
        result = check_proof(
            [
                {"wffstr": "∀xPx", "jstr": "Pr"},
                {"wffstr": "Pa", "jstr": "∀E,1"},
            ],
            num_prems=1, wanted_conc="Pa",
            predicate_settings=True
        )
        assert_valid(result)

    def test_existential_generalization(self, check_proof):
        # Pa ⊢ ∃xPx
        result = check_proof(
            [
                {"wffstr": "Pa", "jstr": "Pr"},
                {"wffstr": "∃xPx", "jstr": "∃I,1"},
            ],
            num_prems=1, wanted_conc="∃xPx",
            predicate_settings=True
        )
        assert_valid(result)

    def test_identity_introduction(self, check_proof):
        # a = a needs no premises; =I cites nothing
        result = check_proof(
            [
                {"wffstr": "a = a", "jstr": "=I"},
            ],
            num_prems=0, wanted_conc="a = a",
            predicate_settings=True
        )
        assert_valid(result)

    def test_substitution_of_identicals(self, check_proof):
        # a = b, Pa ⊢ Pb
        result = check_proof(
            [
                {"wffstr": "a = b", "jstr": "Pr"},
                {"wffstr": "Pa", "jstr": "Pr"},
                {"wffstr": "Pb", "jstr": "=E,1,2"},
            ],
            num_prems=2, wanted_conc="Pb",
            predicate_settings=True
        )
        assert_valid(result)

    def test_conversion_of_quantifiers(self, check_proof):
        # ¬∀xPx ⊢ ∃x¬Px
        result = check_proof(
            [
                {"wffstr": "¬∀xPx", "jstr": "Pr"},
                {"wffstr": "∃x¬Px", "jstr": "CQ,1"},
            ],
            num_prems=1, wanted_conc="∃x¬Px",
            predicate_settings=True
        )
        assert_valid(result)

    def test_fol_rule_rejected_without_predicate_settings(self, check_proof):
        # ∀E should be rejected when predicateSettings is false
        # (the formula itself will fail to parse due to ∀ being a stray char)
        result = check_proof(
            [
                {"wffstr": "∀xPx", "jstr": "Pr"},
                {"wffstr": "Pa", "jstr": "∀E,1"},
            ],
            num_prems=1, wanted_conc="Pa",
            predicate_settings=False
        )
        assert_invalid(result)
