# Recast: academic rewriting that keeps your science intact

Recast rewrites research prose (papers, theses, technical docs, raw LaTeX) in the style you choose. It guarantees that equations, citations, cross-references and LaTeX commands come back **exactly** as you wrote them. It then checks every paragraph for signs that the meaning changed.

It runs on your own machine. With a local model (Ollama) there are **no usage limits and your text never leaves your computer.**

---

## 1. How it works, in plain words

Think of it as five steps, like an editor with a very careful assistant:

```
your text
   │
   ▼
① LOCK      every equation, \cite{}, \ref{}, % comment, URL … is cut out
   │        and replaced by a token like ⟦P3⟧
   ▼
② SPLIT     the text is split into paragraphs (an equation that spans
   │        blank lines is already one token, so it can't be cut in half)
   ▼
③ REWRITE   each paragraph goes to the AI model with strict rules:
   │        same meaning, same numbers, same hedging, keep every token
   ▼
④ VERIFY    did every token come back exactly once? If not → retry once
   │        with a stricter instruction → still broken? keep the ORIGINAL
   │        paragraph (never a corrupted one). Then meaning checks run.
   ▼
⑤ UNLOCK    tokens are swapped back for your original LaTeX, byte for byte
```

**Why lock instead of asking the model nicely?** Models sometimes "improve" `$\lambda_1 = 0.7$` into `$\lambda = 0.7$` or drop a `\cite`. If the model never sees the LaTeX, it cannot damage it.

### What the meaning checks look for

| Check | Example it catches |
|---|---|
| Numbers changed | `90.4%` became `91.4%`, or `3` became `three` |
| Locked terms changed | `ResNet-50` became `ResNet50` |
| Negation changed | "is **not** universal" became "is universal" |
| Hedging removed | "results **may suggest**" became "results show" |
| Certainty added | the rewrite introduces "proves", "always", "clearly" |
| Length out of range | half the paragraph vanished, or new content appeared |

These are warning lights, not proof. A clean report means nothing obvious went wrong. You should still read the result.

---

## 2. Quick start (no Docker)

You need **Python 3.11+** and **Node.js 20+**.

**Terminal 1: backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: frontend**
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**, click **Try a sample**, then **Rewrite**.

It starts in **demo mode**: a stand-in that only swaps a few fixed words, so the output reads oddly on purpose. **Demo mode does not paraphrase.** Connect a real model next.

---

## 3. Connect an AI model (in the app, no config files)

Click the badge at the top right ("Demo mode: set up a model"), or the **Set up a model** button.

1. Choose a **Service**.
2. Paste an **API key** if the service needs one (there's a "Get a key" link).
3. Click **Load models**, then pick one.
4. Click **Test**. It rewrites a test sentence that contains a citation, so you see a real result.
5. Click **Save and use**. The setting is remembered, even after a restart.

| Service | Cost | Privacy | Notes |
|---|---|---|---|
| **Ollama** (on your computer) | Free, no limits | Text never leaves your machine | Install from ollama.com, then `ollama pull qwen2.5:7b-instruct`. 14B+ models write better if your computer can run them. |
| **LM Studio** (on your computer) | Free, no limits | Private | Start its server in the Developer tab. |
| **Groq** | Free tier (per-minute limits) | Cloud | Very fast. |
| **Google Gemini** | Free tier | Cloud; free tier may use your text to improve models | Good writing quality. |
| **OpenRouter** | Some free models | Cloud | Many models with one key. |
| **OpenAI / Anthropic** | Paid per use | Cloud | Highest quality. |

Model names change often, so Recast doesn't hard-code them: **Load models** always shows the service's current list.

**Which model?** Bigger models keep the protected LaTeX tokens and the exact meaning much more reliably. If many paragraphs show "Original kept" in the Checks tab, use a larger model.

You can still configure through `backend/.env` instead (see `.env.example`); anything saved in the app takes priority. Settings live in `backend/data/model.json`, which holds your API key, so never commit or share it.

---

## 4. Troubleshooting

| What you see | Cause and fix |
|---|---|
| Output has odd grammar ("approaches employs") | You're in **demo mode**. Set up a model (section 3). |
| "Backend offline" badge | The Python backend isn't running. Start it (section 2, terminal 1). The app reconnects by itself. |
| "Could not reach the model server" | Ollama/LM Studio isn't running, or the address is wrong. Run `ollama serve` or open the Ollama app. |
| "Rate limit reached" | Free cloud tiers limit requests per minute. Recast retries automatically; for long documents, set **Advanced → Parallel requests** to 1. |
| Many paragraphs say "Original kept" | The model kept breaking the protected LaTeX, so Recast refused to use its output. Use a larger model. |
| "Returned this paragraph almost unchanged" | The model is too timid. Move **Change** to Strong, or use a larger model. |
| A long document takes minutes | Normal for a model on your computer (roughly 10–60 s per paragraph without a GPU). The progress bar shows which paragraph it's on. Set **Parallel requests** to 1 for local models. |
| "Took too long to answer" | Raise **Advanced → Time limit per paragraph**. |

---

## 5. Using the app

- **Modes:**
  - **Academic:** formal register.
  - **Standard:** fresh wording, same tone.
  - **Fluency:** minimal grammar fixes, which is safest for final drafts.
  - **Concise:** cuts 20–30% of the wording.
  - **Elaborate:** adds clearer links between ideas, with no new facts.
  - **Simplify:** plain language.
- **Change** slider: Light, Balanced or Strong, for how much the wording moves.
- **More options:** American or British spelling; active or impersonal voice; input type (auto, LaTeX or plain); your **field** (e.g. "medical imaging"), so terminology fits; **Locked terms**, which are kept exactly (method names, dataset names, defined terms).
- **Rewrite tab:** ochre highlighted text is locked content, copied from your original. **Select a sentence** to get alternatives and click one to apply it. **Edit** lets you fix things by hand.
- **Changes tab:** a word-level diff (green = added, red = removed).
- **Checks tab:** a per-paragraph report. **Use original paragraph** undoes one paragraph.
- **Open file** loads a `.tex`, `.txt` or `.md` file. **Download** saves the result in the same format.
- **Recent** keeps your last 15 runs in this browser only.
- Shortcut: **Ctrl/Cmd + Enter** runs Rewrite.

**A good workflow for a paper:** paste one section at a time. Use **Fluency** for nearly-final text and **Academic** at **Balanced** for drafts. Then read every paragraph flagged in **Checks** next to its original.

---

## 6. Project structure

```
recast/
├── backend/                     FastAPI service (Python)
│   ├── app/
│   │   ├── main.py              HTTP endpoints
│   │   ├── config.py            settings from .env
│   │   ├── model_config.py      model settings saved from the app (data/model.json)
│   │   ├── schemas.py           request/response shapes (validated)
│   │   ├── core/
│   │   │   ├── protect.py       ① LaTeX/math/citation locking (brace-aware parser)
│   │   │   ├── segment.py       ② paragraph splitting, per-paragraph token ids
│   │   │   ├── prompts.py       ③ all prompt wording + mode definitions
│   │   │   ├── validate.py      ④ token checks + meaning heuristics + readability
│   │   │   └── diff.py          word-level diff
│   │   ├── services/
│   │   │   └── paraphrase.py    the pipeline: output cleaning, retry, fallback, streaming
│   │   └── providers/           model adapters: openai_compat, anthropic, demo
│   └── tests/                   42 tests (pytest), incl. real-world failure cases
├── frontend/                    Next.js 16 + TypeScript
│   ├── app/                     page, layout, styles, /api proxy route (no time limit)
│   ├── components/              Controls, TermsInput, OutputPanel, ModelSetup
│   └── lib/                     API client, types, local history, LaTeX highlighter
└── docker-compose.yml
```

### API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Connected provider and model, input limit |
| GET | `/api/modes` | Available modes |
| POST | `/api/paraphrase` | `{text, mode, strength, dialect, voice, field, frozen_terms, format}` returns the rewrite, per-paragraph report, diff and metrics |
| POST | `/api/paraphrase/stream` | Same input; streams progress events (one JSON object per line), then the result |
| GET/PUT | `/api/settings/model` | Read or change the active model (the API key is never returned) |
| POST | `/api/settings/model/models` | List the models a service offers |
| POST | `/api/settings/model/test` | Run one real test rewrite |
| POST | `/api/alternatives` | `{sentence, context, count, …style}` returns alternative sentences that passed the token check |

Interactive API docs: http://localhost:8000/docs

---

## 7. Extending it

- **Add a mode:** add an entry to `MODES` in `backend/app/core/prompts.py` and to the `Mode` type in `schemas.py` and `frontend/lib/types.ts`.
- **Add a provider:** subclass `LLMProvider` (one `complete()` method) and register it in `providers/__init__.py`.
- **Protect more LaTeX:** add environment names to `BLOCK_ENVS`, or commands whose argument is prose to `TEXT_ARG_COMMANDS` in `protect.py`. Then add a round-trip test in `tests/test_protect.py`.

## 8. Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
cd frontend && npm run typecheck && npm run build
```

The tests cover:
- exact LaTeX round-trips, including unbalanced input;
- token-loss detection, and the fallback to the original paragraph;
- each meaning check;
- the request format of both provider adapters, using mocked HTTP;
- the API end to end with the demo provider;
- real-world model failures: "thinking" text, preambles, trailing notes, `[[P0]]`-style tokens, rate limits, one paragraph failing, the server being down, and progress streaming;
- that a saved API key is never returned to the browser or sent to a different service.

## 9. Docker (optional)

```bash
cp backend/.env.example backend/.env
docker compose up --build                        # app on http://localhost:3000
docker compose --profile local-model up --build  # also starts Ollama
```

In Docker, the model server address is different: use `http://ollama:11434/v1` for the Ollama container, or `http://host.docker.internal:11434/v1` for Ollama installed on your computer.

## 10. Honest limitations

- The meaning checks are heuristics. They catch common slips (numbers, negation, hedging) but cannot fully understand science. **You stay the author:** read before you submit.
- Rewrite quality depends on the model. Small local models are more likely to drop tokens; Recast then keeps your original paragraph and tells you.
- Prose inside `\textbf{}`, `\emph{}` and section titles is locked as-is. Footnotes and captions are rewritten.
- Recast is built to run on your own computer. Don't put the backend on the public internet: anyone who can reach it could use your API key.
- Check your venue's and institution's policy on AI-assisted writing, and disclose its use where required.
