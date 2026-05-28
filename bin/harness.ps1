#Requires -Version 5.1
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ArgsList
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HarnessPy = Join-Path $ScriptDir "harness.py"

$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonCmd = @("py", "-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonCmd = @("python")
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
  $pythonCmd = @("python3")
} else {
  Write-Error "Nenhum interpretador Python encontrado (py, python, python3)."
  exit 2
}

& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length-1)]) $HarnessPy @ArgsList
exit $LASTEXITCODE
