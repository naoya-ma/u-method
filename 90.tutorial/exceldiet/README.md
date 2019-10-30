# Excel ダイエット

## 1. 現象別アプローチ
### 現象1：ファイルサイズが大きい。起動が遅い
  * 離れた場所に値・数式・関数を使っている(CTRL + END で確認)
  * 不要なシートの削除
  * 不要な行・列の削除
  * 無駄なオブジェクトの削除
  * セル単位のスタイル設定の抑制(標準へ)

### 現象2：Excelの機能を無駄に使いすぎ。処理が重い
  * 自動計算の抑制(手動計算＋F9)
  * 条件付き書式の削減
  * 共有の解除
  * リンクの削減
  * 名前定義の削除

### 現象3：データ量が多い。処理量が多い。固まる
  * Excel関数からマクロへの変更
  * VBA の表示改善
  * ループ処理の改善

### 現象4：アドインや他のソフトの影響による動作遅延

  * 不要なアドインの削除
  * ウィルス対策ソフトのスキャン

## 2. サンプルデータ

  - [Excelベストプラクティス集](excel-bestpractice.xlsm): ケース別のサンプル集
  - [Excelデータサンプル](exceldiet-sample.xlsx): WBSサンプル


## 参考情報

 - [Microsoft|Excel のパフォーマンス: 計算パフォーマンスの強化](https://docs.microsoft.com/ja-jp/office/vba/excel/concepts/excel-performance/excel-improving-calcuation-performance)
 - [Microsoft|Excel が応答しない、停止する、フリーズする、動作しなくなる](https://support.office.com/ja-jp/article/excel-が応答しない、停止する、フリーズする、動作しなくなる-37e7d3c9-9e84-40bf-a805-4ca6853a1ff4)
 - [Microsoft|Excel のステータス バーのオプション](https://support.office.com/ja-jp/article/Excel-のステータス-バーのオプション-6055ecd9-e20f-4a7a-a611-4481bd488c55)
 - [Microsoft|メモリ使用量が少ないように Excel ブックをクリーンアップする方法](https://docs.microsoft.com/ja-jp/office/troubleshoot/excel/clean-workbook-less-memory)
 - [Microsoft|Excel ブックのファイル サイズが予期せず指数関数的に増えることがあります](https://support.microsoft.com/ja-jp/help/930253/the-file-size-of-an-excel-workbook-may-unexpectedly-increase-exponenti)

