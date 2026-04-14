; OfficeAgent — Inno Setup 6 script
;
; Compile with:
;   iscc setup.iss ^
;     /DMyAppVersion=1.0.0 ^
;     /DMyTier=standard ^
;     /DDistDir=..\build\dist ^
;     /DOutputDir=..\artifacts ^
;     /DOutputBaseName=OfficeAgent-Setup-v1.0.0-Standard
;
; Or let build.ps1 handle it (recommended).

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MyTier
  #define MyTier "standard"
#endif
#ifndef DistDir
  #define DistDir "..\build\dist"
#endif
#ifndef OutputDir
  #define OutputDir "..\artifacts"
#endif
#ifndef OutputBaseName
  #define OutputBaseName "OfficeAgent-Setup-v" + MyAppVersion + "-Standard"
#endif

#define MyAppName     "OfficeAgent"
#define MyAppPublisher "OfficeAgent"
#define MyAppExeName  "OfficeAgent.exe"

[Setup]
AppId={{8F4A2B1C-3D5E-4F6A-B7C8-9D0E1F2A3B4C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://example.com
DefaultDirName={commonpf64}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseName}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
MinVersion=10.0.19044    ; Windows 10 21H2 minimum
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64

; Installer log — available after install at %TEMP%\OfficeAgent-install.log
SetupLogging=yes

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; \
  GroupDescription: "追加タスク:"; Flags: unchecked

[Files]
; --- WPF Launcher ---
Source: "{#DistDir}\OfficeAgent.exe"; DestDir: "{app}"; Flags: ignoreversion

; --- PyInstaller backend bundle ---
Source: "{#DistDir}\app\OfficeAgentBackend.exe"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "{#DistDir}\app\_internal\*"; DestDir: "{app}\app\_internal"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; --- llama-server binaries (all CPU variants) ---
Source: "{#DistDir}\llm\llama-server-avx2.exe";   DestDir: "{app}\llm"; Flags: ignoreversion
Source: "{#DistDir}\llm\llama-server-avx512.exe";  DestDir: "{app}\llm"; Flags: ignoreversion
Source: "{#DistDir}\llm\llama-server-noavx.exe";   DestDir: "{app}\llm"; Flags: ignoreversion

; --- Model (large file — place last for progress bar accuracy) ---
#if MyTier == "pro"
Source: "{#DistDir}\models\pro.gguf"; DestDir: "{app}\models"; Flags: ignoreversion
#else
Source: "{#DistDir}\models\standard.gguf"; DestDir: "{app}\models"; Flags: ignoreversion
#endif

; --- Config (onlyifdoesntexist: preserve IT customisations on upgrade) ---
Source: "{#DistDir}\config\settings.ini"; DestDir: "{app}\config"; \
  Flags: ignoreversion onlyifdoesntexist

; --- Checksums ---
Source: "{#DistDir}\checksums.sha256"; DestDir: "{app}"; Flags: ignoreversion

; --- Placeholder license (onlyifdoesntexist: preserve real license on upgrade) ---
Source: "{#DistDir}\license.key"; DestDir: "{app}"; \
  Flags: ignoreversion onlyifdoesntexist

; --- WebView2 offline bootstrapper (for Windows 10 machines without WebView2) ---
; Download MicrosoftEdgeWebView2RuntimeInstallerX64.exe from Microsoft and
; place it in installer\redist\ before building Phase 2.
Source: "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; \
  DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\OfficeAgent アンインストール"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

[Run]
; Install WebView2 runtime silently if not already present.
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; \
  Parameters: "/silent /install"; \
  Check: WebView2NotInstalled; \
  StatusMsg: "WebView2 ランタイムをインストールしています..."; \
  Flags: waituntilterminated

; Launch the app after install (optional — user can uncheck).
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Ensure both subprocesses are terminated before uninstall removes files.
Filename: "taskkill"; Parameters: "/F /IM OfficeAgentBackend.exe /T"; \
  Flags: runhidden; RunOnceId: "KillBackend"
Filename: "taskkill"; Parameters: "/F /IM llama-server*.exe /T"; \
  Flags: runhidden; RunOnceId: "KillLlama"

[UninstallDelete]
; Remove log directory created by the app (not part of installed files).
Type: filesandordirs; Name: "{commonappdata}\OfficeAgent\logs"
Type: filesandordirs; Name: "{commonappdata}\OfficeAgent"

[Dirs]
; Create empty output and log directories with correct permissions.
Name: "{commonappdata}\OfficeAgent\logs"; Permissions: users-modify
Name: "{app}\output";                    Permissions: users-modify

[Code]
// ---------------------------------------------------------------------------
// WebView2 detection
// ---------------------------------------------------------------------------
function WebView2NotInstalled(): Boolean;
var
  version: String;
begin
  // Check both HKLM and HKCU for the WebView2 runtime registration.
  Result := not RegQueryStringValue(
    HKEY_LOCAL_MACHINE,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', version);

  if Result then
    Result := not RegQueryStringValue(
      HKEY_CURRENT_USER,
      'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', version);
end;

// ---------------------------------------------------------------------------
// Write version manifest to C:\ProgramData\OfficeAgent\version.json
// ---------------------------------------------------------------------------
procedure WriteVersionManifest();
var
  jsonPath: String;
  json: String;
begin
  jsonPath := ExpandConstant('{commonappdata}\OfficeAgent\version.json');
  json := '{"app_version":"' + '{#MyAppVersion}' + '",' +
          '"tier":"' + '{#MyTier}' + '",' +
          '"install_date":"' + GetDateTimeString('yyyy-mm-dd', '-', ':') + '"}';
  SaveStringToFile(jsonPath, json, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteVersionManifest();
end;
