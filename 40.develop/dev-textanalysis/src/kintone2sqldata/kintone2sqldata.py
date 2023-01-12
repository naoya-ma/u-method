import sys
import toml
import csv

# ------------------------------------------------
# Init
# ------------------------------------------------
rc = 0
debug = False

# ------------------------------------------------
# TOML read
# ------------------------------------------------
obj = toml.load('files.toml')
# print(toml.dumps(obj))

# ------------------------------------------------
# CSV Read and Write
# ------------------------------------------------
csvheaderCheckTbl = [
    [0, 'レコード番号'],
    [1, '作成日時'],
]

for csvfile in obj['csvfile']:
    name = csvfile['name']
    infilename = csvfile['infilename']
    outfilename = csvfile['outfilename']
    if debug:
        print('%s:%s:%s' % (name, infilename, outfilename))
    with open(infilename, encoding='cp932', newline='') as inFile:
        countLines = 0
        # -----------------------------------------------
        # csv check
        # -----------------------------------------------
        csvheader = next(csv.reader(inFile))
        if debug:
            print(csvheader)
        errFlag = False
        for x in csvheaderCheckTbl:
            if csvheader[x[0]] != x[1]:
                print('ERROR:CSVヘッダに誤りがあります。File=%s 列=%d フィールド名=%s' %
                      (infilename, x[0]+1, x[1]))
                errFlag = True
                break
        if (errFlag):
            rc = 1
            continue
        # data read
        csvreader = csv.reader(inFile)

        outFile = open(outfilename, 'w', encoding='utf-8')
        csvwriter = csv.writer(outFile, quoting=csv.QUOTE_ALL)
        csvwriter.writerow(csvheader)

        for row in csvreader:
            countLines = countLines + 1
            if debug:
                print(row)
            row[1].replace('/', '-')
            if debug:
                print(row[1])
            csvwriter.writerow(row)

        inFile.close
        outFile.close

        print('IN:%s:%s(%d)' % (name, infilename, countLines))
        print('OUT:%s:%s(%d):complite' % (name, outfilename, countLines))

# -----------------------------------------------
# finale
# -----------------------------------------------
sys.exit(rc)
