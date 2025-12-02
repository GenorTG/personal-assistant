Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c launch-gui.bat hidden", 0, False
Set WshShell = Nothing


