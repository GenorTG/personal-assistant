@echo off
REM Create Desktop Shortcut
REM This creates a shortcut to the launcher on your desktop

echo Creating desktop shortcut...

REM Get the current directory
set SCRIPT_DIR=%~dp0

REM Create VBScript to make shortcut
set SHORTCUT_SCRIPT=%TEMP%\create_shortcut.vbs

echo Set oWS = WScript.CreateObject("WScript.Shell") > %SHORTCUT_SCRIPT%
echo sLinkFile = oWS.SpecialFolders("Desktop") ^& "\Personal Assistant.lnk" >> %SHORTCUT_SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SHORTCUT_SCRIPT%
echo oLink.TargetPath = "%SCRIPT_DIR%start-silent.vbs" >> %SHORTCUT_SCRIPT%
echo oLink.WorkingDirectory = "%SCRIPT_DIR%" >> %SHORTCUT_SCRIPT%
echo oLink.Description = "Personal Assistant Launcher" >> %SHORTCUT_SCRIPT%
echo oLink.IconLocation = "%SCRIPT_DIR%launcher.py,0" >> %SHORTCUT_SCRIPT%
echo oLink.Save >> %SHORTCUT_SCRIPT%

REM Execute the VBScript
cscript //nologo %SHORTCUT_SCRIPT%

REM Clean up
del %SHORTCUT_SCRIPT%

echo.
echo Desktop shortcut created successfully!
echo You can now double-click "Personal Assistant" on your desktop to launch the app.
echo.
pause
