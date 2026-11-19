# The exact release binaries (build_v018\final) through play / basic /
# installer on both clean machines, one machine at a time.
param([string]$Out)
$t = Join-Path $PSScriptRoot 'run_vm_test.ps1'
$fin = Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent) 'build_v018\final'
foreach ($m in @(@('winapps-w11', 'clean-hebrew-user'), @('csharf-w10', 'clean-w10-hebrew'))) {
  $vm, $clean = $m
  foreach ($run in @(@('play', '2049.exe', 'guest_play_test.ps1'),
                     @('basic', '2049.exe', 'guest_test.ps1'),
                     @('installer', '2049_Setup.exe', 'guest_installer_test.ps1'))) {
    $name, $file, $script = $run
    $dir = Join-Path $Out "$vm-$name"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $t -VMName $vm -Clean $clean `
        -Exe (Join-Path $fin $file) -ExeName $file -Out $dir -GuestScript $script | Out-Null
    if ((Get-VM $vm).State -eq 'Running') { Save-VM $vm }
    $res = Get-Content (Join-Path $dir 'results.txt') -Encoding UTF8 -ErrorAction SilentlyContinue
    $pass = @($res | Where-Object { $_ -like 'PASS*' }).Count
    $fail = @($res | Where-Object { $_ -like 'FAIL*' -or $_ -like 'ERROR*' }).Count
    "{0,-12} {1,-10} pass {2,2}  fail {3,2}" -f $vm, $name, $pass, $fail
    $res | Where-Object { $_ -like 'FAIL*' -or $_ -like 'ERROR*' } | ForEach-Object { "    $_" }
  }
  "{0} now: {1}" -f $vm, (Get-VM $vm).State
}
