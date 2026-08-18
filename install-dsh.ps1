[CmdletBinding()]
param(
    [string]$DshHome,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot

$PythonExe = $null
$PythonPrefix = @()
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = (Get-Command python).Source
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = (Get-Command py).Source
    $PythonPrefix = @("-3")
} else {
    throw "Python was not found. WeWrite requires Python 3.11+."
}

Write-Host "Installing WeWrite CLI..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv tool install --force $Repo
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    & pipx install --force $Repo
} else {
    & $PythonExe @PythonPrefix -m pip install --user $Repo
}

$AdapterArgs = @($PythonPrefix) + @("$Repo\scripts\dsh_adapter.py")
if ($DshHome) {
    $AdapterArgs += @("--dsh-home", $DshHome)
}
$AdapterArgs += "install"
if ($Force) {
    $AdapterArgs += "--force"
}

Write-Host "Installing DeepSeek Harness skills..."
& $PythonExe @AdapterArgs
Write-Host "Done. Run: python scripts/dsh_adapter.py doctor"
