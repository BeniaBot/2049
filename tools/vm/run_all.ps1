# The whole clean-machine suite on both test machines, one machine at a time.
# Each run restores the machine to exactly how it was found.
param([string]$Out)
$t = Join-Path $PSScriptRoot 'run_vm_test.ps1'
$b = Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent) 'build_v018'
$machines = @(@('winapps-w11', 'clean-hebrew-user'), @('csharf-w10', 'clean-w10-hebrew'))
foreach ($m in $machines) {
  $vm, $clean = $m
  foreach ($run in @(
      @('update',    "$b\A\2049.exe",       '2049.exe',       'guest_update_test.ps1',    "$b\A,$b\B"),
      @('installer', "$b\A\2049_Setup.exe", '2049_Setup.exe', 'guest_installer_test.ps1', ''),
      @('play',      "$b\A\2049.exe",       '2049.exe',       'guest_play_test.ps1',      ''),
      @('basic',     "$b\A\2049.exe",       '2049.exe',       'guest_test.ps1',           ''))) {
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
