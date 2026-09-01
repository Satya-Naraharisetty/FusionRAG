# PowerShell script to run all CI & pre-push checks locally

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Running Complete Repository Verification Checks..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "`n[1/10] Running Ruff Formatter (backend)..." -ForegroundColor Yellow
Push-Location backend
try {
    uv run ruff format .
} finally {
    Pop-Location
}

Write-Host "`n[2/10] Running Ruff Linter with Auto-Fix (backend)..." -ForegroundColor Yellow
Push-Location backend
try {
    uv run ruff check --fix .
} finally {
    Pop-Location
}

Write-Host "`n[3/10] Running Mypy Type Check (backend)..." -ForegroundColor Yellow
Push-Location backend
try {
    uv run mypy app
} finally {
    Pop-Location
}

Write-Host "`n[4/10] Running Backend Unit Tests..." -ForegroundColor Yellow
Push-Location backend
try {
    uv run pytest
} finally {
    Pop-Location
}

Write-Host "`n[5/10] Running Frontend Prettier Formatter..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run format
} finally {
    Pop-Location
}

Write-Host "`n[6/10] Running Frontend ESLint..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run lint
} finally {
    Pop-Location
}

Write-Host "`n[7/10] Running Frontend TypeScript Typecheck..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run typecheck
} finally {
    Pop-Location
}

Write-Host "`n[8/10] Running Frontend Vitest Suite..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run test
} finally {
    Pop-Location
}

Write-Host "`n[9/10] Running Frontend Production Build..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run build
} finally {
    Pop-Location
}

Write-Host "`n[10/10] Running Secret Leak Detection (Gitleaks)..." -ForegroundColor Yellow
$gitleaksCmd = Get-Command "gitleaks" -ErrorAction SilentlyContinue
if ($null -ne $gitleaksCmd) {
    gitleaks detect --redact --verbose
} else {
    Write-Host "Gitleaks is not installed locally; secret scanning will run in GitHub Actions CI." -ForegroundColor DarkGray
}

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "All verification checks passed successfully!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
