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

mkdir "%BASEDIR%100.--------------"

mkdir "%BASEDIR%100.活動方針"
mkdir "%BASEDIR%110.計画"
mkdir "%BASEDIR%120.役割体制"
mkdir "%BASEDIR%130.ルール"
mkdir "%BASEDIR%140.環境"

mkdir "%BASEDIR%200.--------------"
mkdir "%BASEDIR%200.会議体"
mkdir "%BASEDIR%210.入手"
mkdir "%BASEDIR%220.外部"
mkdir "%BASEDIR%230.情報"
mkdir "%BASEDIR%240.サブチーム"

mkdir "%BASEDIR%300.--------------"
mkdir "%BASEDIR%300.仕様管理"
mkdir "%BASEDIR%400.課題管理"
mkdir "%BASEDIR%500.申請管理"

mkdir "%BASEDIR%600.品質管理"
mkdir "%BASEDIR%610.リスク管理"
mkdir "%BASEDIR%620.なぜなぜ分析"
mkdir "%BASEDIR%630.勉強会"

mkdir "%BASEDIR%700.--------------"
mkdir "%BASEDIR%700.体系管理"
mkdir "%BASEDIR%710.プロセス管理"
mkdir "%BASEDIR%720.リリース管理"
mkdir "%BASEDIR%730.問い合わせ管理"

mkdir "%BASEDIR%800.--------------"
mkdir "%BASEDIR%800.構成管理"
mkdir "%BASEDIR%810.変更管理"
mkdir "%BASEDIR%820.情報保護"
mkdir "%BASEDIR%830.インシデント管理"
mkdir "%BASEDIR%840.引継ぎ"

mkdir "%BASEDIR%900.--------------"
mkdir "%BASEDIR%900.フォーマット"
mkdir "%BASEDIR%910.費用管理"
mkdir "%BASEDIR%920.借用貸出"
mkdir "%BASEDIR%990.その他"

@rem pause
