; Nasolt Vault — Windows installer (NSIS 3).  Build with BUILD_INSTALLER.bat (it runs makensis on this file).
Unicode True

!define APPNAME   "Nasolt Vault"
!define APPVER    "2.0.0"
!define PUBLISHER "Nasolt Studios"
!define EXE       "Nasolt Vault.exe"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NasoltVault"

Name "${APPNAME}"
OutFile "Output\Nasolt_Vault_Setup_${APPVER}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "Software\NasoltVault" "InstallDir"
RequestExecutionLevel user                      ; per-user install: no administrator rights needed
SetCompressor /SOLID lzma
BrandingText "${APPNAME} ${APPVER}"

VIProductVersion "${APPVER}.0"
VIAddVersionKey /LANG=1033 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1033 "CompanyName" "${PUBLISHER}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright (c) ${PUBLISHER}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APPNAME} installer"
VIAddVersionKey /LANG=1033 "FileVersion" "${APPVER}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APPVER}"

!include "MUI2.nsh"
!define MUI_ICON   "..\assets\app.ico"
!define MUI_UNICON "..\assets\app.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "This will install ${APPNAME} ${APPVER} on your computer.$\r$\n$\r$\nInstalled vaults normally live in:$\r$\n%APPDATA%\Nasolt Vault\data$\r$\n$\r$\nAn existing vault beside the program continues to be used. Updating keeps your vault files. Click Next to continue."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ---------- refuse to overwrite a running copy ----------
Function .onInit
  check:
    FindWindow $0 "" "${APPNAME}"
    StrCmp $0 0 done
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "${APPNAME} is running.$\r$\nPlease close it, then click Retry." /SD IDCANCEL IDRETRY check
    Abort
  done:
FunctionEnd

Function un.onInit
  check:
    FindWindow $0 "" "${APPNAME}"
    StrCmp $0 0 done
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "${APPNAME} is running.$\r$\nPlease close it, then click Retry." /SD IDCANCEL IDRETRY check
    Abort
  done:
FunctionEnd

; ---------- install ----------
Section "${APPNAME} (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "..\dist\${EXE}"
  File "installed.flag"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXE}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr   HKCU "Software\NasoltVault" "InstallDir" "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayVersion"  "${APPVER}"
  WriteRegStr   HKCU "${UNINSTKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayIcon"     "$INSTDIR\${EXE}"
  WriteRegStr   HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1

  ; --- offer to bring an existing vault (from the portable version) into the installed copy ---
  ; paths.py deliberately keeps using an existing vault beside the installed exe.
  ; Do not copy to a second location and imply that the app changed storage mode.
  IfFileExists "$INSTDIR\data\vault.enc" 0 +3
    MessageBox MB_OK|MB_ICONINFORMATION "An existing vault was found beside the program. Nasolt Vault will keep using that location. No migration was attempted." /SD IDOK
    Goto migrate_done
  IfFileExists "$APPDATA\Nasolt Vault\data\vault.enc" migrate_done 0
    MessageBox MB_YESNO|MB_ICONQUESTION "Do you already have a Nasolt Vault 'data' folder from the portable version that you want to keep using?$\r$\n$\r$\n(Choose No if this is your first time.)" /SD IDNO IDNO migrate_done
    nsDialogs::SelectFolderDialog "Select your old 'data' folder (the one that contains vault.enc)" ""
    Pop $0
    StrCmp $0 "error" migrate_done
    ClearErrors
    ExecWait '"$INSTDIR\${EXE}" --migrate-vault "$0"' $1
    IfErrors migrate_launch_failed
    StrCmp $1 0 migrate_success
    StrCmp $1 10 migrate_invalid
    StrCmp $1 11 migrate_busy
    StrCmp $1 12 migrate_conflict
    StrCmp $1 13 migrate_unsafe
    StrCmp $1 15 migrate_changed
    StrCmp $1 17 migrate_settings_failed
    MessageBox MB_OK|MB_ICONEXCLAMATION "Migration could not finish. Your original files were kept. Check available space and access permissions, then retry from a verified backup." /SD IDOK
    Goto migrate_done
    migrate_success:
      MessageBox MB_OK|MB_ICONINFORMATION "The encrypted vault was copied and its bytes verified. Unlock it with your usual master password to confirm it is usable. Your original files were kept." /SD IDOK
      Goto migrate_done
    migrate_invalid:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The selected folder has no readable vault.enc with a supported header. Nothing was copied. Choose a different folder or restore from a verified backup." /SD IDOK
      Goto migrate_done
    migrate_busy:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The source vault is in use or its lock cannot be checked. Close the portable app and retry. Nothing was copied." /SD IDOK
      Goto migrate_done
    migrate_conflict:
      MessageBox MB_OK|MB_ICONEXCLAMATION "An installed vault already exists. It was not replaced. Keep both files and choose the vault you intend to use before trying again." /SD IDOK
      Goto migrate_done
    migrate_unsafe:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The selected source or destination uses a link or unsafe path. No vault was copied. Choose an ordinary local folder." /SD IDOK
      Goto migrate_done
    migrate_changed:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The source vault changed during copying. No vault was installed. Close all copies of the app and retry." /SD IDOK
      Goto migrate_done
    migrate_settings_failed:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The encrypted vault was copied and verified, but an optional backup, Lockout Lab file or settings file could not be copied. Your original files were kept. Check both data folders before using the installed copy." /SD IDOK
      Goto migrate_done
    migrate_launch_failed:
      MessageBox MB_OK|MB_ICONEXCLAMATION "The migration helper could not start. No vault was copied. The portable vault is still available in its original folder." /SD IDOK
  migrate_done:
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}"
SectionEnd

LangString DESC_Main    ${LANG_ENGLISH} "The program itself."
LangString DESC_Desktop ${LANG_ENGLISH} "Adds a ${APPNAME} icon to your desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    $(DESC_Main)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_Desktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- uninstall ----------
Section "Uninstall"
  IfFileExists "$INSTDIR\installed.flag" +3 0
    MessageBox MB_OK|MB_ICONSTOP "The installation marker is missing. Uninstallation stopped to avoid deleting files from an unexpected folder." /SD IDOK
    Abort
  ; The app verifies its Run command and shortcut targets before removal.
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --unregister-startup' $0
  IfErrors shortcut_cleanup_failed
  StrCmp $0 0 shortcut_cleanup_done shortcut_cleanup_failed
  shortcut_cleanup_failed:
    MessageBox MB_OK|MB_ICONEXCLAMATION "Startup shortcuts could not be verified or removed. Check the Nasolt Vault Start Menu folder and remove only links you recognize." /SD IDOK
  shortcut_cleanup_done:
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\installed.flag"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"                                   ; only removed if empty
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk"
  RMDir  "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegValue HKCU "${UNINSTKEY}" "DisplayName"
  DeleteRegValue HKCU "${UNINSTKEY}" "DisplayVersion"
  DeleteRegValue HKCU "${UNINSTKEY}" "Publisher"
  DeleteRegValue HKCU "${UNINSTKEY}" "DisplayIcon"
  DeleteRegValue HKCU "${UNINSTKEY}" "InstallLocation"
  DeleteRegValue HKCU "${UNINSTKEY}" "UninstallString"
  DeleteRegValue HKCU "${UNINSTKEY}" "NoModify"
  DeleteRegValue HKCU "${UNINSTKEY}" "NoRepair"
  DeleteRegKey /ifempty HKCU "${UNINSTKEY}"
  DeleteRegValue HKCU "Software\NasoltVault" "InstallDir"
  DeleteRegKey /ifempty HKCU "Software\NasoltVault"
  ; User vaults, backups, settings, logs and exports are always preserved.
  MessageBox MB_OK|MB_ICONINFORMATION "Nasolt Vault was uninstalled. Your vault, backups, settings, logs and exported files were kept. Remove them separately only after verifying a backup." /SD IDOK
SectionEnd
