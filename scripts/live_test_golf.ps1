# live_test_golf.ps1 — one-shot MBB VSR read live-test for the Golf 7 GTE.
#
# Runs scripts/live_test_mbb_vsr.py from the repo root. The VW account
# password is asked for by the Python script via a hidden prompt — it is
# never passed on the command line, never echoed, never stored.
#
# Usage (from anywhere):
#   .\scripts\live_test_golf.ps1
#   .\scripts\live_test_golf.ps1 -Vin WVWZZZ... -Email you@example.com
#   .\scripts\live_test_golf.ps1 -Mfa 123456 -Country CH
param(
    [string]$Vin,
    [string]$Email,
    [string]$Mfa,
    [string]$Country = "DE"
)

$repo = Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    $pyArgs = @("scripts/live_test_mbb_vsr.py")
    if ($Vin)     { $pyArgs += @("--vin", $Vin) }
    if ($Email)   { $pyArgs += @("--email", $Email) }
    if ($Mfa)     { $pyArgs += @("--mfa", $Mfa) }
    if ($Country) { $pyArgs += @("--country", $Country) }
    py @pyArgs
} finally {
    Pop-Location
}
