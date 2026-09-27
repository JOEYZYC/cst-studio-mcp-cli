param(
    [Parameter(Mandatory=$true)][int]$CstPid,
    [Parameter(Mandatory=$true)][int]$DialogHwnd,
    [Parameter(Mandatory=$true)][string]$ProjectStem
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CstKnownAbortWindow {
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr handle);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr handle, uint command);
}
'@
$handle = [IntPtr]$DialogHwnd
if (-not [CstKnownAbortWindow]::IsWindow($handle) -or
    -not [CstKnownAbortWindow]::IsWindowVisible($handle) -or
    -not [CstKnownAbortWindow]::IsWindowEnabled($handle)) {
    throw 'CST abort confirmation is no longer visible and enabled'
}
$owner = [CstKnownAbortWindow]::GetWindow($handle, 4)
if ($owner -eq [IntPtr]::Zero -or [CstKnownAbortWindow]::IsWindowEnabled($owner)) {
    throw 'The confirmation does not disable its owning project window'
}
$dialog = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
$main = [System.Windows.Automation.AutomationElement]::FromHandle($owner)
$expectedMainTail = "$ProjectStem - CST Studio Suite 2026"
if ($dialog.Current.ProcessId -ne $CstPid -or $main.Current.ProcessId -ne $CstPid -or
    $dialog.Current.Name -cne 'CST MICROWAVE STUDIO 2026' -or
    -not $main.Current.Name.EndsWith($expectedMainTail, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'CST PID, confirmation title, or attached project identity mismatch'
}
$textCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Text
)
$messages = @(
    foreach ($item in $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $textCondition)) {
        try {
            $pattern = $item.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $pattern.DocumentRange.GetText(-1).Trim()
        } catch {}
    }
)
if ($messages.Count -ne 1 -or $messages[0] -cne 'Do you really want to abort this calculation?') {
    throw 'Unrecognized CST dialog message; refusing to choose a button'
}
$buttonCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
)
$buttons = $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
$names = @($buttons | ForEach-Object { $_.Current.Name })
if ($names.Count -ne 3 -or (($names | Sort-Object) -join '|') -cne 'Cancel|No|Yes') {
    throw 'Unrecognized CST dialog buttons; refusing to choose one'
}
$yes = @($buttons | Where-Object { $_.Current.Name -ceq 'Yes' })
if ($yes.Count -ne 1 -or -not $yes[0].Current.IsEnabled) {
    throw 'Exactly one enabled Yes button is required'
}
$yes[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
[pscustomobject]@{
    handled = $true
    pid = $CstPid
    dialog_title = 'CST MICROWAVE STUDIO 2026'
    message = $messages[0]
    buttons = $names
    action = 'invoke_yes'
} | ConvertTo-Json -Compress -Depth 4
