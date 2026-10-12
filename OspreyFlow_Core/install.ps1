# The OspreyFlow bootstrap for Windows (06_DECISIONS.md ADR-114 decision 2; Amendment 3 decision 3).
# It brings uv, gets the checkout, installs the `ospreyflow` command as a uv tool and records where
# the checkout is. It installs nothing else and starts nothing: the next two commands it prints do
# that.
#
#   .\install.ps1                              # from inside a checkout
#   $env:OSPREYFLOW_REPO = "<address>"; .\install.ps1   # clone it into $HOME\ospreyflow first
$ErrorActionPreference = "Stop"

function Stop-Install([string]$Message) {
    Write-Error "install.ps1: $Message"
    exit 1
}

function Test-Product([string]$Folder) {
    (Test-Path (Join-Path $Folder "harness\__init__.py")) -and (Test-Path (Join-Path $Folder "osprey.yaml"))
}

# 1. uv.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is not installed; installing it with the official installer (https://astral.sh/uv)."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$HOME\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Stop-Install "uv was installed but is not on the PATH. Open a new terminal and run this again."
    }
}

# 2. The checkout: the one this script sits in, the one it is run from, or a fresh clone.
$here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$product = $null
foreach ($candidate in @($here, (Join-Path $here "OspreyFlow_Core"), (Get-Location).Path)) {
    if (Test-Product $candidate) { $product = $candidate; break }
}
if (-not $product) {
    if (-not $env:OSPREYFLOW_REPO) {
        Stop-Install "This is not run from inside an OspreyFlow checkout. Set OSPREYFLOW_REPO to the address of the OspreyFlow repository and run this again; it will be cloned into $HOME\ospreyflow."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Stop-Install "Git is needed to get the checkout. Install Git (https://git-scm.com/downloads), then run this again."
    }
    $product = Join-Path $HOME "ospreyflow"
    if (Test-Product $product) {
        Write-Host "Using the checkout already in $product."
    } else {
        git clone $env:OSPREYFLOW_REPO $product
        if (-not (Test-Product $product)) {
            Stop-Install "$product is not an OspreyFlow checkout (it has no harness and osprey.yaml)."
        }
    }
}

# 3. The checkout's own environment, then the command.
uv sync --project $product
uv tool install --editable (Join-Path $product "cli")

# 4. Remember where the checkout is, so the command finds it from any folder.
$homeFile = Join-Path $env:APPDATA "ospreyflow\home"
New-Item -ItemType Directory -Force -Path (Split-Path $homeFile) | Out-Null
Set-Content -Path $homeFile -Value $product -Encoding utf8

Write-Host ""
Write-Host "OspreyFlow's command is installed. The checkout is $product."
Write-Host "Next:"
Write-Host "  ospreyflow doctor"
Write-Host "  ospreyflow install --mode lite"
Write-Host "(If the command is not found, open a new terminal, or run: uv tool update-shell)"
