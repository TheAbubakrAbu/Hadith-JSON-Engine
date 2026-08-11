import json
from final_repair import build_index, repair
BOOKS = {
 "bukhari":("eng-bukhari","bukhari"), "muslim":("eng-muslim","muslim"),
 "nasai":("eng-nasai","nasai"), "abudawud":("eng-abudawud","abudawud"),
 "tirmidhi":("eng-tirmidhi","tirmidhi"), "ibnmajah":("eng-ibnmajah","ibnmajah"),
 "malik":("eng-malik","malik"), "ahmed":(None,"ahmad"), "darimi":(None,"darimi"),
 "qudsi40":("engqudsi","forty"), "nawawi40":("eng-nawawi","forty"),
 "shahwaliullah40":(None,"forty"), "aladab_almufrad":(None,"adab"),
 "shamail_muhammadiyah":(None,"shamail"), "riyad_assalihin":(None,"riyadussalihin"),
 "mishkat_almasabih":(None,"mishkat"), "bulugh_almaram":(None,"bulugh"),
}
def main():
    tot={'total':0,'damaged':0,'repaired':0,'unmatched_scarred':0,'ambiguous':0,'unprovable':0}
    rows=[]
    for slug,(fw,cw) in BOOKS.items():
        book=json.load(open(f"{slug}.json")); idxs=[]
        if fw: idxs.append(build_index([h['text'] for h in json.load(open(f"{fw}.json"))['hadiths']]))
        if cw: idxs.append(build_index([x['english'] for x in json.load(open(f"cws/{cw}.json")) if x.get('english')]))
        st,log=repair(book,idxs)
        json.dump(book,open(f"fixed/{slug}.json","w"),ensure_ascii=False,indent=2)
        json.dump(log,open(f"logs/{slug}.repairlog.json","w"),ensure_ascii=False,indent=2)
        for k in tot: tot[k]+=st.get(k,0)
        rows.append((slug,st))
    return rows,tot
if __name__=='__main__':
    rows,tot=main()
    print(f"{'book':<24}{'hadiths':>9}{'damaged':>9}{'repaired':>10}{'folded':>8}")
    for slug,st in rows:
        fold=sum(1 for e in json.load(open(f'logs/{slug}.repairlog.json')) if e.get('narrator_folded'))
        print(f"{slug:<24}{st['total']:>9,}{st['damaged']:>9,}{st['repaired']:>10,}{fold:>8,}")
    print(f"\n{'TOTAL':<24}{tot['total']:>9,}{tot['damaged']:>9,}{tot['repaired']:>10,}")
    print(f"unprovable (left alone): {tot['unprovable']}   ambiguous refused: {tot['ambiguous']}")
