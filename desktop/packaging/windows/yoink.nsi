; SPDX-License-Identifier: AGPL-3.0-or-later
; Copyright (C) 2026 Ayoze Torres
;
; Per-user NSIS installer for the Yoink egui app. Installs the self-contained
; binaries to %LOCALAPPDATA%\Yoink, replacing any previous install in place —
; including the legacy React+Tauri app, for the one-time legacy->egui migration
; (the setup .exe is signed with the same minisign key the legacy updater trusts).
; After a silent (/S) install — the in-app self-updater's path — it relaunches
; the app, since the finish page that would otherwise do that is skipped.
;
; Build:  makensis -DVERSION=<x.y.z> -DSRCDIR=<dir with the built binaries> yoink.nsi

Unicode true
ManifestDPIAware true

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "dist"
!endif

!define PRODUCT "Yoink"
!define PUBLISHER "Ayoze Torres"
!define MAINEXE "yoink-desktop.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT}"

Name "${PRODUCT}"
OutFile "Yoink_${VERSION}_x64-setup.exe"
; Fixed per-user location (the same one the legacy Tauri app used), so an update
; or migration overwrites it in place and never needs admin rights.
InstallDir "$LOCALAPPDATA\${PRODUCT}"
RequestExecutionLevel user
SetCompressor /SOLID lzma

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "(C) 2026 ${PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT} setup"

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
; No directory page: the location is fixed (see InstallDir above), which keeps
; the clean-install wipe below pointed only ever at our own per-user dir.
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${MAINEXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; Close a running Yoink (egui or the legacy Tauri build) so its files unlock.
!macro KillRunning
  nsExec::Exec 'taskkill /F /IM yoink-desktop.exe'
  nsExec::Exec 'taskkill /F /IM yoink-core.exe'
  nsExec::Exec 'taskkill /F /IM yoink-minter.exe'
  nsExec::Exec 'taskkill /F /IM Yoink.exe'
  Sleep 500
!macroend

Section "Install"
  !insertmacro KillRunning

  ; Wipe the install dir for a tidy migration (drops legacy Tauri leftovers).
  ; User data never lives here — downloads go to %USERPROFILE%\Downloads\Yoink and
  ; the history DB/config live under the user profile — so this is safe. The
  ; running installer is staged in TEMP, not here, so it can't delete itself.
  RMDir /r "$INSTDIR"
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
  SetOverwrite on

  File "${SRCDIR}\${MAINEXE}"
  File "${SRCDIR}\yoink-core.exe"
  File "${SRCDIR}\yt-dlp.exe"
  File "${SRCDIR}\ffmpeg.exe"
  File "${SRCDIR}\ffprobe.exe"

  CreateShortCut "$SMPROGRAMS\${PRODUCT}.lnk" "$INSTDIR\${MAINEXE}"
  CreateShortCut "$DESKTOP\${PRODUCT}.lnk" "$INSTDIR\${MAINEXE}"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${PRODUCT}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${MAINEXE}"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"

  ; Silent install (the self-updater) skips the finish page, so relaunch here.
  IfSilent 0 +2
    Exec '"$INSTDIR\${MAINEXE}"'
SectionEnd

Section "Uninstall"
  !insertmacro KillRunning
  Delete "$SMPROGRAMS\${PRODUCT}.lnk"
  Delete "$DESKTOP\${PRODUCT}.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
