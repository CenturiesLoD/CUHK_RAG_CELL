param(
    [string]$HostName = "118.145.32.133",
    [int]$Port = 20484,
    [string]$User = "root",
    [string]$IdentityFile = "C:\Users\JXZ\.ssh\public_key",
    [string]$RuntimeDir = "/data/L202500484/cell_rag",
    [switch]$RestartTunnel,
    [switch]$PublishEndpoint,
    [switch]$PrintApiKey
)

$ErrorActionPreference = "Stop"

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

ssh `
    -p $Port `
    -i $IdentityFile `
    -o IdentitiesOnly=yes `
    -o StrictHostKeyChecking=no `
    -o UserKnownHostsFile=NUL `
    "$User@$HostName" `
    $remoteCommand
