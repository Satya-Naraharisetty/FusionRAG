#!/usr/bin/env bash
set -e

echo "=================================================="
echo "🚀 Running Fast Repository Verification Checks..."
echo "=================================================="

echo -e "\n[1/8] 🐍 Running Ruff Formatter (backend)..."
(cd backend && uv run ruff format .)

echo -e "\n[2/8] 🐍 Running Ruff Linter with Auto-Fix (backend)..."
(cd backend && uv run ruff check --fix .)

echo -e "\n[3/8] 🐍 Running Mypy Type Check (backend)..."
(cd backend && uv run mypy app)

echo -e "\n[4/8] 🎨 Running Frontend Prettier Formatter..."
(cd frontend && npm run format)

echo -e "\n[5/8] ⚛️ Running Frontend ESLint..."
(cd frontend && npm run lint)

echo -e "\n[6/8] ⚛️ Running Frontend TypeScript Typecheck..."
(cd frontend && npm run typecheck)

echo -e "\n[7/8] ⚛️ Running Frontend Production Build..."
(cd frontend && npm run build)

echo -e "\n[8/8] 🔐 Running Secret Leak Detection (Gitleaks)..."
if command -v gitleaks &> /dev/null; then
    gitleaks detect --redact --verbose
else
    echo "ℹ️ Gitleaks is not installed locally; secret scanning will run in GitHub Actions CI."
fi

echo -e "\n=================================================="
echo "✅ All fast verification checks passed successfully!"
echo "ℹ️ Test suites (pytest & vitest) will run in GitHub Actions CI."
echo "=================================================="
