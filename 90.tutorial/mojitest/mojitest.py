#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Unicode IVS
#
#

import io
import sys
import json
from logging import getLogger, config
import sqlite3

def prelude():
    global logger 

    with open('./config-log.json', 'r') as f:
        log_conf = json.load(f)
    config.dictConfig(log_conf)
    logger = getLogger( __file__ )
    print (__file__)
    logger.info( 'BEGIN' )

    logger.critical('critical message')
    logger.info('info message')
    logger.error('error message')
    logger.warning('warning message')
    logger.debug('debug message')
    #logger.notice('notice message')

    logger.info( 'sys.getdefaultencoding=' + sys.getdefaultencoding())

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logger.info( 'END')

def basictest():

    logger.info( 'START')

    # ---------------------------------------------------------------
    # 葛[UTF-8 3バイト] 
    # ---------------------------------------------------------------
    moji1 = b'\xE8\x91\x9B'.decode('utf-8')  
    logger.info ( 'str=' + moji1 )
    logger.info ( 'class type=' + str(type(moji1) ))
    logger.info ( 'str.len=' + str(len(moji1) ))
    logger.info ( moji1 )
    logger.info ( '----' )
 
    # ---------------------------------------------------------------
    # 東京都葛飾区の葛[UTF-8 3バイト + IVS 3バイト] 
    # ---------------------------------------------------------------
    moji2  = b'\xE8\x91\x9B\xF3\xA0\x84\x81'.decode('utf-8')  
    logger.info ( 'str=' + moji2 )
    logger.info ( 'class type=' + str(type(moji2) ))
    logger.info ( 'str.len=' + str(len(moji2) ))
    logger.info ( '東京都' + moji2 + '飾区(カツシカク)'  )
    logger.info ( '----' )

    # ---------------------------------------------------------------
    # 奈良県葛󠄀城市の葛󠄀[UTF-8 3バイト + IVS 3バイト]
    #   https://www.city.katsuragi.nara.jp/shisei/shinoshokai/3700.html
    # ---------------------------------------------------------------
    moji3  = b'\xE8\x91\x9B\xF3\xA0\x84\x80'.decode('utf-8')  
    logger.info ( 'str=' + moji3 )
    logger.info ( 'class type=' + str(type(moji3) ))
    logger.info ( 'str.len=' + str(len(moji3) ))
    logger.info ( '京都府' + moji3 + '城市(カツラギシ)' )
    logger.info ( '----' )

    # ---------------------------------------------------------------
    # 辻(2点ツジ)
    # ---------------------------------------------------------------
    moji4 = '\U00008FBB'
    logger.info ( 'str=' + moji4 )
    logger.info ( 'class type=' + str(type(moji4) ))
    logger.info ( 'str.len=' + str(len(moji4) ))
    logger.info ( '辻(2点ツジ)' )
    logger.info ( 'char=' + '辻'.encode('utf-8', 'replace').hex() )
    logger.info ( 'char=' + moji4.encode('utf-8', 'replace').hex() )
    logger.info ( '----' )

    # ---------------------------------------------------------------
    # 辻󠄀(1点ツジ)
    # ---------------------------------------------------------------
    #moji5 = '\U00008FBB\U000E0102'
    moji5 = '辻󠄀'
    logger.info ( 'str=' + moji5 )
    logger.info ( 'class type=' + str(type(moji5) ))
    logger.info ( 'str.len=' + str(len(moji5) ))
    logger.info ( '辻󠄀(1点ツジ)' )
    logger.info ( 'char=' + '辻󠄀'.encode('utf-8', 'replace').hex() )
    logger.info ( 'char=' + moji5.encode('utf-8', 'replace').hex() )

    logger.info ( '----' )
    logger.info ( 'END' )

def sqlitetest():

    logger.info( 'START')
    try:
        # DBオープン処理
        con = sqlite3.connect('example.db')
        cur = con.cursor()
        #con.execute('''DROP TABLE IF EXISTS address''')
        cur.execute('''CREATE TABLE address (id int, data text)''')
 
        sql = ('''INSERT INTO address VALUES (?, ?)''')

        data = [
            (1, b'\xE8\x91\x9B'.decode('utf-8') ) , 
            (2, b'\xE8\x91\x9B\xF3\xA0\x84\x81'.decode('utf-8')) , 
            (3, b'\xE8\x91\x9B\xF3\xA0\x84\x80'.decode('utf-8') ) , 
            (4, '\U00008FBB' ) , 
            (5, '辻󠄀')
        ]

        logger.info(data)

        # DB更新
        cur.executemany(sql, data)
        con.commit()

        # DB内容の出力
        cur.execute("select * from address")
        resultTable = cur.fetchall()
        for result in resultTable:
            logger.info(result)
            logger.info(result[1].encode(encoding='utf-8'))
            
    except Exception as e:
        logger.error(f"Error Occurred: {e}")

    finally:
        if cur is not None :
            logger.info("db close")
            con.close()

    logger.info ( '----' )
    logger.info ( 'END' )

def main():

    # ---------------------------------------------------------------
    # Prelude
    # ---------------------------------------------------------------
    prelude()
    logger.info( 'utf-8 IVStest: BEGIN' )

    # ---------------------------------------------------------------
    # Momvement
    # ---------------------------------------------------------------
    basictest()
    sqlitetest()

    # ---------------------------------------------------------------
    # Finale
    # ---------------------------------------------------------------
    logger.info( 'utf-8 IVStest: END' )

if __name__ == '__main__':
    main()
