#!/usr/bin/env bash
set -euo pipefail

# Scaffolds the Retry Budget Allocator repo.
#
# Usage:
#   bash setup.sh              # backend scaffold (run this first)
#   bash setup.sh --dashboard  # React dashboard (run at build order step 9)
#
# The --dashboard step is INTERACTIVE (shadcn asks configuration questions).
# Run it in a terminal you can answer, not in CI or a background process.

if [[ "${1:-}" == "--dashboard" ]]; then
  echo "==> Scaffolding dashboard (build order step 9)"
  echo "    This step is interactive - shadcn will ask you questions."
  if [[ -d dashboard ]]; then
    echo "dashboard/ already exists - aborting so nothing is overwritten."
    exit 1
  fi
  npm create vite@latest dashboard -- --template react-ts
  cd dashboard
  npm install
  # Tailwind pinned to v3: v4 removed `tailwindcss init` and uses CSS-first
  # config, which shadcn's standard init flow does not expect.
  npm install -D tailwindcss@^3 postcss autoprefixer
  npx tailwindcss init -p
  npm install framer-motion lucide-react recharts
  npx shadcn@latest init
  echo ""
  echo "==> Dashboard ready."
  echo "    recharts       - sensitivity sweep chart (PRD Sec 5.2 / 6.1)"
  echo "    framer-motion  - stage transitions in the pipeline trace view"
  echo "    Run: cd dashboard && npm run dev"
  exit 0
fi

echo "==> Creating directory structure"
mkdir -p pipeline eval/results data docs tests .github/workflows

echo "==> Creating package markers"
touch pipeline/__init__.py eval/__init__.py

echo "==> Writing .gitignore"
cat > .gitignore <<'EOF'
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
node_modules/
dist/
.DS_Store
data/runs/
EOF

echo "==> Writing .env.example"
cat > .env.example <<'EOF'
# Copy to .env and fill in. .env is git-ignored - never commit real keys.

# Razorpay TEST MODE credentials.
# Free: sign up at dashboard.razorpay.com, stay in Test Mode,
# Settings > API Keys > Generate Test Key. No KYC needed for test mode.
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# LLM used ONLY for plain-language explanations (PRD Sec 4, Stage 7).
# Never used for retry/stop decisions.
#
# OpenRouter free tier - models with the :free suffix cost nothing and need no
# credit balance (they are rate-limited, which is fine: the LLM is off the
# critical path). Get a key at openrouter.ai/keys
EXPLANATION_MODEL=moonshotai/kimi-k2.6:free
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-xxxxxxxx
#
# Fallback if the above rate-limits mid-build - swap this one line, no code change:
# EXPLANATION_MODEL=z-ai/glm-4.7-flash:free
#LLM_BASE_URL=https://openrouter.ai/api/v1
#LLM_API_KEY=sk-or-v1-xxxxxxxx
# NOTE: NVIDIA build.nvidia.com gives free trial CREDITS, not unlimited free
# usage. Only use it if you accept the balance running out mid-build.

# Funding-window inference confidence floor (PRD Sec 4, Stage 4).
# Below this, fall back to documented safe spacing (24h / 72h / 7d).
FUNDING_CONFIDENCE_THRESHOLD=0.6
EOF

echo "==> Writing requirements.txt"
cat > requirements.txt <<'EOF'
pydantic>=2.0
python-dotenv>=1.0
httpx>=0.27
openai>=1.40
razorpay>=1.4
pytest>=8.0
pytest-cov>=5.0
ruff>=0.6
EOF

echo "==> Writing starter test"
# Without at least one test, pytest exits code 5 (no tests collected) and the
# first CI run fails before any code is written.
cat > tests/test_scaffold.py <<'EOF'
"""Placeholder so CI passes on the scaffold commit.

Replace with the compliance invariant tests (PRD Sec 7, build order step 2):
  - never more than 3 retry attempts per mandate
  - never schedule inside a peak window (10:00-13:00, 17:00-21:30)
  - never more than one successful debit per token per billing cycle
"""


def test_scaffold_imports():
    import pipeline  # noqa: F401
EOF

echo "==> Writing CI workflow"
cat > .github/workflows/ci.yml <<'EOF'
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: pytest --cov=pipeline --cov-report=term
EOF

echo "==> Writing build log stub"
cat > docs/build-log.md <<'EOF'
# Build log

Running record of what broke and how it was fixed. Feeds the pitch video's
Failure Recovery narrative, which is graded as its own axis. Add entries as
they happen - do not reconstruct at the end.

| Date | What broke | How it was caught | Fix |
|---|---|---|---|
EOF

echo "==> Writing results stub"
cat > docs/RESULTS.md <<'EOF'
# Results

Fill this in once the eval harness runs (PRD Sec 6.4). Structure:

1. Headline - money recovered vs baseline, attempts saved, compliance
   violations (zero)
2. The outcome model, stated BEFORE any number (PRD Sec 5.1)
3. Per-cause breakdown - where the allocator helps and where it does not
4. Sensitivity sweep (PRD Sec 5.2) - how the advantage holds across settings
5. Stop-decision precision
6. What did not work - failure modes found
7. Limitations - simulation study, modelled failure mix, probabilistic funding
   inference, small N

Write so a non-specialist follows the headline and a technical reader can audit
the method.
EOF

echo "==> Writing README"
# The README is the first thing a judge opens on a public repo. Problem Taste is
# graded from what is visible here, not from docs/prd.md.
cat > README.md <<'EOF'
# Retry Budget Allocator

**Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery**

## The problem

When a UPI AutoPay recurring payment fails, Razorpay's controlled flow returns
retry responsibility to the merchant — its own S2S documentation states that no
automatic retry is attempted and the merchant should retry manually.

The merchant must then decide how to spend a hard budget of **three
NPCI-permitted retry attempts**, restricted to non-peak windows, with only one
successful debit allowed per billing cycle.

That budget is usually spent on a fixed schedule that ignores *why* the payment
failed. An expired or revoked mandate consumes attempts it can never convert. An
insufficient-balance failure — the dominant cause, behind roughly 20 million
AutoPay revocations a month — consumes all three attempts within days, before the
customer's account is funded again.

This is a **constrained allocation problem, not a scheduling one**: a small,
regulated, non-renewable budget of interventions, spent without knowing which
failures are recoverable.

## What this builds

A decision layer that classifies the failure cause, chooses between notifying,
retrying at a specific compliant time, or stopping early, and records why each
decision was made.

- **Deterministic where it should be** — cause classification is a lookup over
  the real Razorpay error object, not a model call
- **AI where it earns its place** — an LLM writes the plain-language reasoning
  and customer notification copy, and never decides whether to retry
- **Compliance proven, not claimed** — invariants (max 3 attempts, no peak-window
  scheduling, one debit per cycle) are asserted in tests and re-run live

## Results

**[docs/RESULTS.md](docs/RESULTS.md)** — headline numbers, method, sensitivity
analysis, and what did not work. Results are a simulation study against a
published outcome model, not a field measurement; the model is stated before any
number.

## Docs

- [docs/RESULTS.md](docs/RESULTS.md) — results, method, and limitations
- [docs/architecture.md](docs/architecture.md) — pipeline design and data flow
- [docs/prd.md](docs/prd.md) — full specification and verified sources
- [docs/build-log.md](docs/build-log.md) — what broke during the build and how it was fixed

## Setup

    bash setup.sh
    cp .env.example .env    # fill in keys
    source .venv/bin/activate
    pytest

## Dashboard (build order step 11)

    bash setup.sh --dashboard
    cd dashboard && npm run dev
EOF

echo "==> Setting up virtualenv"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Verifying install"
python -c "import pydantic, dotenv, httpx, openai, razorpay; print('deps ok')"

echo "==> Running scaffold checks"
ruff check . && pytest -q

if command -v npm >/dev/null 2>&1; then
  echo "==> Installing Ponytail (referenced by CLAUDE.md)"
  npm install -g ponytail --silent || \
    echo "    Ponytail install failed - install manually or via the Claude Code"
    echo "    plugin marketplace: /plugin marketplace add DietrichGebert/ponytail"
else
  echo "==> npm not found - install Ponytail manually (see CLAUDE.md)"
fi

if [[ ! -d .git ]]; then
  echo "==> Initialising git"
  git init -b main
  git add -A
  git commit -m "Initial scaffold (PRD Sec 7)" --quiet
  echo "    Local repo initialised, first commit made."
else
  echo "==> git already initialised, skipping init"
fi

cat <<'EOF'

==> Done. Scaffold checks passed, so CI will be green on first push.

Git and GitHub
--------------
  With the gh CLI (easiest):
    gh repo create retry-budget-allocator --public --source=. --push

  Without gh - create an EMPTY repo on github.com (no README, no .gitignore,
  or the first push will conflict), then:
    git remote add origin https://github.com/Asha0509/retry-budget-allocator.git
    git push -u origin main

  If you cloned an empty repo first and ran setup.sh inside it, git init was
  skipped - just commit and push:
    git add -A && git commit -m "Initial scaffold (PRD Sec 7)" && git push

Next steps
----------
  1. cp .env.example .env   and fill in your keys
  2. Copy the PRD to docs/prd.md and CLAUDE.md to the repo root, then commit
  3. source .venv/bin/activate
  4. Start with pipeline/classify.py (PRD Sec 7, build order step 1)

Reminder: build order step 2 replaces tests/test_scaffold.py with the real
compliance invariant tests. Write those before the allocator.

Dashboard is step 9 - do not run --dashboard until the eval harness produces
real numbers.
EOF
