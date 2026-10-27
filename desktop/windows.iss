#ifndef AppVersion
  #define AppVersion "0.1.2"
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
Name: dependencies; Description: "Download and prepare local narration and PowerPoint support (internet required)"
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Preparing Microsoft WebView2…"; Flags: waituntilterminated; Check: NeedsWebView2
Filename: "{app}\SlideVoice.exe"; Parameters: "--install-dependencies"; StatusMsg: "Downloading and preparing narration models and PowerPoint support. This may take several minutes..."; Flags: runhidden waituntilterminated; Tasks: dependencies; AfterInstall: CheckDependencies
Filename: "{app}\SlideVoice.exe"; Description: "Open SlideVoice"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := not (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version));
end;

function LoadSetupStatus: String;
var Content: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(ExpandConstant('{localappdata}\SlideVoice\data\setup-status.json'), Content) then
    Result := String(Content);
end;

procedure CheckDependencies;
var ResultCode: Integer;
begin
  if not FileExists(ExpandConstant('{localappdata}\SlideVoice\data\setup-status.json')) then
    Log('Dependency setup did not write a status file; use Settings to repair.');
  { The status is also visible in Settings, with a resumable repair action. }
  if Pos('"status": "complete"', LoadSetupStatus) = 0 then begin
    if not WizardSilent then begin
      while MsgBox('Some components could not finish downloading. Check your internet connection. Retry now? You can also retry later from Settings > Prepare / repair components.', mbError, MB_RETRYCANCEL) = IDRETRY do begin
        Exec(ExpandConstant('{app}\SlideVoice.exe'), '--install-dependencies', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode = 0 then break;
      end;
    end;
  end;
end;
