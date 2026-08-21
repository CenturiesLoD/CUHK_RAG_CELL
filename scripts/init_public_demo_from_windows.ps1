param(
    [string]$HostName = $env:CELL_RAG_SSH_HOST,
    [int]$Port = $(if ($env:CELL_RAG_SSH_PORT) { [int]$env:CELL_RAG_SSH_PORT } else { 22 }),
    [string]$User = $env:CELL_RAG_SSH_USER,
    [string]$IdentityFile = $env:CELL_RAG_SSH_KEY,
    [string]$RuntimeDir = $env:CELL_RAG_RUNTIME_DIR,
    [switch]$RestartTunnel,
    [switch]$PublishEndpoint,
    [switch]$PrintApiKey
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "Set -HostName or CELL_RAG_SSH_HOST."
}

if (-not $User) {
    throw "Set -User or CELL_RAG_SSH_USER."
}

if (-not $RuntimeDir) {
    throw "Set -RuntimeDir or CELL_RAG_RUNTIME_DIR."
}

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
