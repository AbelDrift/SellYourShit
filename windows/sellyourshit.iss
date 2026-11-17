; Inno Setup-script voor SellYourShit (wordt aangeroepen door build.ps1).
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{8C6E2A55-4E0B-4B8B-9E77-5E1F0A7D2C11}
AppName=SellYourShit
AppVersion={#AppVersion}
AppVerName=SellYourShit {#AppVersion}
AppPublisher=HerNieuw
DefaultDirName={localappdata}\Programs\SellYourShit
DefaultGroupName=SellYourShit
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir={#Uitvoer}
OutputBaseFilename=SellYourShit-{#AppVersion}-setup
SetupIconFile={#BronMap}\sellyourshit.ico
UninstallDisplayIcon={app}\sellyourshit.ico
UninstallDisplayName=SellYourShit
Compression=lzma2/normal
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=no
CloseApplications=yes

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; oude programmaonderdelen weg bij een update (je gegevens staan apart in AppData en blijven staan)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\gtk"
; {app}\modellen blijft staan: daar komt ook het RMBG-1.4-model dat de app zelf downloadt
; (dat mag niet worden meegeleverd); de meegeleverde modellen worden gewoon overschreven.

[Files]
Source: "{#BronMap}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SellYourShit"; Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\start_sellyourshit.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\sellyourshit.ico"; AppUserModelID: "HerNieuw.SellYourShit"
Name: "{autodesktop}\SellYourShit"; Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\start_sellyourshit.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\sellyourshit.ico"; AppUserModelID: "HerNieuw.SellYourShit"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\start_sellyourshit.pyw"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,SellYourShit}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; ook de bestanden die Python later zelf aanmaakt (__pycache__); je gegevens in AppData blijven staan
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\gtk"
Type: filesandordirs; Name: "{app}\modellen"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"
