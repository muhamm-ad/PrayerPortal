REM NOTE: This script is not tested and may not function as expected.

@echo off

REM Define constants and variables for paths
set "USER_NAME=%USERNAME%"
set "CIRCUITPY_REPO=%~dp0CIRCUITPY"
set "CIRCUITPY_DRIVE=%~dpc:\CIRCUITPY"
set "SYNC_DIRECTION=%1"

REM Function to ensure directory exists, otherwise create it
:prepare_directory
if not exist "%~1" (
    echo Directory %~1 does not exist. Creating it now...
    mkdir "%~1"
    if errorlevel 1 (
        echo Failed to create the directory %~1.
        exit /b 1
    )
)
goto :eof

REM Function to perform robocopy and check for errors
:perform_robocopy
robocopy "%~1" "%~2" /E /NFL /NDL /NJH /NJS /NP /R:3 /W:10
if errorlevel 8 (
    echo An error occurred during the robocopy operation.
    exit /b 1
) else (
    echo Operation completed successfully.
)
goto :eof

REM Check if SYNC_DIRECTION is provided
if "%SYNC_DIRECTION%"=="" (
    echo Usage: %0 {push|pull}
    exit /b 1
)

REM Check if CIRCUITPY drive is available
if not exist "%CIRCUITPY_DRIVE%" (
    echo CIRCUITPY drive not found at %CIRCUITPY_DRIVE%. Make sure the drive is connected.
    exit /b 1
)

REM Synchronize based on the provided direction
if "%SYNC_DIRECTION%"=="push" (
    echo Starting file push to CIRCUITPY...
    call :perform_robocopy "%CIRCUITPY_REPO%" "%CIRCUITPY_DRIVE%"
) else if "%SYNC_DIRECTION%"=="pull" (
    echo Starting file pull from CIRCUITPY...
    call :prepare_directory "%CIRCUITPY_REPO%"
    call :perform_robocopy "%CIRCUITPY_DRIVE%" "%CIRCUITPY_REPO%"
) else (
    echo Invalid argument. Use 'push' to send files or 'pull' to receive files.
    exit /b 1
)
