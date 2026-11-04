; Установщик Astra для Windows (Inno Setup 6).
; Сборка из корня репозитория после PyInstaller и tools/build_docs.py:
;   iscc /DAppVersion=1.0.0 packaging\astra.iss
; Результат: dist\installer\Astra-<версия>-setup.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6A2F7C1E-3B8D-4E59-9C41-0D7F2A6B8E13}
AppName=Astra
AppVersion={#AppVersion}
AppVerName=Astra {#AppVersion}
AppPublisher=Astra
AppComments=Термодинамические расчёты на базе NASA CEA
DefaultDirName={autopf}\Astra
DefaultGroupName=Astra
DisableProgramGroupPage=yes
; установка для всех пользователей (с правами администратора) или только для себя
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=Astra-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=..\dist\docs\NOTICE.txt
UninstallDisplayName=Astra {#AppVersion}
UninstallDisplayIcon={app}\Astra.exe
SetupIconFile=astra.ico
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Установщик Astra

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[InstallDelete]
; при обновлении удаляем прежнюю папку библиотек, чтобы не смешивались файлы разных сборок
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Astra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; руководство и справка (HTML, собираются tools/build_docs.py)
Source: "..\dist\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Astra"; Filename: "{app}\Astra.exe"
Name: "{group}\Руководство пользователя"; Filename: "{app}\docs\rukovodstvo.html"
Name: "{group}\Самопроверка Astra"; Filename: "{app}\Astra.exe"; Parameters: "--selftest ""{userdocs}\Astra-самопроверка.txt"""
Name: "{group}\Удалить Astra"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Astra"; Filename: "{app}\Astra.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Astra.exe"; Description: "Запустить Astra"; Flags: nowait postinstall skipifsilent

; Проекты пользователя (папка данных AppData\Roaming\Astra) при удалении программы сохраняются.
