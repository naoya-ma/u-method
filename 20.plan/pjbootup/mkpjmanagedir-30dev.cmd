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

mkdir "%BASEDIR%10.����"
mkdir "%BASEDIR%20.���"
mkdir "%BASEDIR%30.�݌v"
mkdir "%BASEDIR%30.�݌v\10.RD"
mkdir "%BASEDIR%30.�݌v\20.BD"
mkdir "%BASEDIR%30.�݌v\30.FD"
mkdir "%BASEDIR%40.�J��"
mkdir "%BASEDIR%40.�J��\10.DD"
mkdir "%BASEDIR%40.�J��\20.CD"
mkdir "%BASEDIR%40.�J��\30.MN"
mkdir "%BASEDIR%40.�J��\40.UT"
mkdir "%BASEDIR%40.�J��\50.IT"
mkdir "%BASEDIR%50.�]��"
mkdir "%BASEDIR%50.�]��\60.FT"
mkdir "%BASEDIR%50.�]��\70.ST"
mkdir "%BASEDIR%50.�]��\80.UAT"
mkdir "%BASEDIR%70.�^�p"

mkdir "%BASEDIR%90.�Ǘ�"

@rem pause