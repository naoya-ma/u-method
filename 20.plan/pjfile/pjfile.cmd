rem @echo off
:: ========================================================================
::  -*- coding: shift_jis -*-
::
::  Function:  
::
:: ========================================================================


@rem ----------------------------------------------------------------------
@rem 1. Valiables
@rem ----------------------------------------------------------------------
setlocal enabledelayedexpansion

set CMDNAME=pjfile.cmd
set MAINPS=pjfile.ps1
::set time2=%time: =0%
::set FN=%date:/=%%time2:~-11,2%%time2:~-8,2%
::set LOGFILE="%~dp0%COMPUTERNAME%-%CMDNAME%-%FN%.log"

::set STYLEOPTION=-windowstyle Minimize
::set STYLEOPTION=-windowstyle Maximize
::set STYLEOPTION=-windowstyle hidden
::set PSHVER=-v 2

@rem ----------------------------------------------------------------------
@rem 2. Init
@rem ----------------------------------------------------------------------

set USAGE=NO
if "%1" == "/h" set USAGE=YES
if "%1" == "/H" set USAGE=YES
if "%1" == "/?" set USAGE=YES
if "%2" == "" if not"%1" == "" set USAGE=YES
if "%USAGE%" == "YES" (
  echo usage: %CMDNAME% 
  exit /b 1
)

@rem ----------------------------------------------------------------------
@rem 3. Prelude
@rem ----------------------------------------------------------------------

echo [INFO] %CMDNAME%:
echo [INFO] The application is being executed now.... Please wait for a while.  
echo %DATE% %TIME%:%CMDNAME%:INFO:Start

@rem ----------------------------------------------------------------------
@rem 4. Movement
@rem ----------------------------------------------------------------------

powershell %STYLEOPTION% %PSHVER% -NoProfile -ExecutionPolicy ByPass "%~dp0%MAINPS%" %1 %2
if not %ERRORLEVEL% == 0 (
  echo %DATE% %TIME%:%CMDNAME%:ERROR:Exec Error. FILE=%MAINPS% rc=%ERRORLEVEL%
  echo.
  @set /p <nul=Press Any Key to exit
  @pause > nul
  exit /b %ERRORLEVEL%
)
goto finale


@rem ----------------------------------------------------------------------
@rem 5. Postlude
@rem ----------------------------------------------------------------------

:postlude
::

@rem ----------------------------------------------------------------------
@rem 6. Finale
@rem ----------------------------------------------------------------------

:finale
echo %DATE% %TIME%:%CMDNAME%:INFO:Finished. 
echo.
:error-skip
@set /p <nul=Press Any Key to exit
@pause > nul
exit /b 0
