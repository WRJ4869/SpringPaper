$ErrorActionPreference = "Stop"

$Version = "1.0.0"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = $env:SPRINGPAPER_PYTHON
if (-not $Python) {
    $BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $BundledPython) {
        $Python = $BundledPython
    } else {
        $Python = "python"
    }
}

Set-Location $ProjectRoot

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import PyInstaller" 2>$null
$NeedsPyInstaller = $LASTEXITCODE -ne 0
$ErrorActionPreference = $PreviousErrorActionPreference
if ($NeedsPyInstaller) {
    & $Python -m pip install pyinstaller
}

if (-not (Test-Path -LiteralPath ".\assets\springpaper.ico")) {
    & $Python ".\tools\make_icon.py"
}

Remove-Item -LiteralPath ".\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath ".\dist" -Recurse -Force -ErrorAction SilentlyContinue

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name "SpringPaper" `
    --icon ".\assets\springpaper.ico" `
    --version-file ".\build_version_info.txt" `
    --collect-data "customtkinter" `
    ".\src\springpaper.py"

$PackageDir = ".\releases\SpringPaper-v$Version"
Remove-Item -LiteralPath $PackageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
New-Item -ItemType Directory -Force -Path "$PackageDir\assets", "$PackageDir\docs", "$PackageDir\sample" | Out-Null

Copy-Item -LiteralPath ".\dist\SpringPaper.exe" -Destination "$PackageDir\SpringPaper.exe" -Force
Copy-Item -LiteralPath ".\README.md", ".\LICENSE", ".\CHANGELOG.md", ".\scoring_prompt.md" -Destination $PackageDir -Force
$FirstUseGuideName = -join ([char[]](39318,27425,20351,29992,35828,26126,46,109,100))
Copy-Item -LiteralPath ".\$FirstUseGuideName" -Destination $PackageDir -Force
Copy-Item -Path ".\assets\*" -Destination "$PackageDir\assets" -Recurse -Force
Copy-Item -Path ".\docs\*" -Destination "$PackageDir\docs" -Recurse -Force
Copy-Item -Path ".\sample\*" -Destination "$PackageDir\sample" -Recurse -Force

Compress-Archive -Path "$PackageDir\*" -DestinationPath ".\releases\SpringPaper-v$Version.zip" -Force

Write-Host "Release package created:"
Write-Host (Resolve-Path $PackageDir)
Write-Host (Resolve-Path ".\releases\SpringPaper-v$Version.zip")
