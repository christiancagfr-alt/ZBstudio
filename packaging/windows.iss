#ifndef SourceDir
#define SourceDir "..\dist\ZBStudio"
#endif
#ifndef OutputDir
#define OutputDir "..\installers"
#endif
[Setup]
AppId={{D7BA63AD-5774-45BC-8C74-32890911A850}
AppName=ZB Studio
AppVersion=0.5.0
DefaultDirName={localappdata}\Programs\ZB Studio
DefaultGroupName=ZB Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ZBStudio-0.5.0-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ZBStudio.exe
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\ZB Studio"; Filename: "{app}\ZBStudio.exe"
[Run]
Filename: "{app}\ZBStudio.exe"; Description: "Launch ZB Studio"; Flags: nowait postinstall skipifsilent
