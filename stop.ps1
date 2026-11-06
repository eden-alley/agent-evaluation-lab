$ErrorActionPreference = 'Stop'
$stateFile = Join-Path $PSScriptRoot 'data\runtime\processes.json'
if (!(Test-Path -LiteralPath $stateFile)) { Write-Output 'No recorded services.'; exit 0 }
$state = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
foreach ($processId in @($state.api_pid, $state.web_pid)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if ($null -eq $process) { continue }
    if (!$process.CommandLine -or !$process.CommandLine.Contains($PSScriptRoot)) {
        throw "Process $processId no longer matches this project. It was not stopped."
    }
    $descendants = @()
    $parents = @($processId)
    while ($parents.Count -gt 0) {
        $children = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -in $parents })
        if ($children.Count -eq 0) { break }
        $descendants += $children.ProcessId
        $parents = @($children.ProcessId)
    }
    [array]::Reverse($descendants)
    foreach ($childId in $descendants) { Stop-Process -Id $childId -ErrorAction SilentlyContinue }
    Stop-Process -Id $processId -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $stateFile
Write-Output 'Recorded project services stopped.'
