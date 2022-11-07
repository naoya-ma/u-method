import csv
import re
import MeCab
import neologdn
import fasttext

mecab = MeCab.Tagger('-Owakati -d /usr/lib64/mecab/dic/mecab-ipadic-neologd/')

# ファイル入出力(csv 2 text)
with open('traindata.csv') as fin, open('train_fasttext.txt', 'w') as fout:
    reader = csv.reader(fin)
    next(reader)

    for row in reader:
        label = "__label__{0}".format(row[2])
        # (1) 前処理によるテキストクレンジング
        text = neologdn.normalize(row[1])
        text = re.sub(r'http{|s}?://[\w/:%#\$&\?\(\)~\.=\+\-]+', '', text)
        # (2) 分かち書き＋改行コードの除去
        text = mecab.parse(text).rstrip('\n')
        # (3) ファイル出力
        print(label + ", " + text)
        fout.write('{} , {}\n'.format(label, text))

# ファイル出力
model = fasttext.train_supervised(input="train_fasttext.txt")
model.save_model("model.bin")

ret = model.predict("ハイプ サイクル")
print(ret)
