#define AppVersion "1.0.4"
[Setup]
AppId={{D772CB63-E6AF-42F5-888C-33DD60A7C854}
AppName=Trollsound
AppVersion={#AppVersion}
DefaultDirName={autopf}\Trollsound
DefaultGroupName=Trollsound
OutputDir=..\dist
OutputBaseFilename=Trollsound-Setup-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\Trollsound.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\dist\Trollsound\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Trollsound"; Filename: "{app}\Trollsound.exe"
Name: "{autodesktop}\Trollsound"; Filename: "{app}\Trollsound.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Trollsound.exe"; Description: "Abrir Trollsound"; Flags: postinstall nowait skipifsilent runasoriginaluser; Check: CanLaunch

[Code]
var
  DriverNeedsRestart: Boolean;

function CanLaunch: Boolean;
begin
  Result := not DriverNeedsRestart;
end;

function NeedRestart: Boolean;
begin
  Result := DriverNeedsRestart;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep <> ssPostInstall then exit;
  if not Exec(ExpandConstant('{app}\Trollsound.exe'), '--check-vb-cable',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then begin
    if not WizardSilent then
      MsgBox('No se pudo verificar VB-Cable. Trollsound lo comprobara al abrirse.', mbError, MB_OK);
    exit;
  end;
  if Code = 0 then exit;
  if WizardSilent then begin
    Log('VB-Cable no operativo. Instalacion automatica del controlador omitida sin consentimiento interactivo.');
    exit;
  end;
  if Code = 11 then
    MsgBox('VB-Cable esta deshabilitado, incompleto o pendiente de reinicio. Comprueba los dispositivos de sonido de Windows. No reinstales un controlador operativo.', mbInformation, MB_OK);
  if MsgBox('No hay un par VB-Cable operativo. Deseas abrir el asistente de descarga e instalacion oficial? Requiere permisos de administrador y reiniciar Windows.',
            mbConfirmation, MB_YESNO) = IDYES then begin
    if Exec(ExpandConstant('{app}\Trollsound.exe'), '--install-vb-cable',
            ExpandConstant('{app}'), SW_SHOWNORMAL, ewWaitUntilTerminated, Code) then begin
      DriverNeedsRestart := Code = 20;
      if (Code <> 20) and (Code <> 12) then
        MsgBox('La instalacion de VB-Cable no se completo. Podras reintentar desde Trollsound. Las macros permaneceran bloqueadas sin el cable.', mbInformation, MB_OK);
    end;
  end;
end;
