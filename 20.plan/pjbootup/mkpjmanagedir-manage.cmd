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

mkdir "%BASEDIR%100.�������j"
mkdir "%BASEDIR%110.�v��"
mkdir "%BASEDIR%120.�����̐�"
mkdir "%BASEDIR%130.���[��"
mkdir "%BASEDIR%140.��"

mkdir "%BASEDIR%200.--------------"
mkdir "%BASEDIR%200.��c��"
mkdir "%BASEDIR%210.����"
mkdir "%BASEDIR%220.�O��"
mkdir "%BASEDIR%230.���"
mkdir "%BASEDIR%240.�T�u�`�[��"

mkdir "%BASEDIR%300.--------------"
mkdir "%BASEDIR%300.�d�l�Ǘ�"
mkdir "%BASEDIR%400.�ۑ�Ǘ�"
mkdir "%BASEDIR%500.�\���Ǘ�"

mkdir "%BASEDIR%600.�i���Ǘ�"
mkdir "%BASEDIR%610.���X�N�Ǘ�"
mkdir "%BASEDIR%620.�Ȃ��Ȃ�����"
mkdir "%BASEDIR%630.�׋���"

mkdir "%BASEDIR%700.--------------"
mkdir "%BASEDIR%700.�̌n�Ǘ�"
mkdir "%BASEDIR%710.�v���Z�X�Ǘ�"
mkdir "%BASEDIR%720.�����[�X�Ǘ�"
mkdir "%BASEDIR%730.�₢���킹�Ǘ�"

mkdir "%BASEDIR%800.--------------"
mkdir "%BASEDIR%800.�\���Ǘ�"
mkdir "%BASEDIR%810.�ύX�Ǘ�"
mkdir "%BASEDIR%820.���ی�"
mkdir "%BASEDIR%830.�C���V�f���g�Ǘ�"
mkdir "%BASEDIR%840.���p��"

mkdir "%BASEDIR%900.--------------"
mkdir "%BASEDIR%900.�t�H�[�}�b�g"
mkdir "%BASEDIR%910.��p�Ǘ�"
mkdir "%BASEDIR%920.�ؗp�ݏo"
mkdir "%BASEDIR%990.���̑�"

@rem pause
