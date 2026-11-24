param(
    [switch]$NoInstall,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$PyInstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    $PyInstaller = "pyinstaller"
}

Write-Host "==> Fetching FaceLandmarker model..."
& $Python (Join-Path $Root "scripts\fetch_models.py")
if ($LASTEXITCODE -ne 0) { throw "fetch_models.py failed" }

$WorkPath = Join-Path $env:TEMP "openplay-pyi-work"
$DistPath = Join-Path $env:TEMP "openplay-pyi-dist"
$BuiltDir = Join-Path $DistPath "OpenPlay Access"
$BuiltExe = Join-Path $BuiltDir "OpenPlay Access.exe"

Write-Host "==> Building OpenPlay Access.exe in $DistPath..."
& $PyInstaller --noconfirm --workpath $WorkPath --distpath $DistPath (Join-Path $Root "scripts\openplay.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

if (-not (Test-Path $BuiltExe)) {
    throw "Built executable not found at $BuiltExe"
}

$SmokeOut = Join-Path $env:TEMP "openplay_smoke.json"
if (Test-Path $SmokeOut) { Remove-Item $SmokeOut -Force }

Write-Host "==> Running headless smoke test on built executable..."
$proc = Start-Process -FilePath $BuiltExe -ArgumentList "--smoke-test", "--smoke-out", $SmokeOut -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    if (Test-Path $SmokeOut) { Get-Content $SmokeOut }
    throw "Smoke test exited with code $($proc.ExitCode)"
}
$smoke = Get-Content $SmokeOut -Raw | ConvertFrom-Json
if (-not $smoke.ok) {
    Get-Content $SmokeOut
    throw "Smoke test reported ok=false"
}
Write-Host "==> Smoke test PASSED."

if ($Zip) {
    $VerLine = Select-String -Path (Join-Path $Root "openplay\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"'
    $Version = if ($VerLine) { $VerLine.Matches[0].Groups[1].Value } else { "0.2.0" }
    $ReleaseDir = Join-Path $Root "release"
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    $ZipPath = Join-Path $ReleaseDir "OpenPlayAccess-v$Version-win64.zip"
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    Compress-Archive -Path $BuiltDir -DestinationPath $ZipPath
    Write-Host "==> Created release archive: $ZipPath"
}

if (-not $NoInstall) {
    Get-Process | Where-Object { $_.ProcessName -like "OpenPlay*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300

    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\OpenPlay Access"
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
    Copy-Item -Recurse -Force $BuiltDir $InstallDir

    $InstalledExe = Join-Path $InstallDir "OpenPlay Access.exe"
    $WshShell = New-Object -ComObject WScript.Shell

    $DesktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "OpenPlay Access.lnk"
    $sc1 = $WshShell.CreateShortcut($DesktopLnk)
    $sc1.TargetPath = $InstalledExe
    $sc1.WorkingDirectory = $InstallDir
    $sc1.IconLocation = "$InstalledExe,0"
    $sc1.Save()

    $StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "OpenPlay Access"
    New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
    $StartMenuLnk = Join-Path $StartMenuDir "OpenPlay Access.lnk"
    $sc2 = $WshShell.CreateShortcut($StartMenuLnk)
    $sc2.TargetPath = $InstalledExe
    $sc2.WorkingDirectory = $InstallDir
    $sc2.IconLocation = "$InstalledExe,0"
    $sc2.Save()

    Write-Host "==> Installed to: $InstallDir"
    Write-Host "==> Shortcuts created on Desktop and Start Menu."
}
