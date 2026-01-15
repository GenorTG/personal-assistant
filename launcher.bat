@echo off
REM Windows launcher menu for Personal Assistant
REM Uses PowerShell for a simple GUI menu

setlocal
cd /d "%~dp0"

REM Check if PowerShell is available
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PowerShell not found. Using simple menu...
    goto :simple_menu
)

REM Use PowerShell for GUI menu
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$choices = @('Install', 'Update and Start', 'Start', 'Exit'); ^
$title = 'Personal Assistant'; ^
$message = 'Choose an action:'; ^
$choice = $choices | Out-GridView -Title $title -OutputMode Single; ^
if ($choice) { ^
    switch ($choice) { ^
        'Install' { Start-Process -FilePath 'install.bat' -WindowStyle Normal } ^
        'Update and Start' { Start-Process -FilePath 'update-and-start.bat' -WindowStyle Normal } ^
        'Start' { Start-Process -FilePath 'start.bat' -WindowStyle Normal } ^
        'Exit' { exit } ^
    } ^
}"

if %ERRORLEVEL% EQU 0 goto :end

:simple_menu
REM Fallback to simple text menu
echo.
echo ==========================================
echo Personal Assistant
echo ==========================================
echo.
echo Choose an action:
echo   1) Install
echo   2) Update and Start
echo   3) Start
echo   4) Exit
echo.
set /p choice="Enter choice [1-4]: "

if "%choice%"=="1" (
    call install.bat
) else if "%choice%"=="2" (
    call update-and-start.bat
) else if "%choice%"=="3" (
    call start.bat
) else (
    exit /b 0
)

:end
endlocal
