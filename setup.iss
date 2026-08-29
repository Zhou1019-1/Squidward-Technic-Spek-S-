; 章鱼频谱查看器 - Inno Setup 安装包脚本
#define AppName "章鱼频谱查看器"
#define AppVersion "1.0.0"
#define AppPublisher "章鱼工作室"
#define AppExe "章鱼频谱查看器.exe"

[Setup]
AppId={{8F3A2E71-0C70-4AB5-9E47-0D2026082901}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\OctopusSpectrumViewer
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=章鱼频谱查看器-setup-1.0.0
SetupIconFile=icon\HMSicon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent
