; Nasolt Vault — Windows installer (NSIS 3).  Build with BUILD_INSTALLER.bat (it runs makensis on this file).
Unicode True

!define APPNAME   "Nasolt Vault"
!define APPVER    "2.0.0"
!define PUBLISHER "Nasolt Studios"
!define EXE       "Nasolt Vault.exe"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NasoltVault"

Name "${APPNAME}"
OutFile "artifacts\installer\Nasolt_Vault_Setup_${APPVER}.exe"
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
!define MUI_ICON   "..\..\src\nasolt_vault\assets\app.ico"
!define MUI_UNICON "..\..\src\nasolt_vault\assets\app.ico"
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
  ; Check both fixed Start Menu names before copying any installed files.
  ; The bundled helper verifies target, arguments, workdir, icon and hotkey,
  ; plus the previous install marker and HKCU registration for upgrades.
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=NasoltShortcutCheck.exe "artifacts\dist\${EXE}"
  File /oname=installed.flag "installed.flag"
  WriteUninstaller "$PLUGINSDIR\Uninstall.exe"
  IfErrors main_stage_failed
  ; A previous setup may have stopped after replacing one program file.
  ; Its journal and verified local copies restore the previous working pair.
  ClearErrors
  ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-upgrade recover "$INSTDIR"' $0
  IfErrors main_recovery_failed
  StrCmp $0 0 main_recovered main_recovery_failed
  main_stage_failed:
    MessageBox MB_OK|MB_ICONSTOP "Setup could not prepare its program files. Nothing was changed in the installation folder." /SD IDOK
    Abort
  main_recovery_failed:
    MessageBox MB_OK|MB_ICONSTOP "An interrupted installation could not be safely recovered. Existing program and vault files were preserved. Inspect the installation folder and retry from a backup." /SD IDOK
    Abort
  main_recovered:
  ClearErrors
  ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-shortcuts check-main "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors main_shortcut_conflict
  StrCmp $0 0 main_shortcuts_checked main_shortcut_conflict
  main_shortcut_conflict:
    MessageBox MB_OK|MB_ICONSTOP "A Nasolt Vault Start Menu shortcut cannot be verified as belonging to this installation. Setup stopped before changing program files or shortcuts. Resolve the conflicting shortcut and retry." /SD IDOK
    Abort
  main_shortcuts_checked:
  ; A custom install path may already contain unrelated files. Do not copy
  ; over them unless the marker, program files and HKCU registration identify
  ; an existing installation in this exact folder.
  ClearErrors
  ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-shortcuts check-install-dir "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors main_install_dir_conflict
  StrCmp $0 0 main_install_dir_checked main_install_dir_conflict
  main_install_dir_conflict:
    MessageBox MB_OK|MB_ICONSTOP "The selected installation folder contains files that cannot be verified as this Nasolt Vault installation. Setup stopped before copying program files. Choose an empty folder or resolve the existing installation." /SD IDOK
    Abort
  main_install_dir_checked:
  ; Stage and hash the new pair beside the installed files. Keep verified old
  ; copies until the registration is written, so retry can undo interruption.
  ClearErrors
  ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-upgrade install "$INSTDIR" "$PLUGINSDIR"' $0
  IfErrors main_copy_failed
  StrCmp $0 0 main_files_ready main_copy_failed
  main_copy_failed:
    MessageBox MB_OK|MB_ICONSTOP "Setup could not install and verify program files. The previous application was restored when possible. Vault data was not touched. Retry setup after checking available space and access permissions." /SD IDOK
    Abort
  main_files_ready:

  ; A verified executable and uninstaller are now in place. The transaction
  ; remains recoverable until HKCU registration and the marker are verified.
  ClearErrors
  WriteRegStr   HKCU "Software\NasoltVault" "InstallDir" "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayVersion"  "${APPVER}"
  WriteRegStr   HKCU "${UNINSTKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayIcon"     "$INSTDIR\${EXE}"
  WriteRegStr   HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  IfErrors main_registration_failed
  ClearErrors
  ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-upgrade finalize "$INSTDIR"' $0
  IfErrors main_registration_failed
  StrCmp $0 0 main_registration_done main_registration_failed
  main_registration_failed:
    ClearErrors
    ExecWait '"$PLUGINSDIR\NasoltShortcutCheck.exe" --installer-upgrade recover "$INSTDIR"' $0
    MessageBox MB_OK|MB_ICONSTOP "Setup could not complete installation verification. Recovery was attempted; a committed program is kept if cleanup was interrupted. Vault data was not touched. Inspect the installation folder and rerun setup." /SD IDOK
    Abort
  main_registration_done:
  ; Shortcut creation happens after commit. If it fails, the verified program
  ; still opens from its installed folder and setup can be safely retried.
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --installer-shortcuts install-main "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors main_shortcut_install_failed
  StrCmp $0 0 main_shortcut_install_done main_shortcut_install_failed
  main_shortcut_install_failed:
    MessageBox MB_OK|MB_ICONSTOP "Nasolt Vault was installed, but its Start Menu shortcuts could not be completed. The application remains in the installation folder. Resolve the shortcut conflict and retry setup." /SD IDOK
    Abort
  main_shortcut_install_done:

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
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --installer-shortcuts install-desktop "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors desktop_shortcut_conflict
  StrCmp $0 0 desktop_shortcut_done desktop_shortcut_conflict
  desktop_shortcut_conflict:
    MessageBox MB_OK|MB_ICONEXCLAMATION "The desktop shortcut was not created because an existing shortcut could not be verified or the shortcut operation failed. The existing shortcut was preserved." /SD IDOK
  desktop_shortcut_done:
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
  ; Do not remove shortcuts, program files or HKCU values unless this folder
  ; and the uninstall registration agree on the installation being removed.
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --installer-shortcuts check-uninstall "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors uninstall_registration_conflict
  StrCmp $0 0 uninstall_registration_checked uninstall_registration_conflict
  uninstall_registration_conflict:
    MessageBox MB_OK|MB_ICONSTOP "Uninstallation stopped because the program folder or HKCU uninstall registration could not be verified. No shortcuts, program files or vault data were removed." /SD IDOK
    Abort
  uninstall_registration_checked:
  ; Refuse uninstall before removing any files if a fixed-name shortcut is
  ; foreign, unreadable or changed. Other Start Menu contents are preserved.
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --installer-shortcuts uninstall "$INSTDIR" "$SMPROGRAMS" "$DESKTOP"' $0
  IfErrors uninstall_shortcut_conflict
  StrCmp $0 0 uninstall_shortcuts_done uninstall_shortcut_conflict
  uninstall_shortcut_conflict:
    MessageBox MB_OK|MB_ICONSTOP "Uninstall stopped because a Nasolt Vault shortcut could not be verified or removed. No program or vault files were deleted. Resolve the conflicting shortcut and retry." /SD IDOK
    Abort
  uninstall_shortcuts_done:
  ; The app verifies its Run command and shortcut targets before removal.
  ClearErrors
  ExecWait '"$INSTDIR\${EXE}" --unregister-startup' $0
  IfErrors shortcut_cleanup_failed
  StrCmp $0 0 shortcut_cleanup_done shortcut_cleanup_failed
  shortcut_cleanup_failed:
    MessageBox MB_OK|MB_ICONSTOP "Startup registration or shortcuts could not be verified or removed. Uninstallation stopped before deleting program files; resolve the conflict and retry." /SD IDOK
    Abort
  shortcut_cleanup_done:
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\installed.flag"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"                                   ; only removed if empty
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
