# u-method: 30-Operation Tools

PJ活動の中で、度々必要となるオペレーション効率化を支援するツール群です。

[TOC]


### getWebContents
  - 概要:  
    URLからWebコンテンツのタイトルを入手  
    
  - ユースケース: 
    - 複数のURL情報から文書タイトル、URL情報だけを抽出したいとき 
    
  - 使い方:   
    - CUIモード  
      gwebc-cui -c [ < URLを記述したテキストファイル名 ]
    - GUIモード  
      gwebc 
    
  - スクリーンショット:    
    <img src="img\gwebc.png" width="460px">
    
  - ビルド方法:        
     - build.cmd  

-----

### qmmd(Quick Make Meeting Directory)
  - 概要:  
    会議用ディレクトリの準備
 
  - ユースケース: 
    会議の用途別に資料置き場を素早く用意したいとき（リーダー会議、開発定例、アドホックなど）
    
  - 使い方:   
    - CUIモード  
      qmmd   ベースディレクトリ    曜日   会議名称(サフィックス）[オプション]  
      オプション:  
      /p　　前週の会議からのディレクトリコピー  
      /t 　　テンプレートディレクトリからのファイルコピー  　
    
  - スクリーンショット:    
```
      > qmmd D:\MEETINGDIR 3 アドホック /t
      > qmmd D:\MEETINGDIR 1 週次定例 /p
      > tree D:\MEETINGDIR
      D:\MEETINGDIR
      ├─00Template-週次定例
      │  ├─01-App
      │  ├─02-Dev
      │  └─03-Ops
      :
      :
```

### mj(myjoblauncher) 

  - 概要:  
    登録しておいたコマンドを画面のボタンから実行できる、社内向けの汎用ランチャーアプリ(Fletアプリ)
    
  - ユースケース: 
    定型作業（バッチ処理・ファイル操作など）をカンタン操作で実行。まとめ実行もできます。

  - スクリーンショット:    
    <img src="img\myjoblauncher.png" width="460px">
    
  - 使い方:    
      [README.md](myjoblauncher/README.md)を参照ください。

-----


