; Inno Setup Script for JobHunter Desktop Application
; Generates a professional Windows Setup installer (JobHunter-Setup.exe)

#define MyAppName "JobHunter"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "JobHunter"
#define MyAppExeName "JobHunter.exe"

[Setup]
AppId={{C8E790E5-3A2F-4F81-998E-D93BC9D4AA41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Install for current user (no Administrator password/UAC prompt needed)
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=JobHunter-Setup
SetupIconFile=app_icon.ico
SolidCompression=yes
Compression=lzma2/ultra64
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\JobHunter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
