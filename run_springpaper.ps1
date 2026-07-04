$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

$Python = $env:SPRINGPAPER_PYTHON
if (-not $Python) {
    $BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $BundledPython) {
        $Python = $BundledPython
    } else {
        $Python = "python"
    }
}

& $Python -c "import customtkinter, openai, PIL, pyautogui" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing SpringPaper dependencies..."
    & $Python -m pip install -r ".\requirements.txt"
}

& $Python ".\src\springpaper.py"
