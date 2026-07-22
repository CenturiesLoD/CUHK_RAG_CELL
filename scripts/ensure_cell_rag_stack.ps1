param(
    [string]$HostName = $env:CELL_RAG_SSH_HOST,
    [int]$SshPort = 20484,
    [string]$User = "root",
    [string]$IdentityFile = $env:CELL_RAG_SSH_KEY,
    [string]$RemoteProjectRoot = "/data/L202500484/cell_rag",
    [switch]$OpenTunnel
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "Set -HostName or CELL_RAG_SSH_HOST."
}

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $HOME ".ssh\public_key"
}

$target = "$User@$HostName"
$tunnelScript = Join-Path $PSScriptRoot "mentor_rag_api_tunnel.ps1"
$sshArgs = @(
    "-p", "$SshPort",
    "-i", "$IdentityFile",
    "-o", "ConnectTimeout=20",
    "-o", "ServerAliveInterval=30",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=NUL",
    "$target",
    "cd $RemoteProjectRoot && scripts/ensure_stack.sh"
)

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
    Write-Host "Opening mentor API tunnel..."
    & powershell.exe -ExecutionPolicy Bypass -File $tunnelScript -HostName $HostName -SshPort $SshPort -User $User -IdentityFile $IdentityFile
}
else {
    Write-Host ""
    Write-Host "To open the tunnel now, run:"
    Write-Host "powershell -ExecutionPolicy Bypass -File scripts\mentor_rag_api_tunnel.ps1 -HostName $HostName -IdentityFile `"$IdentityFile`""
}
