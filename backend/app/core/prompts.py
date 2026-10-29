"""Prompt construction. All wording that reaches the model lives here."""

from __future__ import annotations

from dataclasses import dataclass

MODES: dict[str, dict[str, str]] = {
    "academic": {
        "label": "Academic",
        "description": "Formal, precise register for papers and theses.",
        "instruction": (
            "Rewrite in a formal academic register suitable for a peer-reviewed venue. "
            "Prefer precise, discipline-appropriate vocabulary, avoid contractions, "
            "colloquialisms and rhetorical questions, and keep sentences well-structured."
        ),
    },
    "standard": {
        "label": "Standard",
        "description": "Fresh wording with the same meaning and tone.",
        "instruction": (
            "Paraphrase the passage with new wording and sentence structure while keeping "
            "its tone and level of formality."
        ),
    },
    "fluency": {
        "label": "Fluency",
        "description": "Minimal edits: grammar, articles, awkward phrasing.",
        "instruction": (
            "Make the smallest set of edits that fixes grammar, article use, agreement, "
            "word choice and awkward phrasing. Leave sentences that are already correct "
            "and clear unchanged."
        ),
    },
    "concise": {
        "label": "Concise",
        "description": "Cut redundancy and wordiness.",
        "instruction": (
            "Make the passage more concise by removing redundancy, filler phrases and "
            "nominalisations. Aim for roughly 20-30% fewer words, but never drop a claim, "
            "condition, quantity or qualification."
        ),
    },
    "expand": {
        "label": "Elaborate",
        "description": "Smoother, more explicit flow without new facts.",
        "instruction": (
            "Make the passage more explicit and better connected: add transitions, spell out "
            "implicit logical links and define the relationship between ideas. Do not add new "
            "facts, results, examples or citations; only clarify what is already stated."
        ),
    },
    "simplify": {
        "label": "Simplify",
        "description": "Plainer language for broad readers.",
        "instruction": (
            "Rewrite in clear, plain language that a reader outside the field can follow. Use "
            "shorter sentences and common words, but keep technical terms that have no exact "
            "plain equivalent."
        ),
    },
}

STRENGTH = {
    1: "Change wording only where it clearly improves the text; keep most of the original sentence structure.",
    2: "Rephrase most sentences with new wording and moderate restructuring.",
    3: "Substantially restructure sentences and vary the vocabulary, while keeping the meaning identical.",
}

DIALECT = {
    "en-US": "Use American English spelling and conventions (e.g., 'analyze', 'behavior').",
    "en-GB": "Use British English spelling and conventions (e.g., 'analyse', 'behaviour').",
    "keep": "Keep the spelling variety used in the input.",
}

VOICE = {
    "keep": "",
    "active": "Prefer active voice where it reads naturally (e.g., 'we propose' rather than 'it is proposed').",
    "passive": "Prefer an impersonal, passive style where it reads naturally, avoiding first person.",
}

SYSTEM_PROMPT = """You are an expert academic editor who rewrites passages from research papers, theses and technical documents.

Non-negotiable rules:
1. Preserve the scientific meaning exactly. Every claim, quantity, condition, comparison, causal direction and limitation must stay the same.
2. Do not add facts, results, citations, examples or interpretations that are not in the input, and do not remove any.
3. Tokens such as ⟦P0⟧ and ⟦P1⟧ stand for equations, citations, cross-references and LaTeX code. Copy every token exactly once, character for character, with the same brackets, and keep each one next to the words it belongs to. Never invent new tokens, never explain them.
4. Keep all numbers, units, symbols, variable names, acronyms and statistical values exactly as written. Do not convert numerals to words or words to numerals.
5. Keep the degree of certainty. Hedged statements (may, suggests, appears) stay hedged; definite statements stay definite.
6. Write in English. Keep the paragraph as one paragraph; if the input has line breaks between list items, keep them.
7. Output only the rewritten passage: no preamble, no notes, no explanation of changes, no quotation marks, no markdown.

Example
Input: Recent works ⟦P0⟧ uses transformers, which may improves accuracy on ⟦P1⟧ by 3.2%.
Output: Recent studies ⟦P0⟧ employ transformers, which may improve accuracy on ⟦P1⟧ by 3.2%."""


@dataclass
class StyleOptions:
    mode: str = "academic"
    strength: int = 2
    dialect: str = "en-US"
    voice: str = "keep"
    field: str = ""
    frozen_terms: tuple[str, ...] = ()


def _style_lines(o: StyleOptions) -> list[str]:
    lines = [MODES[o.mode]["instruction"], STRENGTH[o.strength], DIALECT[o.dialect]]
    if VOICE[o.voice]:
        lines.append(VOICE[o.voice])
    if o.field.strip():
        lines.append(f"The text is from the field of {o.field.strip()}; use that field's conventional terminology.")
    if o.frozen_terms:
        terms = "; ".join(f'"{t}"' for t in o.frozen_terms)
        lines.append(f"Keep these terms exactly as written, with the same capitalisation: {terms}.")
    return lines


def _token_line(token_count: int) -> str:
    if not token_count:
        return "The passage contains no protected tokens; do not add any."
    tokens = " ".join(f"⟦P{i}⟧" for i in range(token_count))
    return f"The passage contains {token_count} protected token(s), and each must appear exactly once in your output: {tokens}"


def paraphrase_prompt(passage: str, o: StyleOptions, retry_note: str = "", token_count: int = 0) -> str:
    style = "\n".join(f"- {line}" for line in _style_lines(o))
    note = f"\nIMPORTANT: {retry_note}\n" if retry_note else ""
    return (
        f"Task instructions:\n{style}\n- {_token_line(token_count)}\n{note}\n"
        "Rewrite the passage between <<< and >>>. Reply with the rewritten passage only.\n"
        f"<<<\n{passage}\n>>>"
    )


def alternatives_prompt(sentence: str, context: str, o: StyleOptions, count: int, token_count: int = 0) -> str:
    style = "\n".join(f"- {line}" for line in _style_lines(o))
    style += f"\n- {_token_line(token_count)}"
    ctx = f"Surrounding paragraph, for context only (do not rewrite it):\n{context}\n\n" if context else ""
    return (
        f"Task instructions:\n{style}\n\n{ctx}"
        f"Write {count} distinct alternative versions of the sentence between <<< and >>>. "
        "Each alternative must follow every rule above.\n"
        'Return ONLY a JSON array of strings, for example ["first version", "second version"].\n'
        f"<<<\n{sentence}\n>>>"
    )
