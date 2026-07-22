param(
    [string]$BaseUrl = $env:CELL_RAG_DEMO_URL,
    [string]$ApiKey = $env:CELL_RAG_DEMO_API_KEY,
    [string]$Question = "What is a regulatory T cell?",
    [int]$TopK = 5,
    [int]$MaxTokens = 300,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if (-not $ApiKey) {
    throw "Set -ApiKey or CELL_RAG_DEMO_API_KEY."
}

$pythonArgsPrefix = @()
if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = "py"
        $pythonArgsPrefix = @("-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $Python = "python"
    } else {
        throw "Python was not found. Install Python 3 or pass -Python <path>."
    }
}

$client = Join-Path $PSScriptRoot "python_client.py"
$clientArgs = @(
    $client,
    "--api-key", $ApiKey,
    "--question", $Question,
    "--top-k", $TopK,
    "--max-tokens", $MaxTokens
)

if ($BaseUrl) {
    $clientArgs += @("--base-url", $BaseUrl)
}

& $Python @pythonArgsPrefix @clientArgs

exit $LASTEXITCODE
