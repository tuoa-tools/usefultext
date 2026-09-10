; Inno Setup script - wraps build\windows (see scripts/build_windows.py) into a per-user installer.
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\windows.iss
; Output: UsefulText-windows-x64-setup.exe in the repo root.

#define AppName "UsefulText"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
; Paths below are relative to the repo root, not to this file's folder.
SourceDir=..
AppId={{4E6C2B7A-9F1D-4C3E-8A5B-2D7F0E9C1B63}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Adam Simmons
AppPublisherURL=https://github.com/tuoa-tools/usefultext
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=UsefulText-windows-x64-setup
SetupIconFile=packaging\icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
WizardStyle=modern

[Files]
Source: "build\windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "packaging\icon.ico"; DestDir: "{app}"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Comment: "Photos of pages into text"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.launcher"; WorkingDir: "{app}"; Description: "Open {#AppName} now"; Flags: postinstall nowait skipifsilent
