param(
    [string]$HostName = "118.145.32.133",
    [int]$Port = 20484,
    [string]$User = "root",
    [string]$IdentityFile = $env:CELL_RAG_SSH_KEY,
    [string]$RuntimeDir = "/data/L202500484/cell_rag",
    [switch]$RestartTunnel,
    [switch]$PublishEndpoint,
    [switch]$PrintApiKey
)

$ErrorActionPreference = "Stop"

if (-not $IdentityFile) {
    $userProfile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $keyCandidates = @("public_key", "id_ed25519", "id_rsa") |
        ForEach-Object { Join-Path $userProfile ".ssh\$_" }
    $IdentityFile = $keyCandidates | Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
}

if ($IdentityFile -and -not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file was not found: $IdentityFile"
}

$remoteArgs = @()
if ($RestartTunnel) {
    $remoteArgs += "--restart-tunnel"
}
if ($PublishEndpoint) {
    $remoteArgs += "--publish-endpoint"
}
if ($PrintApiKey) {
    $remoteArgs += "--print-api-key"
}

$escapedRuntimeDir = $RuntimeDir.Replace("'", "'\''")
$escapedArgs = ($remoteArgs | ForEach-Object { "'" + $_.Replace("'", "'\''") + "'" }) -join " "
$remoteCommand = "cd '$escapedRuntimeDir' && scripts/init_public_demo.sh $escapedArgs"

$sshArgs = @(
    "-p", "$Port",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=20",
    "-o", "ServerAliveInterval=30",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=NUL"
)

if ($IdentityFile) {
    $sshArgs += @("-i", $IdentityFile, "-o", "IdentitiesOnly=yes")
}

$sshArgs += @("$User@$HostName", $remoteCommand)

& ssh.exe @sshArgs
if ($LASTEXITCODE -ne 0) {
    throw "Hosted demo initialization failed with SSH exit code $LASTEXITCODE."
}
