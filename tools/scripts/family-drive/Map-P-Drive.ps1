# Map-P-Drive.ps1 - connect P: to the Family share on oscar (run on each Utah PC).
# Needs the Cloudflare One client installed and signed in first; see
# docs/workflows/family-drive.md. Run in a normal (not admin) PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\Map-P-Drive.ps1
param(
    [string]$Server = '10.77.77.1',
    [string]$Share = 'Family',
    [string]$Letter = 'P',
    [string]$User = 'family',
    [string]$Label = 'Family'
)
$ErrorActionPreference = 'Stop'
$unc = "\\$Server\$Share"

$warp = 'C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe'
if (Test-Path $warp) {
    Write-Host "Cloudflare One: $((& $warp status) -join ' ')"
} else {
    Write-Host 'Cloudflare One client is not installed. Install it first (see the guide).' -ForegroundColor Red
    exit 1
}

Write-Host "Checking that oscar answers at $Server ..."
if (-not (Test-NetConnection $Server -Port 445 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    Write-Host 'oscar did not answer. Make sure Cloudflare One shows Connected, and sign in again if it asks.' -ForegroundColor Red
    exit 1
}

$secure = Read-Host "Password for '$User' (from Mike)" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
cmdkey /add:$Server /user:$User /pass:$plain | Out-Null
$plain = $null

if (Test-Path "${Letter}:\") { net use "${Letter}:" /delete /y | Out-Null }
net use "${Letter}:" $unc /persistent:yes
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Could not connect the drive. Check the password, then run this again.' -ForegroundColor Red
    exit 1
}
(New-Object -ComObject Shell.Application).NameSpace("${Letter}:\").Self.Name = $Label
Write-Host "Done: $Label (${Letter}:) is in File Explorer under This PC." -ForegroundColor Green
