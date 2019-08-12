@echo off

setlocal 

set time2=%time: =0%
set FN=%date:/=%%time2:~-11,2%%time2:~-8,2%
@rem ex. 
@rem set date1=%date%
@rem for /f "tokens=3 delims= " %%a in ('chcp') do set cp=%%a
@rem if "%cp%" == "932" (
@rem  set FN=%date1:~-10,4%%date1:~-5,2%%date1:~-2,2%%time2:~-11,2%%time2:~-8,2%
@rem ) else (
@rem  set FN=%date1:~-4,4%%date1:~-10,2%%date1:~-7,2%%time2:~-11,2%%time2:~-8,2%
@rem )

set LOGFILE="%~dp0%COMPUTERNAME%-mkpjmanagedir-%FN%.log"
set BASEDIR="%~dp0%"

rem mkdir "%BASEDIR%000.Shortcut"

mkdir "%BASEDIR%10.メンバー"
mkdir "%BASEDIR%20.計画"
mkdir "%BASEDIR%30.会議体"
mkdir "%BASEDIR%40.テーマ別"
mkdir "%BASEDIR%50.入手"
mkdir "%BASEDIR%60.提供"
mkdir "%BASEDIR%90.その他"

@rem pause
