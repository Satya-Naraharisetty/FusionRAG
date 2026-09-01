#!/usr/bin/env bash
set -e

echo "=================================================="
echo "🚀 Running Complete Repository Verification Checks..."
echo "=================================================="

echo -e "\n[1/10] 🐍 Running Ruff Formatter (backend)..."
(cd backend && uv run ruff format .)

echo -e "\n[2/10] 🐍 Running Ruff Linter with Auto-Fix (backend)..."
(cd backend && uv run ruff check --fix .)

echo -e "\n[3/10] 🐍 Running Mypy Type Check (backend)..."
(cd backend && uv run mypy app)

echo -e "\n[4/10] 🐍 Running Backend Unit Tests..."
(cd backend && uv run pytest)

echo -e "\n[5/10] 🎨 Running Frontend Prettier Formatter..."
(cd frontend && npm run format)

echo -e "\n[6/10] ⚛️ Running Frontend ESLint..."
(cd frontend && npm run lint)

echo -e "\n[7/10] ⚛️ Running Frontend TypeScript Typecheck..."
(cd frontend && npm run typecheck)

echo -e "\n[8/10] ⚛️ Running Frontend Vitest Suite..."
(cd frontend && npm run test)

echo -e "\n[9/10] ⚛️ Running Frontend Production Build..."
(cd frontend && npm run build)

echo -e "\n[10/10] 🔐 Running Secret Leak Detection (Gitleaks)..."
if command -v gitleaks &> /dev/null; then
    gitleaks detect --redact --verbose
else
    echo "ℹ️ Gitleaks is not installed locally; secret scanning will run in GitHub Actions CI."
fi

echo -e "\n=================================================="
echo "✅ All verification checks passed successfully!"
echo "=================================================="
