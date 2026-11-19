# Host side: run guest_test.ps1 on a clean Hyper-V machine and bring the
# results back. Leaves the machine exactly as it was found.
#   powershell -File run_vm_test.ps1 -VMName winapps-w11 -Clean clean-hebrew-user -Exe ...\2049.exe -Out ...
param(
  [Parameter(Mandatory)] [string]$VMName,
  [Parameter(Mandatory)] [string]$Clean,
  [Parameter(Mandatory)] [string]$Exe,
  [Parameter(Mandatory)] [string]$Out,
  [string]$ExeName = '2049.exe',
  [string]$GuestScript = 'guest_test.ps1',
  [string[]]$Folders = @()          # extra folders copied into C:\bench\<name>
)
$ErrorActionPreference = 'Stop'
. D:\Claude\vm\vmtools.ps1
New-Item -ItemType Directory -Force $Out | Out-Null
function Say([string]$s) { "$(Get-Date -Format HH:mm:ss) $s" | Tee-Object -FilePath (Join-Path $Out 'host.log') -Append }

$vm = Get-VM $VMName
$keep = '2049-test-keep-' + (Get-Date -Format 'yyyyMMdd-HHmm')
Say "machine $VMName was $($vm.State); keeping that state as checkpoint $keep"
Checkpoint-VM -Name $VMName -SnapshotName $keep
try {
  Restore-VMSnapshot -VMName $VMName -Name $Clean -Confirm:$false
  if ((Get-VM $VMName).State -ne 'Running') { Start-VM $VMName }
  $cred = Get-BenchCred
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $s = $null
  while (-not $s -and $sw.Elapsed.TotalSeconds -lt 300) {
    try { $s = New-PSSession -VMName $VMName -Credential $cred -ErrorAction Stop } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $s) { throw 'PowerShell Direct never came up' }
  Say "guest reachable after $([int]$sw.Elapsed.TotalSeconds)s"
  # let the desktop settle (auto-logon, first-run shell work)
  Start-Sleep -Seconds 20
  Invoke-Command -Session $s { Remove-Item C:\bench -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory C:\bench | Out-Null }
  Copy-Item $Exe -Destination ("C:\bench\" + $ExeName) -ToSession $s
  Copy-Item (Join-Path $PSScriptRoot $GuestScript) -Destination C:\bench\guest.ps1 -ToSession $s
  # via "powershell -File" a list arrives as one comma-joined string
  foreach ($f in ($Folders | ForEach-Object { $_ -split ',' } | Where-Object { $_ })) {
    $name = Split-Path $f -Leaf
    Invoke-Command -Session $s { param($n) New-Item -ItemType Directory -Force ("C:\bench\" + $n) | Out-Null } -ArgumentList $name
    Get-ChildItem $f -File | Where-Object { $_.Extension -in '.exe', '.txt' } | ForEach-Object {
      Copy-Item $_.FullName -Destination ("C:\bench\" + $name + "\" + $_.Name) -ToSession $s }
  }
  Say "running $GuestScript on the user desktop"
  $r = Invoke-BenchDesktop -VMName $VMName -Exe 'powershell.exe' -Arguments '-NoProfile -ExecutionPolicy Bypass -File C:\bench\guest.ps1' -WaitSeconds 600
  Say "task result $($r.LastResult) state $($r.State)"
  Save-BenchScreen -VMName $VMName -Path (Join-Path $Out 'vm_screen.png') | Out-Null
  Copy-Item -FromSession $s -Path 'C:\bench\out\*' -Destination $Out -Recurse -Force
  Remove-PSSession $s
  Get-Content (Join-Path $Out 'results.txt') -Encoding UTF8 | ForEach-Object { Say $_ }
} finally {
  Say "restoring $VMName to how it was"
  Restore-VMSnapshot -VMName $VMName -Name $keep -Confirm:$false
  Remove-VMSnapshot -VMName $VMName -Name $keep -Confirm:$false
  Say "machine state now: $((Get-VM $VMName).State)"
}
