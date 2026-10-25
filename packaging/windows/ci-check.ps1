# CI check of the Windows build, on the runner's desktop: start Caelum behind the icons and in
# front of them, take screenshots, and click its
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
    [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r);
    // Does this window's thread answer within 2 s? (SMTO_ABORTIFHUNG)
    public static bool Answers(IntPtr h) { IntPtr r; return SendMessageTimeout(h, 0, IntPtr.Zero, IntPtr.Zero, 2, 2000, out r) != IntPtr.Zero; }
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
    return $bmp
}

# Share of a 20 x 15 grid of points (above the taskbar) that differ between two screenshots
function Changed($x, $y) {
    $n = 0
    for ($i = 0; $i -lt 20; $i++) { for ($j = 0; $j -lt 15; $j++) {
        $px = [int](($i + 0.5) * $work.Width / 20); $py = [int](($j + 0.5) * $work.Height / 15)
        $p1, $p2 = $x.GetPixel($px, $py), $y.GetPixel($px, $py)
        if ([math]::Abs($p1.R - $p2.R) + [math]::Abs($p1.G - $p2.G) + [math]::Abs($p1.B - $p2.B) -gt 30) { $n++ }
    } }
    return $n / 300
}

$cfgDir = "$env:APPDATA\caelum"
New-Item -ItemType Directory -Force $cfgDir | Out-Null
$failed = @()
$settingsTitle = "Caelum $([char]0x2014) Settings"
foreach ($mode in 'behind-icons', 'click-through-off') {
    $ct = if ($mode -eq 'behind-icons') { 'true' } else { 'false' }
    # The runner's terminal covers the compass: show the bare desktop
    (New-Object -ComObject Shell.Application).MinimizeAll()
    Start-Sleep -Seconds 2
    Set-Content "$cfgDir\config.json" "{`"click_through`": $ct, `"facing`": 180.0}"
    $before = Shot "$mode-0"
    $p = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 25
    $s1 = Shot "$mode-1"
    Start-Sleep -Seconds 5
    $null = Shot "$mode-2"
    # The sky must cover most of the desktop it replaced
    $covered = Changed $before $s1
    Write-Output "${mode}: the sky changed $([int]($covered * 100)) % of the desktop"
    if ($covered -lt 0.6) { $failed += "${mode}: sky not visible ($([int]($covered * 100)) % changed)" }

    # Compass (bottom left: centre 62 in, 78 up from the work area's corner): a click to the
    # right of the centre faces east
    [Desk]::Click($work.Left + 62 + 30, $work.Bottom - 78)
    Start-Sleep -Seconds 1
    $null = Shot "$mode-compass-click"
    Start-Sleep -Seconds 2
    $facing = (Get-Content "$cfgDir\config.json" | ConvertFrom-Json).facing
    if ([math]::Abs($facing - 90) -gt 1) { $failed += "${mode}: compass click (facing $facing)" }
    $null = Shot "$mode-compass"

    # Gear (28 px in from the work area's bottom-right corner) opens Settings
    [Desk]::Click($work.Right - 28, $work.Bottom - 28)
    Start-Sleep -Seconds 4
    $null = Shot "$mode-gear"
    $dlg = [Desk]::FindWindow([NullString]::Value, $settingsTitle)   # $null would pass ""
    if ($dlg -eq [IntPtr]::Zero) {
        $failed += "${mode}: gear click opened no Settings"
    } else {
        $null = Shot "$mode-settings"
        # Second tab (Display): the four tabs are centred under the title bar
        $r = New-Object Desk+RECT
        [Desk]::GetWindowRect($dlg, [ref]$r) | Out-Null
        [Desk]::Click([int](($r.Left + $r.Right) / 2 - 45), $r.Top + 55)
        Start-Sleep -Seconds 2
        $null = Shot "$mode-settings-tab"
        # With Settings open, Explorer's desktop and taskbar must still answer (they froze once)
        foreach ($cls in 'Progman', 'Shell_TrayWnd') {
            $w = [Desk]::FindWindow($cls, [NullString]::Value)
            if (-not [Desk]::Answers($w)) { $failed += "${mode}: $cls stopped answering with Settings open" }
        }
    }

    $log = "$env:LOCALAPPDATA\caelum\caelum.log"
    if (Test-Path $log) { Copy-Item $log "checks\caelum-$mode.log"; Get-Content $log }
    if ($p.HasExited) { $failed += "${mode}: Caelum exited (code $($p.ExitCode))" }
    else { Stop-Process -Id $p.Id }
    Start-Sleep -Seconds 3
}
if ($failed) { throw ($failed -join '; ') }
