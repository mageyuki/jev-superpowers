# PowerShell installer for jev-superpowers
$ErrorActionPreference = "Stop"

Write-Host "⚡ Installing jev-superpowers..." -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Shared preflight checks credentials without HTTP or printing their values.
# Validate before creating directories or copying any skills.
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (!$python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (!$python) {
    Write-Error "Python 3 is required for System One backend configuration."
    exit 1
}
$backend = & $python.Source (Join-Path $scriptDir "scripts/jev-systemone.py") --check-backend
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "✔ System One backend configured: $backend" -ForegroundColor Green
if ($backend -eq "laya" -and !$env:TYPESAFE_API_KEY) {
    $env:TYPESAFE_API_KEY = "local"
} elseif ($backend -eq "opencode-zen") {
    Write-Host "  Typed decisions: python3 $scriptDir/scripts/jev-systemone.py"
    Write-Host "  Zen does not replace jev-scout registry searches or git jev check."
}

$targetDir = Join-Path $HOME ".agents\skills"
if (!(Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
}

# Copy skills
Get-ChildItem (Join-Path $scriptDir "skills") | ForEach-Object {
    $dest = Join-Path $targetDir $_.Name
    Copy-Item $_.FullName -Destination $dest -Recurse -Force
}

Write-Host "✔ Skills installed to $targetDir" -ForegroundColor Green

# Check tooling
Write-Host "`n🔍 Checking TypeSafe Jev tooling on PATH..." -ForegroundColor Cyan

$missing = 0

function Check-Tool ($tool, $installCmd) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "  ✔ $tool found ($($cmd.Source))" -ForegroundColor Green
    } else {
        Write-Host "  ✘ $tool MISSING! Install via: $installCmd" -ForegroundColor Red
        $script:missing++
    }
}

function Check-GitSubcommand ($name, $installCmd) {
    git $name --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✔ git $name found" -ForegroundColor Green
    } else {
        Write-Host "  ✘ git $name MISSING! Install via: $installCmd" -ForegroundColor Red
        $script:missing++
    }
}

Check-Tool "jev-scout" "cargo install jev-scout"
Check-Tool "jev-axi" "npm install -g jev-axi"
Check-GitSubcommand "jev" "git jev install"
Check-Tool "jev-guard" "npm install -g jev-guard"
Check-Tool "supercov" "npm install -g supercov"
$limpetInstalled = (Test-Path "$HOME\limpet\limpet.py") -or (Get-Command limpet -ErrorAction SilentlyContinue)
if ($limpetInstalled) {
    Write-Host "  ✔ limpet found" -ForegroundColor Green
} else {
    Write-Host "  ✘ limpet MISSING! Install via: git clone https://github.com/noplan-inc/limpet `$HOME\limpet" -ForegroundColor Red
    $missing++
}
Check-Tool "jev-seo" "cargo install jev-seo"

if ($missing -gt 0) {
    Write-Host "`n⚠️  Skills installed successfully, but $missing prerequisite tool(s) were not detected." -ForegroundColor Yellow
    Write-Host "   Install the missing tools above to activate their respective Jev reflex gates." -ForegroundColor Yellow
} else {
    Write-Host "`n✔ All TypeSafe Jev tools and environment variables verified!" -ForegroundColor Green
}

Write-Host "`n🚀 jev-superpowers ready! Use 'jev-using-superpowers' or 'jev-brainstorming' in your agent sessions." -ForegroundColor Cyan
