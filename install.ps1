<#
.SYNOPSIS
    Automatic Zero-Friction Setup Script for Graphify 2.0 on Windows.
.DESCRIPTION
    1. Detects or bootstraps Python 3.10+ (using system python, py launcher, or winget).
    2. Sets up the isolated virtual environment (.venv).
    3. Installs all required dependencies (KuzuDB, Graphify, FastAPI, NetworkX).
    4. Auto-configures AI assistants (Google Antigravity, Claude Desktop, Cursor, Windsurf).
    5. Pre-indexes starter knowledge graph so the Web Studio is immediately populated.
    6. Emits native launcher scripts (start.bat, start.ps1, start.sh).
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
.EXAMPLE
    .\install.ps1 -Start
.EXAMPLE
    .\install.ps1 -Codebase "C:\path\to\your\repo" -Start
#>

[CmdletBinding()]
param(
    [switch]$Start,
    [int]$Port = 28848,
    [string]$Codebase = "",
    [switch]$SkipGraph,
    [switch]$Docker
)

$ErrorActionPreference = "Stop"

# Color helpers
function Write-Step { param([string]$msg) Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Success { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Determine repository root
$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) {
    $RepoRoot = (Get-Location).Path
}
Set-Location $RepoRoot

Write-Host "==================================================================" -ForegroundColor Magenta
Write-Host "       Graphify 2.0 -- Automatic Windows Setup (Zero-Config)      " -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Magenta
Write-Host "  Repository: $RepoRoot" -ForegroundColor Gray
Write-Host ""

# 1. Detect Python Interpreter
Write-Step "Checking for Python 3.10+ installation..."

$PythonCmd = $null

# Check if local .venv already exists and has working python
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonCmd = $VenvPy
}

# Check 'python' in PATH
if (-not $PythonCmd) {
    try {
        $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver -and [double]$ver -ge 3.10) {
            $PythonCmd = "python"
        }
    } catch {}
}

# Check 'py -3' launcher
if (-not $PythonCmd) {
    try {
        $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver -and [double]$ver -ge 3.10) {
            $PythonCmd = "py -3"
        }
    } catch {}
}

# Check 'python3' in PATH
if (-not $PythonCmd) {
    try {
        $ver = & python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver -and [double]$ver -ge 3.10) {
            $PythonCmd = "python3"
        }
    } catch {}
}

# Search common Windows Python paths
if (-not $PythonCmd) {
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe"
    )
    foreach ($cand in $commonPaths) {
        if (Test-Path $cand) {
            $PythonCmd = $cand
            break
        }
    }
}

# If Python still not found, offer/attempt winget install
if (-not $PythonCmd) {
    Write-Warn "Python 3.10+ was not found on your system."
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue

    if ($hasWinget) {
        Write-Step "Attempting automatic installation of Python 3.11 via winget..."
        try {
            winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
            Start-Sleep -Seconds 5
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $PythonCmd = "python"
        } catch {
            Write-Fail "Automatic installation via winget failed."
        }
    }

    if (-not $PythonCmd) {
        Write-Fail "Please install Python 3.10+ from https://www.python.org/downloads/ and re-run this script."
        exit 1
    }
}

Write-Success "Using Python: $PythonCmd"

# 2. Invoke the Universal Python Installer Engine
Write-Step "Running automated installation engine..."
$installPy = Join-Path $RepoRoot "install.py"

$installArgs = @()
if ($Codebase) {
    $installArgs += "--codebase"
    $installArgs += $Codebase
}
if ($SkipGraph) {
    $installArgs += "--skip-graph"
}
$installArgs += "--port"
$installArgs += $Port.ToString()
if ($Docker) {
    $installArgs += "--docker"
}

if ($PythonCmd -eq "py -3") {
    & py -3 $installPy @installArgs
} else {
    & $PythonCmd $installPy @installArgs
}

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Installation failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

# 3. Handle -Start Switch
if ($Start) {
    Write-Host ""
    Write-Step "Launching Graphify Local Server on port $Port..."
    $serverRunner = Join-Path $RepoRoot "run_server.py"
    $targetPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $targetPy)) { $targetPy = $PythonCmd }

    $env:PORT = $Port.ToString()
    if ($targetPy -eq "py -3") {
        & py -3 $serverRunner
    } else {
        & $targetPy $serverRunner
    }
}
