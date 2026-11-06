param([switch]$Development)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot 'data\runtime'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$web = Join-Path $projectRoot 'apps\web'
$next = Join-Path $web 'node_modules\next\dist\bin\next'
$backend = Join-Path $projectRoot 'backend'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $next)) {
    throw 'Dependencies are missing. Follow README.md setup instructions first.'
}
if (!$Development -and !(Test-Path -LiteralPath (Join-Path $web '.next\BUILD_ID'))) {
    throw 'Build the web app first: cd apps/web; npm run build'
}
foreach ($port in @(8100, 3100)) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync('127.0.0.1', $port)
        if ($connection.Wait(300) -and $client.Connected) { throw "Port $port is already in use. Stop the existing service first." }
    } catch [System.AggregateException] {
        # No listener; this port is available.
    } finally { $client.Dispose() }
}
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$apiProcess = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','lab.main:app','--app-dir',"`"$backend`"",'--host','127.0.0.1','--port','8100') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'api.log') -RedirectStandardError (Join-Path $runtimeDir 'api-error.log')
try {
    $mode = if ($Development) { 'dev' } else { 'start' }
    $node = (Get-Command node.exe).Source
    $webProcess = Start-Process -FilePath $node -ArgumentList @("`"$next`"",$mode,'--hostname','127.0.0.1','--port','3100') -WorkingDirectory $web -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'web.log') -RedirectStandardError (Join-Path $runtimeDir 'web-error.log')
    @{api_pid=$apiProcess.Id;web_pid=$webProcess.Id;project_root=$projectRoot} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'processes.json') -Encoding utf8
    Write-Output 'Workspace: http://127.0.0.1:3100/projects'
    Write-Output 'Framework example: http://127.0.0.1:3100/evaluations/example-candidate?mode=example'
    Write-Output 'Startup is asynchronous. Logs: data/runtime. Stop only these processes with stop.ps1.'
} catch {
    if (!$apiProcess.HasExited) { $apiProcess.Kill() }
    throw
}
