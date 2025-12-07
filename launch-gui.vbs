Set WshShell = CreateObject("WScript.Shell")
' Run the batch file and wait for it to complete (so error checks can run)
WshShell.Run "cmd /c """"" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\launch-gui.bat"" hidden", 0, True
Set WshShell = Nothing


