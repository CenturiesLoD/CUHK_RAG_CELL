param(
    [string]$HostName = $env:CELL_RAG_SSH_HOST,
    [int]$SshPort = 20484,
    [string]$User = "root",
    [string]$IdentityFile = $env:CELL_RAG_SSH_KEY,
    [int]$LocalPort = 8020,
    [int]$RemotePort = 8020,
    [string]$ApiKey = "",
    [string]$Question = "What is a regulatory T cell?",
    [switch]$NoSmokeTest,
    [switch]$OneShot
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "Set -HostName or CELL_RAG_SSH_HOST."
}

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $HOME ".ssh\public_key"
}

function Wait-Health {
    param(
        [string]$BaseUrl,
        [int]$Attempts = 30
    )

    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            return Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 5
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "Mentor API did not become reachable at $BaseUrl/health."
}

$baseUrl = "http://127.0.0.1:$LocalPort"
$target = "$User@$HostName"
$sshArgs = @(
    "-N",
    "-L", "127.0.0.1:$LocalPort`:127.0.0.1:$RemotePort",
    "-p", "$SshPort",
    "-i", "$IdentityFile",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=NUL",
    "$target"
)

Write-Host "Starting SSH tunnel to $target..."
$process = Start-Process -FilePath "ssh.exe" -ArgumentList $sshArgs -WindowStyle Hidden -PassThru

try {
    $health = Wait-Health -BaseUrl $baseUrl
}
catch {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    throw
}

Write-Host ""
Write-Host "Mentor API tunnel is ready."
Write-Host "Docs URL: $baseUrl/docs"
Write-Host "Health: $($health.status), RAG: $($health.rag_status), backend: $($health.vector_backend), reranker_loaded: $($health.reranker_loaded)"

if (-not $NoSmokeTest) {
    $headers = @{}
    if ($ApiKey) {
        $headers["Authorization"] = "Bearer $ApiKey"
    }

    $body = @{
        question = $Question
        top_k = 3
        max_tokens = 220
        include_sources = $true
    } | ConvertTo-Json

    try {
        $answer = Invoke-RestMethod -Method Post -Uri "$baseUrl/ask" -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec 300
        Write-Host ""
        Write-Host "Smoke query passed."
        Write-Host "Question: $Question"
        Write-Host "Answer:"
        Write-Host $answer.answer
        Write-Host ""
        Write-Host "Citation check:"
        $answer.citation_check | ConvertTo-Json -Depth 6
    }
    catch {
        Write-Host ""
        Write-Host "Health succeeded, but /ask failed."
        Write-Host "If the server has MENTOR_API_KEY set, rerun this script with -ApiKey <key>."
        throw
    }
}

Write-Host ""
if ($OneShot) {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    Write-Host "Tunnel stopped because -OneShot was used."
}
else {
    Write-Host "Tunnel process id: $($process.Id)"
    Write-Host "Keep this PowerShell session open while mentors test the API."
    Write-Host "Stop the tunnel with: Stop-Process -Id $($process.Id)"
}
