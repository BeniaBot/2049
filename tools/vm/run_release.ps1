# A release candidate on both clean machines, one machine at a time:
#   update    - the PUBLISHED previous release (A) updates itself, in game,
#               to the candidate (B): the path every player will take
#   installer / play / basic - on the candidate itself
# -Build points at a folder holding A\ (previous release) and B\ (candidate).
# Each run restores the machine to exactly how it was found.
param([string]$Out, [string]$Build)
$t = Join-Path $PSScriptRoot 'run_vm_test.ps1'
$machines = @(@('winapps-w11', 'clean-hebrew-user'), @('csharf-w10', 'clean-w10-hebrew'))
foreach ($m in $machines) {
  $vm, $clean = $m
  foreach ($run in @(
      @('update',    "$Build\A\2049.exe",       '2049.exe',       'guest_update_test.ps1',    "$Build\A,$Build\B"),
      @('installer', "$Build\B\2049_Setup.exe", '2049_Setup.exe', 'guest_installer_test.ps1', ''),
      @('play',      "$Build\B\2049.exe",       '2049.exe',       'guest_play_test.ps1',      ''),
      @('basic',     "$Build\B\2049.exe",       '2049.exe',       'guest_test.ps1',           ''))) {
    $name, $exe, $exeName, $script, $folders = $run
    $dir = Join-Path $Out "$vm-$name"
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $t, '-VMName', $vm, '-Clean', $clean,
           '-Exe', $exe, '-ExeName', $exeName, '-Out', $dir, '-GuestScript', $script)
    if ($folders) { $a += @('-Folders', $folders) }
    & powershell @a | Out-Null
    if ((Get-VM $vm).State -eq 'Running') { Save-VM $vm }
    $res = Get-Content (Join-Path $dir 'results.txt') -Encoding UTF8 -ErrorAction SilentlyContinue
    $pass = @($res | Where-Object { $_ -like 'PASS*' }).Count
    $fail = @($res | Where-Object { $_ -like 'FAIL*' -or $_ -like 'ERROR*' }).Count
    "{0,-12} {1,-10} pass {2,2}  fail {3,2}" -f $vm, $name, $pass, $fail
    $res | Where-Object { $_ -like 'FAIL*' -or $_ -like 'ERROR*' } | ForEach-Object { "    $_" }
  }
  "{0} now: {1}" -f $vm, (Get-VM $vm).State
}
