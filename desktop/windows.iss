#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
[Setup]
AppName=SlideVoice
AppVersion={#AppVersion}
AppPublisher=SlideVoice
SetupIconFile=assets\SlideVoice.ico
VersionInfoDescription=SlideVoice installer
VersionInfoVersion={#AppVersion}
AppId=org.slidevoice.desktop
DefaultDirName={localappdata}\Programs\SlideVoice
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SlideVoice-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\SlideVoice.exe,0
[Files]
Source: "..\.desktop-build\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\dist\SlideVoice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\SlideVoice"; Filename: "{app}\SlideVoice.exe"; IconFilename: "{app}\SlideVoice.exe"; AppUserModelID: "org.slidevoice.desktop"
Name: "{autodesktop}\SlideVoice"; Filename: "{app}\SlideVoice.exe"; Tasks: desktopicon; IconFilename: "{app}\SlideVoice.exe"; AppUserModelID: "org.slidevoice.desktop"
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Preparing Microsoft WebView2…"; Flags: waituntilterminated; Check: NeedsWebView2
Filename: "{app}\SlideVoice.exe"; Description: "Open SlideVoice"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := not (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version));
end;
