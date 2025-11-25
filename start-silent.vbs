' Personal Assistant Silent Launcher
' This VBScript launches the GUI without showing a console window

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Check if venv exists
venvPath = scriptDir & "\.launcher_venv\Scripts\python.exe"
If Not fso.FileExists(venvPath) Then
    MsgBox "Virtual environment not found!" & vbCrLf & vbCrLf & _
           "Please run launch-gui.bat first to set up dependencies.", _
           vbCritical, "Personal Assistant"
    WScript.Quit 1
End If

' Launch the Python GUI launcher without showing console
launcherPath = scriptDir & "\launcher.py"
If Not fso.FileExists(launcherPath) Then
    MsgBox "launcher.py not found!", vbCritical, "Personal Assistant"
    WScript.Quit 1
End If

' Run hidden (0 = hidden window, False = don't wait for completion)
WshShell.Run """" & venvPath & """ """ & launcherPath & """", 0, False

WScript.Quit 0
