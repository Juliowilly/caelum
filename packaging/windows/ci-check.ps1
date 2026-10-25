# CI check of the Windows build, on the runner's desktop: start Caelum behind the icons and in
# front of them (each with GTK's layered painting off and on), take screenshots, and click its
# controls as a user would (compass, gear, a tab of Settings). Screenshots and logs go to
# checks\. Fails if a click had no effect.
param([string]$Exe = 'dist\caelum\caelum.exe')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Desk {
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(300);
        mouse_event(2, 0, 0, 0, UIntPtr.Zero);   // left down
        mouse_event(4, 0, 0, 0, UIntPtr.Zero);   // left up
    }
}
'@

New-Item -ItemType Directory -Force checks | Out-Null
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$b, $work = $screen.Bounds, $screen.WorkingArea

function Shot($name) {
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $bmp.Save("$PWD\checks\$name.png")
}

$cfgDir = "$env:APPDATA\caelum"
New-Item -ItemType Directory -Force $cfgDir | Out-Null
$failed = @()
# TEMPORARY bisection: which Windows step stops GTK drawing (CAELUM_WIN_SKIP)
$runs = @(@('click-through-off', 'parent'), @('click-through-off', 'wstyle'),
          @('click-through-off', 'pos'), @('click-through-off', 'framechanged'),
          @('click-through-off', 'parent,wstyle'))
foreach ($run in $runs) {
    $place, $env:CAELUM_WIN_SKIP = $run
    $mode = "$place-skip-$($env:CAELUM_WIN_SKIP -replace ',', '+')"
    $ct = if ($place -eq 'behind-icons') { 'true' } else { 'false' }
    Set-Content "$cfgDir\config.json" "{`"click_through`": $ct, `"facing`": 180.0}"
    $p = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 22
    Shot "$mode-1"
    Start-Sleep -Seconds 5
    Shot "$mode-2"            # compared with -1: the sky must keep repainting

    # Compass (centre 62, 95 inside the work area): a click to the right of the centre faces east
    [Desk]::Click($work.Left + 62 + 30, $work.Top + 95)
    Start-Sleep -Seconds 2
    $facing = (Get-Content "$cfgDir\config.json" | ConvertFrom-Json).facing
    if ([math]::Abs($facing - 90) -gt 1) { $failed += "${mode}: compass click (facing $facing)" }
    Shot "$mode-compass"

    # Gear (28 px in from the work area's bottom-right corner) opens Settings
    [Desk]::Click($work.Right - 28, $work.Bottom - 28)
    Start-Sleep -Seconds 4
    $dlg = [Desk]::FindWindow($null, 'Caelum — Settings')
    if ($dlg -eq [IntPtr]::Zero) {
        $failed += "${mode}: gear click opened no Settings"
    } else {
        Shot "$mode-settings"
        # Second tab (Display): the four tabs are centred under the title bar
        $r = New-Object Desk+RECT
        [Desk]::GetWindowRect($dlg, [ref]$r) | Out-Null
        [Desk]::Click([int](($r.Left + $r.Right) / 2 - 45), $r.Top + 55)
        Start-Sleep -Seconds 2
        Shot "$mode-settings-tab"
    }

    $log = "$env:LOCALAPPDATA\caelum\caelum.log"
    if (Test-Path $log) { Copy-Item $log "checks\caelum-$mode.log"; Get-Content $log }
    if ($p.HasExited) { $failed += "${mode}: Caelum exited (code $($p.ExitCode))" }
    else { Stop-Process -Id $p.Id }
    Start-Sleep -Seconds 3
}
if ($failed) { throw ($failed -join '; ') }
