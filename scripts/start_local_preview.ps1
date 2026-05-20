param(
    [int]$Port = 8527,
    [string]$Python = "D:\Anaconda\python.exe",
    [string]$DataRoot = "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform",
    [string]$GeoRoot = "D:\Tencent\Data analysis\ANZ_Data_Warehouse\data\Geo_warehouse_streamlit_staging",
    [string]$LogDir = "tmp",
    [int]$TimeoutSeconds = 45,
    [switch]$StopAfterSmoke
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logRoot = Join-Path $repoRoot $LogDir
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

$outLog = Join-Path $logRoot ("streamlit-local-{0}.out.log" -f $Port)
$errLog = Join-Path $logRoot ("streamlit-local-{0}.err.log" -f $Port)
$healthUrl = "http://127.0.0.1:$Port/_stcore/health"
$appUrl = "http://127.0.0.1:$Port"

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already listening. Pick another port with -Port or stop the existing BI preview first."
}

function Quote-ProcessArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + ($Value -replace '\\(?=\\*")', '$0\' -replace '"', '\"') + '"'
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Python
$psi.WorkingDirectory = [string]$repoRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = [bool]$StopAfterSmoke
$psi.RedirectStandardError = [bool]$StopAfterSmoke
$psi.CreateNoWindow = $true

$arguments = @(
    "-m",
    "streamlit",
    "run",
    "app.py",
    "--server.headless",
    "true",
    "--server.port",
    [string]$Port,
    "--browser.gatherUsageStats",
    "false"
)
$psi.Arguments = (($arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " ")

$previewEnv = @{
    DATA_BACKEND = "local"
    LOCAL_DATA_ROOT = $DataRoot
    LOCAL_GEO_STAGING_ROOT = $GeoRoot
    AUTH_ENABLED = "false"
}
$previousEnv = @{}
foreach ($name in $previewEnv.Keys) {
    $previousEnv[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process")
    [System.Environment]::SetEnvironmentVariable($name, [string]$previewEnv[$name], "Process")
}

try {
    $process = [System.Diagnostics.Process]::Start($psi)
} finally {
    foreach ($name in $previousEnv.Keys) {
        [System.Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
    }
}

$stdoutTask = $null
$stderrTask = $null
if ($StopAfterSmoke) {
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
}

try {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) {
            break
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $ready) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        throw "Streamlit did not become healthy within $TimeoutSeconds seconds. Check $outLog and $errLog."
    }

    Write-Output "Streamlit local preview is healthy: $appUrl"
    Write-Output "ProcessId: $($process.Id)"
    if ($StopAfterSmoke) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Write-Output "Stopped smoke-test preview process $($process.Id)."
    }
} finally {
    if ($StopAfterSmoke -and $null -ne $stdoutTask -and $null -ne $stderrTask) {
        $stdoutTask.Wait(2000) | Out-Null
        $stderrTask.Wait(2000) | Out-Null
        $stdoutTask.Result | Set-Content -Path $outLog -Encoding UTF8
        $stderrTask.Result | Set-Content -Path $errLog -Encoding UTF8
    }
}
