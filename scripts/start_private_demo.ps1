#requires -Version 7.2
# A temporary HTTPS demo hosted on this PC. No account or payment method is created.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string[]] $AllowedMail,
    [Parameter(Mandatory = $true)] [string] $EnvFile,
    [string] $Database = (Join-Path $env:LOCALAPPDATA 'whoami\private-demo\editorial.sqlite3'),
    [int] $Port = 8765
)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectDirectory '.venv\Scripts\whoami.exe'
$client = Join-Path $projectDirectory '.cache\cloudflared\cloudflared.exe'
$logs = Join-Path $projectDirectory '.cache\private-demo'
$expectedHash = '86AEE4017B26625CEE8484C113558F48EFFA4CD47F7AA05FCF425604E5D2B23C'
foreach ($email in $AllowedMail) {
    if ($email -notmatch '^[A-Za-z0-9.!#$%&''+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$') {
        throw 'Provide explicit individual email addresses for private access.'
    }
}
if (-not $AllowedMail.Count -or -not (Test-Path -LiteralPath $EnvFile) -or -not (Test-Path -LiteralPath $launcher)) {
    throw 'An allowed email, existing environment file and installed project environment are required.'
}
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose a port between 1024 and 65535.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw 'The selected port is already in use; choose another port.'
}
if (-not (Test-Path -LiteralPath $client)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $client) | Out-Null
    Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.0/cloudflared-windows-amd64.exe' -OutFile "$client.part"
    if ((Get-FileHash -LiteralPath "$client.part" -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Client download checksum mismatch.' }
    Move-Item -LiteralPath "$client.part" -Destination $client
}
if ((Get-FileHash -LiteralPath $client -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Client checksum mismatch.' }
$clientHelp = (& $client tunnel --help) -join "`n"
if ($LASTEXITCODE -ne 0 -or $clientHelp -notmatch '--allowed-mail') { throw 'Client does not support protected Quick Tunnels.' }
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$previousEnvFile = $env:WHOAMI_ENV_FILE
$previousOffline = $env:WHOAMI_OFFLINE
$previousDemo = $env:WHOAMI_DEMO
$previousThreads = $env:WHOAMI_EMBEDDING_THREADS
$appProcess = $null
$tunnelProcess = $null
function Get-LaunchProcessIds([int] $ProcessId) {
    $ProcessId
    foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId")) {
        Get-LaunchProcessIds -ProcessId $child.ProcessId
    }
}
function Stop-LaunchProcess($Process) {
    if ($Process -and -not $Process.HasExited) {
        $ownedIds = @(Get-LaunchProcessIds -ProcessId $Process.Id)
        [Array]::Reverse($ownedIds)
        foreach ($ownedId in $ownedIds) { Stop-Process -Id $ownedId -ErrorAction SilentlyContinue }
    }
}
try {
    $env:WHOAMI_ENV_FILE = (Resolve-Path -LiteralPath $EnvFile).Path
    $env:WHOAMI_OFFLINE = '0'
    $env:WHOAMI_DEMO = '0'
    $env:WHOAMI_EMBEDDING_THREADS = '4'
    # Start-Process joins arguments on Windows; quote paths explicitly and reject embedded quotes.
    if ($Database.Contains('"')) { throw 'Database path contains an invalid quote.' }
    $appProcess = Start-Process -FilePath $launcher -ArgumentList @('local-demo', '--database', "`"$Database`"", '--port', $Port) -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs\app.out.log" -RedirectStandardError "$logs\app.err.log"
    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        if ($appProcess.HasExited) { throw 'App failed to start. Inspect the local app error log.' }
        try {
            $readiness = Invoke-RestMethod "http://127.0.0.1:$Port/demo-readiness" -TimeoutSec 2
            if ($readiness.ready -and $readiness.retrieval.StartsWith('hybrid:')) { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'The app did not confirm local semantic retrieval.' }
    $tunnelProcess = Start-Process -FilePath $client -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port", '--allowed-mail', ($AllowedMail -join ','), '--no-autoupdate') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs\tunnel.out.log" -RedirectStandardError "$logs\tunnel.err.log"
    $publicUrl = $null
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($tunnelProcess.HasExited) { throw 'Protected tunnel failed. Inspect its local error log.' }
        $content = Get-Content -LiteralPath "$logs\tunnel.err.log" -Raw -ErrorAction SilentlyContinue
        if ($content -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $publicUrl = $Matches[0]; break }
        Start-Sleep -Seconds 1
    }
    if (-not $publicUrl) { throw 'No temporary URL was returned.' }
    # A PIN gate must block anonymous reads and writes before the URL is presented as private.
    $accessChecks = @(
        @{ Path = '/'; Method = 'GET' },
        @{ Path = '/demo-readiness'; Method = 'GET' },
        @{ Path = '/api/cases/__access_probe__/assistant'; Method = 'POST'; Body = '{}'; ContentType = 'application/json' }
    )
    foreach ($check in $accessChecks) {
        $path = $check.Path
        $arguments = @{} + $check
        $arguments.Remove('Path')
        $response = Invoke-WebRequest "$publicUrl$path" @arguments -MaximumRedirection 0 -SkipHttpErrorCheck -ErrorAction SilentlyContinue
        $loginRedirect = $false
        if ($response.Headers.Location) {
            $destination = [Uri]::new([Uri]$publicUrl, [string]@($response.Headers.Location)[0])
            $loginRedirect = $destination.Host.EndsWith('.cloudflareaccess.com') -and $destination.Scheme -eq 'https'
        }
        if ($response.StatusCode -notin @(301, 302, 303, 307, 308, 401, 403) -or
            ($response.StatusCode -lt 400 -and -not $loginRedirect)) {
            throw 'The public endpoint did not confirm an email/PIN access gate.'
        }
    }
    $appIds = @(Get-LaunchProcessIds -ProcessId $appProcess.Id)
    $state = @{ url = $publicUrl; appPids = $appIds; tunnelPid = $tunnelProcess.Id; database = $Database; started = (Get-Date).ToUniversalTime().ToString('o') }
    $state | ConvertTo-Json | Set-Content -LiteralPath "$logs\session.json" -Encoding utf8
    Write-Output "Private temporary demo: $publicUrl"
    Write-Output "Keep this PC connected. To stop only these processes: Stop-Process -Id $(($appIds + $tunnelProcess.Id) -join ',')"
} catch {
    Stop-LaunchProcess $tunnelProcess
    Stop-LaunchProcess $appProcess
    throw
} finally {
    $env:WHOAMI_ENV_FILE = $previousEnvFile
    $env:WHOAMI_OFFLINE = $previousOffline
    $env:WHOAMI_DEMO = $previousDemo
    $env:WHOAMI_EMBEDDING_THREADS = $previousThreads
}
