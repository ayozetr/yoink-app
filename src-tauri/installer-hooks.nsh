; Tauri NSIS installer hooks for Yoink.
;
; Before copying files, make sure no running Yoink — or its lingering backend
; sidecar — still holds the executables we are about to overwrite. The
; PyInstaller --onefile backend can outlive the app on Windows, and then the
; updater fails with "Error opening file for writing ...\yoink-backend.exe".
; Killing the tree here lets an in-place update proceed without a manual stop.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /IM yoink.exe /F /T'
  nsExec::Exec 'taskkill /IM yoink-backend.exe /F /T'
!macroend
