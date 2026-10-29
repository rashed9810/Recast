from app.core.protect import mask, mask_latex, mask_plain, placeholder_ids, unmask
from app.core.segment import globalise, segment

LATEX = r"""We propose a method~\cite{smith2020,lee2021} that minimises $\mathcal{L}(\theta)$ as in Eq.~\eqref{eq:loss}.
% TODO: tighten this
\begin{equation}
  \mathcal{L} = \sum_{i=1}^{N} \| y_i - f(x_i) \|^2 \label{eq:loss}

\end{equation}
Results improve by 12.5\% on \textbf{CIFAR-10}\footnote{See \url{https://example.org/data} for details.}.

Second paragraph uses {GPU}s and \[ a^2 + b^2 = c^2 \] inline."""


def test_roundtrip_is_exact():
    m = mask_latex(LATEX)
    assert unmask(m.text, m.spans) == LATEX


def test_math_cites_and_comments_hidden():
    m = mask_latex(LATEX)
    for fragment in ["\\cite", "$", "\\begin", "\\end", "% TODO", "\\eqref", "\\textbf", "https://", "{GPU}", "\\%", "a^2", "~"]:
        assert fragment not in m.text, fragment
    assert "We propose a method" in m.text
    assert "Results improve by 12.5" in m.text


def test_equation_with_blank_line_is_one_span():
    m = mask_latex(LATEX)
    eq = [s for s in m.spans if "\\begin{equation}" in s]
    assert len(eq) == 1 and "\\end{equation}" in eq[0]


def test_footnote_text_is_rewritable_and_paired():
    m = mask_latex(LATEX)
    assert "for details." in m.text
    assert len(m.pairs) == 1
    open_id, close_id = m.pairs[0]
    assert m.spans[open_id] == "\\footnote{" and m.spans[close_id] == "}"


def test_unbalanced_input_does_not_crash():
    for bad in ["cost $5 only", r"\textbf{unclosed", "stray } brace", r"\[ never closed", "%"]:
        m = mask_latex(bad)
        assert unmask(m.text, m.spans) == bad


def test_plain_mode_protects_urls_and_numeric_cites():
    text = "As shown in [3, 4], see https://doi.org/10.1000/xyz. Costs $5 and $10."
    m = mask_plain(text)
    assert "[3, 4]" not in m.text and "https://" not in m.text
    assert "$5 and $10" in m.text  # dollars are prose in plain mode
    assert unmask(m.text, m.spans) == text


def test_auto_detects_format():
    assert "⟦P" in mask(r"See \cite{x}.").text
    assert mask("A plain sentence.").spans == []


def test_segments_preserve_document_and_use_local_ids():
    m = mask_latex(LATEX)
    segs, seps = segment(m.text)
    assert len(segs) == 2
    for s in segs:
        ids = placeholder_ids(s.body)
        assert ids and min(ids) == 0
    rebuilt = ""
    for k, s in enumerate(segs):
        rebuilt += s.lead + globalise(s.body, s.local_to_global) + s.trail
        if k < len(seps):
            rebuilt += seps[k]
    assert unmask(rebuilt, m.spans) == LATEX


def test_placeholder_only_paragraph_is_skipped():
    m = mask_latex("\\section{Introduction}\n\nSome real prose goes here today.")
    segs, _ = segment(m.text)
    assert segs[0].rewrite is False and segs[1].rewrite is True
