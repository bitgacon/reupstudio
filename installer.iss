[Setup]
AppId={{CFA6A0B6-3DF9-45F7-961A-68A1DF826CE7}
AppName=Reup Voice Studio
AppVersion=__VERSION__
AppPublisher=Reup Voice Studio
DefaultDirName={localappdata}\Programs\ReupVoiceStudio
DefaultGroupName=Reup Voice Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=__OUTPUT__
OutputBaseFilename=ReupVoiceStudio-__VERSION__-Lite-Setup
Compression=lzma2/fast
LZMANumBlockThreads=4
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
SetupIconFile=__STAGE__\web\app.ico
UninstallDisplayIcon={app}\ReupVoiceStudio.exe
CloseApplications=no
LicenseFile=__STAGE__\THIRD_PARTY_NOTICES.md
DisableProgramGroupPage=yes

[Files]
Source: "__STAGE__\*"; DestDir: "{app}"; Excludes: "*.pyc,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Tạo shortcut trên Desktop"; Flags: checkedonce

[Icons]
Name: "{group}\Reup Voice Studio"; Filename: "{app}\ReupVoiceStudio.exe"; WorkingDir: "{app}"; AppUserModelID: "ReupVoiceStudio.Desktop"
Name: "{autodesktop}\Reup Voice Studio"; Filename: "{app}\ReupVoiceStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "ReupVoiceStudio.Desktop"
Name: "{group}\Hướng dẫn"; Filename: "{app}\CAI_DAT_LITE.md"

[Run]
Filename: "{app}\ReupVoiceStudio.exe"; WorkingDir: "{app}"; Description: "Mở Reup Voice Studio"; Flags: nowait postinstall skipifsilent
