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

mkdir "%BASEDIR%00.Shortcut"

mkdir "%BASEDIR%10.共通"
mkdir "%BASEDIR%20.企画"
mkdir "%BASEDIR%30.設計"
mkdir "%BASEDIR%30.設計\10.RD"
mkdir "%BASEDIR%30.設計\20.BD"
mkdir "%BASEDIR%30.設計\30.FD"
mkdir "%BASEDIR%40.開発"
mkdir "%BASEDIR%40.開発\10.DD"
mkdir "%BASEDIR%40.開発\20.CD"
mkdir "%BASEDIR%40.開発\30.MN"
mkdir "%BASEDIR%40.開発\40.UT"
mkdir "%BASEDIR%40.開発\50.IT"
mkdir "%BASEDIR%50.評価"
mkdir "%BASEDIR%50.評価\60.FT"
mkdir "%BASEDIR%50.評価\70.ST"
mkdir "%BASEDIR%50.評価\80.UAT"
mkdir "%BASEDIR%70.運用"

mkdir "%BASEDIR%90.管理"

@rem pause