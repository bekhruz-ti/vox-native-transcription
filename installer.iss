; Inno Setup Script for Vox Native Transcription
; Build with: ISCC installer.iss
; Requires Inno Setup 6.x

#define MyAppName "Vox Native Transcription"
#define MyAppPublisher "Vox Native Transcription"
#define MyAppExeName "Vox.exe"
#define MyAppURL "https://github.com/bekhruz-ti/vox-native-transcription"

; Read version from VERSION file
#define FileHandle FileOpen("VERSION")
#define MyAppVersion Trim(FileRead(FileHandle))
#expr FileClose(FileHandle)

[Setup]
; App identity
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install location (user-space, no admin required)
DefaultDirName={localappdata}\Vox
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest

; Output settings
OutputDir=dist
OutputBaseFilename=Vox-Setup-{#MyAppVersion}
SetupIconFile=src\ui\resources\icons\app.ico

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Installer appearance
WizardStyle=modern
DisableProgramGroupPage=yes

; Upgrade behavior
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no

; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Include all files from PyInstaller output
Source: "dist\Vox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Startup entry (optional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Option to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Close running instance before install/upgrade
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Try to close any running instance gracefully
  if Exec('taskkill', '/IM Vox.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    // Wait a moment for the process to fully close
    Sleep(500);
  end;
end;
