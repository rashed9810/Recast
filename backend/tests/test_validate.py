from app.core.diff import word_diff
from app.core.validate import check_meaning, check_placeholders
from app.services.paraphrase import _parse_json_list, clean_model_output


def codes(issues):
    return {i.code for i in issues}


def test_placeholder_checks():
    assert check_placeholders("a ⟦P0⟧ b ⟦P1⟧", 2) == []
    assert "placeholder_missing" in codes(check_placeholders("a ⟦P0⟧", 2))
    assert "placeholder_invented" in codes(check_placeholders("⟦P0⟧ ⟦P1⟧ ⟦P2⟧", 2))
    assert "placeholder_duplicated" in codes(check_placeholders("⟦P0⟧ ⟦P0⟧ ⟦P1⟧", 2))
    assert "placeholder_order" in codes(check_placeholders("⟦P1⟧ x ⟦P0⟧", 2, [(0, 1)]))
    assert check_placeholders("⟦ P0 ⟧ and ⟦P1⟧", 2) == []  # tolerant of spacing


def test_numbers_and_terms():
    orig = "Accuracy rose from 81.2% to 90.4% using ResNet-50 on 3 datasets."
    out = "Accuracy increased from 81.2% to 91.4% with ResNet50 on three datasets."
    c = codes(check_meaning(orig, out, "standard", ("ResNet-50",)))
    assert {"numbers_changed", "numbers_added", "term_changed"} <= c


def test_negation_and_hedging():
    orig = "These results may suggest that the effect is not universal."
    out = "These results show that the effect is universal."
    c = codes(check_meaning(orig, out, "standard"))
    assert "negation_changed" in c and "hedging_reduced" in c


def test_clean_rewrite_has_no_warnings():
    orig = "The proposed model reduces training time while keeping accuracy comparable to the baseline."
    out = "The suggested model shortens training time and keeps accuracy comparable to the baseline."
    assert [i for i in check_meaning(orig, out, "standard") if i.level != "info"] == []


def test_clean_model_output():
    assert clean_model_output('Here is the rewritten passage:\n"Text here."') == "Text here."
    assert clean_model_output("```\nText\n```") == "Text"
    assert clean_model_output("<<<\nText\n>>>") == "Text"


def test_parse_json_list():
    assert _parse_json_list('Sure:\n["one two three", "four five six"]') == ["one two three", "four five six"]
    assert _parse_json_list("1. first option here\n2. second option here") == ["first option here", "second option here"]


def test_word_diff_roundtrip():
    a, b = "the quick brown fox", "the fast brown fox jumps"
    ops = word_diff(a, b)
    assert "".join(o["text"] for o in ops if o["op"] != "delete") == b
    assert "".join(o["text"] for o in ops if o["op"] != "insert").split() == a.split()


def test_unchanged_paragraph_is_reported():
    text = "The proposed decoder reduces the number of parameters while keeping accuracy stable."
    assert "unchanged" in codes(check_meaning(text, text, "academic"))
    assert "unchanged" not in codes(check_meaning(text, text, "fluency"))
