; Inno Setup script for the OpenMob Windows desktop app.
;
; Packages the release build at app\build\windows\x64\runner\Release\ into a
; single setup .exe that installs to Program Files, adds Start Menu (and optional
; desktop) shortcuts, and registers an uninstaller. Version is injected by CI:
;
;   ISCC.exe /DAppVersion=1.2.3 installer\windows\openmob.iss
;
; ISCC resolves [Files] Source paths relative to this script's directory, so the
; build output is referenced as ..\..\app\build\windows\x64\runner\Release.

#define AppName "OpenMob"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "Zevnix AI"
#define AppExeName "openmob.exe"
#define AppUrl "https://github.com/ZevnixAi-Applications/OpenMob"
#define BuildDir "..\..\app\build\windows\x64\runner\Release"

[Setup]
; A stable AppId keeps upgrades/uninstalls tied to the same product across versions.
AppId={{9F5B2E1C-3A4D-4C7E-9B21-0C6D8E2F1A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=Output
OutputBaseFilename=OpenMob-{#AppVersion}-windows-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BuildDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
