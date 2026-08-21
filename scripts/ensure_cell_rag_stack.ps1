param(
    [string]$HostName = $env:CELL_RAG_SSH_HOST,
    [int]$SshPort = $(if ($env:CELL_RAG_SSH_PORT) { [int]$env:CELL_RAG_SSH_PORT } else { 22 }),
    [string]$User = $env:CELL_RAG_SSH_USER,
    [string]$IdentityFile = $env:CELL_RAG_SSH_KEY,
    [string]$RemoteProjectRoot = $env:CELL_RAG_RUNTIME_DIR,
    [switch]$OpenTunnel
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "Set -HostName or CELL_RAG_SSH_HOST."
}

if (-not $User) {
    throw "Set -User or CELL_RAG_SSH_USER."
}

if (-not $RemoteProjectRoot) {
    throw "Set -RemoteProjectRoot or CELL_RAG_RUNTIME_DIR."
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

$target = "$User@$HostName"
$tunnelScript = Join-Path $PSScriptRoot "public_api_tunnel.ps1"
$sshArgs = @(
    "-p", "$SshPort",
    "-o", "ConnectTimeout=20",
    "-o", "ServerAliveInterval=30",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=NUL"
)

if ($IdentityFile) {
    $sshArgs += @("-i", $IdentityFile, "-o", "IdentitiesOnly=yes")
}

$sshArgs += @("$target", "cd $RemoteProjectRoot && scripts/ensure_stack.sh")

Write-Host "Ensuring remote Cell RAG stack on $target..."
& ssh.exe @sshArgs

if ($LASTEXITCODE -ne 0) {
    throw "Remote stack ensure failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Remote stack is ready."
Write-Host "Use the tunnel URL from this machine: http://127.0.0.1:8020/docs"

if ($OpenTunnel) {
    Write-Host ""
    Write-Host "Opening public API tunnel..."
    & powershell.exe -ExecutionPolicy Bypass -File $tunnelScript -HostName $HostName -SshPort $SshPort -User $User -IdentityFile $IdentityFile
}
else {
    Write-Host ""
    Write-Host "To open the tunnel now, run:"
    $identityArgument = if ($IdentityFile) { " -IdentityFile `"$IdentityFile`"" } else { "" }
    Write-Host "powershell -ExecutionPolicy Bypass -File scripts\public_api_tunnel.ps1 -HostName $HostName -SshPort $SshPort -User $User$identityArgument"
}
