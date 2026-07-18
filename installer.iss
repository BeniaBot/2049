; ============================================================
;  2049 - Inno Setup installer script
; ============================================================
;  One-time setup:
;    1. Install Inno Setup (free): https://jrsoftware.org/isdl.php
;    2. Build the game exe first with build_exe.bat  (creates dist\2049.exe)
;    3. Open THIS file in Inno Setup and press "Compile" (or run
;       build_installer.bat).
;  Result:  Output\2049_Setup.exe  - a normal Windows installer that
;  installs the SAME 2049.exe, plus a desktop shortcut and Start-menu entry.
; ============================================================

#define MyAppName "2049"
#define MyAppVersion "0.13.0"
#define MyAppPublisher "BeniaBot"
#define MyAppURL "https://github.com/BeniaBot/2049"
#define MyAppExeName "2049.exe"

[Setup]
AppId={{A2049BENI-2049-4B49-9C49-2049BENIABOT}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Install per-user so no admin rights are needed (works for everyone).
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=2049_Setup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Show a nice language selector; both Hebrew UI and English are common.

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; The game itself (the exact same standalone exe as the portable version)
Source: "dist\2049.exe"; DestDir: "{app}"; Flags: ignoreversion
; Bundle the icon so shortcuts look right
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start-menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
; Desktop shortcut (only if the user ticked the box)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Offer to launch the game right after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up the icon we copied (config lives in %APPDATA%\2049 and is kept)
Type: files; Name: "{app}\icon.ico"
