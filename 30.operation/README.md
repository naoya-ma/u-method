# u-method: 30-Operation Tools

PJ活動の中で度々必要なオペレーションを効率化するツールです。

[TOC]


### getWebContents
  - 概要:  
    URLからWebコンテンツのタイトルを入手  
    
  - Use scene:
    - 複数のURL情報から文書タイトルを知りたいとき
    - URL情報だけを抽出したいとき 
    
  - usage:   
    - CUIモード  
      gwebc-cui -c [ < URLを記述したテキストファイル名 ]
    - GUIモード  
      gwebc 
    
  - snapshot:    
    <img src="img\gwebc.png" width="460px">
    
  -  build:        
     - build.cmd  
-----

### qmmd(Quick Make Meeting Directory)
  - 概要:  
    会議用ディレクトリの準備
 
  - Use scene:  
    会議の用途別に資料置き場を素早く用意したいとき（リーダー会議、開発定例、アドホックなど）
    
  - usage:   
    - CUIモード  
      qmmd   ベースディレクトリ    曜日   会議名称(サフィックス）[オプション]  
      オプション:  
      /p　　前週の会議からのディレクトリコピー  
      /t 　　テンプレートディレクトリからのファイルコピー  　
    
  - snapshot:    
```
> qmmd D:\MEETINGDIR 3 アドホック /t
> qmmd D:\MEETINGDIR 1 週次定例 /p
> tree D:\MEETINGDIR
D:\MEETINGDIR
├─00Template-週次定例
│  ├─01-App
│  ├─02-Dev
│  └─03-Ops
├─00Template-アドホック
│  ├─課題
│  └─テーマ別
│  :
├─20200714-アドホック
│  ├─課題
│  └─テーマ別
├─20200720-週次定例
│  ├─01-App
│  ├─02-Dev
│  └─03-Ops
├─20200727-週次定例
│  ├─01-App
│  ├─02-Dev
│  └─03-Ops
└─20200729-アドホック
```
-----


