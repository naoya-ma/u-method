# 文字テスト

UTF-8 IVS TEST

# 前提ソフトウェア

python3 + sqlite3 

## usage 

```
$ pytyon3 mojitest.py

$ tail -f 10 output.log

2022/07/25 16:54:19.448 MainProcess(534) mojitest.py prelude [INFO]: BEGIN
....
2022/07/25 16:54:19.456 MainProcess(534) mojitest.py main [INFO]: utf-8 IVStest: BEGIN
2022/07/25 16:54:19.564 MainProcess(534) mojitest.py sqlitetest [INFO]: b'\xe8\x91\x9b'
2022/07/25 16:54:19.565 MainProcess(534) mojitest.py sqlitetest [INFO]: (2, '葛󠄁')
2022/07/25 16:54:19.565 MainProcess(534) mojitest.py sqlitetest [INFO]: b'\xe8\x91\x9b\xf3\xa0\x84\x81'
2022/07/25 16:54:19.566 MainProcess(534) mojitest.py sqlitetest [INFO]: (3, '葛󠄀')
2022/07/25 16:54:19.566 MainProcess(534) mojitest.py sqlitetest [INFO]: b'\xe8\x91\x9b\xf3\xa0\x84\x80'
2022/07/25 16:54:19.567 MainProcess(534) mojitest.py sqlitetest [INFO]: (4, '辻')
2022/07/25 16:54:19.567 MainProcess(534) mojitest.py sqlitetest [INFO]: b'\xe8\xbe\xbb'
2022/07/25 16:54:19.567 MainProcess(534) mojitest.py sqlitetest [INFO]: (5, '辻󠄀')
2022/07/25 16:54:19.568 MainProcess(534) mojitest.py sqlitetest [INFO]: b'\xe8\xbe\xbb\xf3\xa0\x84\x80'
2022/07/25 16:54:19.568 MainProcess(534) mojitest.py sqlitetest [INFO]: db close
2022/07/25 16:54:19.570 MainProcess(534) mojitest.py sqlitetest [INFO]: ----
2022/07/25 16:54:19.570 MainProcess(534) mojitest.py sqlitetest [INFO]: END
2022/07/25 16:54:19.571 MainProcess(534) mojitest.py main [INFO]: utf-8 IVStest: END
```
