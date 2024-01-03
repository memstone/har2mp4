#!/usr/bin/python
#! by mostone@hotmail.com
import os
import sys
import json
import base64
import re

ptnTs = re.compile(r"([^/]+.ts)")
ptnM3u = re.compile(r"([^/]+.m3u8)")

# 解析 HAR 文件，返回数据
'''
result:
{
    "ts": {
        "fileName_1": bytes_1,
        "fileName_2": bytes_2,
        "fileName_3": bytes_3,
        ...
    },
    "m3u": [
        [fileName_1, text_1],
        [fileName_2, text_2],
        [fileName_3, text_3],
        ...
    ]
}
'''
def parseHAR(f):
    print("开始读取 HAR 文件...")
    bs = None
    with open(f, "rb") as har:
        bs = har.read()

    print("开始解析 HAR 文件...")
    data = json.loads(bs)
    print(f"HAR file version: {data["log"]["version"]}")

    tsDict = {}
    m3uList = []

    for e in data["log"]["entries"]:
        if not ("content" in e["response"] and "mimeType" in e["response"]["content"]): continue
        # 以文件名为 key, 添加 bytes 内容
        if e["response"]["content"]["mimeType"] == r"video/mp2t":
            tsDict[ptnTs.search(e["request"]["url"]).group()] = base64.b64decode(e["response"]["content"]["text"])
            continue
        
        if not(e["request"]["url"].endswith(".m3u8")): continue
        
        # 获取 m3u8 文件内容
        txt = e["response"]["content"]["text"]
        if "encoding" in e["response"]["content"]:
            if e["response"]["content"]["encoding"] == "base64":
                txt = base64.b64decode(txt, "utf-8")
            else:
                raise Exception(f"未实现的 m3u8 文件编码格式: {e["response"]["content"]["encoding"]}")
        else:
            # #EXTM3U：表明该文件是一个 m3u8 文件。每个 M3U 文件必须将该标签放置在第一行。
            if txt.find(r"\n", 0, 15) != -1:
                txt =txt.replace(r"\n", "\n")

        m3uList.append([
            ptnM3u.search(e["request"]["url"]).group(),
            txt
        ])

    return {"ts": tsDict, "m3u": m3uList}

# 返回 ts 列表，忽略 m3u8 文件头
# [ [ts-file-name, extinfo], [] ...]
def splitTsInfo(s):
    isHead = True
    extInfo = None
    lst = []
    for l in s.splitlines():
        # 跳过文件头，至到出现 "#EXTINF"
        isExtInfo = l.startswith("#EXTINF:")
        if isHead and isExtInfo:
            isHead = False
        if isHead: continue

        if isExtInfo:
            extInfo = l
        elif extInfo is not None:
            lst.append([ptnTs.search(l).group() ,extInfo])
            extInfo = None
        else:
            continue

    return lst

# 删除 cur 中与 prev 重复的项（复制 cur 列表，不改变原始 cur）
def removeRepeat(prev, cur):
    ret = cur.copy()
    for i in range(len(ret) - 1, -1, -1):
        for p in prev:
            # 比较 ts 文件名
            if ret[i][0] == p[0]: 
                del ret[i]
                break
    return ret

# 返回去重后的 m3u8 列表
def getDistinct(m3u):
    # 逐一保存单个 m3u8 文件
    prev = None
    distinct = []
    for f in m3u:
        cur = splitTsInfo(f[1])
        if prev is None:
            distinct.extend(cur)
        else:
            distinct.extend(removeRepeat(prev, cur))

        prev = cur

    return distinct

def outputMulti(data):
    # 逐一保存单个 ts 文件
    for k, v in data["ts"].items():
        with open(k, "wb") as w: w.write(v)

    # 逐一保存单个 m3u8 文件
    m3u = data["m3u"]
    for i in range(0, len(m3u)):
        with open(m3u[i][0].replace(".m3u8", f"_{i+1}.m3u8"), "w") as w: w.write(m3u[i][1])

    # 保存整合的 m3u8 文件，保存 ts 文件列表
    baM3u = bytearray()
    baLst = bytearray()
    dis = getDistinct(m3u)
    for l in dis:
        # 忽略未实际下载的 ts 文件
        if l[0] in data["ts"]:
            baM3u.extend(bytes(f"{l[1]}\n{l[0]}\n", "utf-8"))
            baLst.extend(bytes(f"file {l[0]}\n", "utf-8"))
        else:
            print(f"[提示]：{l[0]} 文件不存在，未输出至 o.m3u8 和 o.lst")

    with open("o.m3u8", "wb") as w: w.write(baM3u)
    with open("o.lst", "wb") as w: w.write(baLst)

def outputMp4(data, f):
    # 合并所有 ts 文件，输出 o.ts
    dis = getDistinct(data["m3u"])
    isFileMiss = False
    with open("o.ts", "wb") as w:
        for l in dis:
            # 忽略未实际下载的 ts 文件
            if l[0] in data["ts"]:
                w.write(data["ts"][l[0]])
            else:
                print(f"[提示]：{l[0]} 文件不存在，忽略之")
                isFileMiss = True

    if isFileMiss and input("是否继续[y/n]:").upper() != "Y": return
    
    # 转 o.ts -> o.mp4
    cmd = f"ffmpeg -i o.ts -c copy {f}"
    os.system(cmd)

# main
# -----------------------------------------------------
# 解析 HAR 文件，合成一个 mp4 文件
# >>> python py文件名 mp4 HAR文件 o.mp4
if len(sys.argv)==4 and sys.argv[1] == "mp4":
    f = sys.argv[2]
    data = parseHAR(f)
    outputMp4(data, sys.argv[3])
    quit()

# 解析 HAR 文件，并提取所有的 ts, m3u8 文件逐一保存到当前目录
# >>> python py文件名 parse HAR文件
if len(sys.argv)==3 and sys.argv[1] == "parse":
    f = sys.argv[2]
    data = parseHAR(f)
    outputMulti(data)
    quit()

# 调用 ffmpeg 截取视频片断
# >>> python py文件名 split o.mp4 ss to ss.mp4
if len(sys.argv)==6 and sys.argv[1] == "split":
    cmd = f"ffmpeg -i {sys.argv[2]} -ss {sys.argv[3]} -to {sys.argv[4]} -c copy {sys.argv[5]}"
    os.system(cmd)
    quit()

# 合并 ts 文件（需在参数中提供 ts 列表文件）
# >>> python py文件名 concat o.lst o.ts
if len(sys.argv)==4 and sys.argv[1] == "concat":
    with open(sys.argv[3], "wb") as dst:
        with open(sys.argv[2], "r") as lst:
            for l in lst:
                fs = l.split()
                with open(fs[1], "rb") as tsbs: dst.write(tsbs.read())
    quit()

print(f'''命令参数不正确，请使用以下格式：
python {sys.argv[0]} mp4 <HAR文件> <o.mp4>
      解析 HAR 文件，合成一个 mp4 文件
      
python {sys.argv[0]} parse <HAR文件>
      解析 HAR 文件，并提取所有的 ts, m3u8 文件逐一保存到当前目录

python {sys.argv[0]} concat <o.lst> <o.ts>
      合并 ts 文件

python {sys.argv[0]} split <o.mp4> <ss> <to> <ss.mp4>
    调用 ffmpeg 截取视频片断          
    ss 和 to 是时间，格式为：HH:MM:SS.MILLISECONDS''')
