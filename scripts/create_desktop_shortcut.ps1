$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)

$ShortcutPath = Join-Path $DesktopPath "Marches Publics Maroc.lnk"
$TargetPath = Join-Path $ProjectRoot "Launch_MarchesPublics.bat"
$IconPath = Join-Path $ProjectRoot "assets\marchespublics.ico"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Intelligence & Ingestion des Marchés Publics Marocains"

if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
}

$Shortcut.Save()

Write-Host "======================================================================" -ForegroundColor Green
Write-Host " [OK] Raccourci Windows créé avec succès sur votre Bureau !" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host " Emplacement : $ShortcutPath" -ForegroundColor Cyan
Write-Host " Cible       : $TargetPath" -ForegroundColor Cyan
Write-Host " Icône       : $IconPath" -ForegroundColor Cyan
Write-Host ""
