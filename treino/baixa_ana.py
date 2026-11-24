import sys,calendar,datetime as dt,concurrent.futures as cf
sys.path.insert(0,".")
from monitor import ana
import pandas as pd
ST=["56850000","56661000","56110005","56696000","56825000","56846200","56719998"]
months=[(y,m) for y in range(2019,2027) for m in range(1,13) if (2019,10)<=(y,m)<=(2026,11) and m in (10,11,12,1,2,3,4)]
def get(a):
    c,y,m=a
    for _ in range(3):
        try: return [dict(r,c=c) for r in ana.fetch(c,dt.date(y,m,1),dt.date(y,m,calendar.monthrange(y,m)[1]),retries=2)]
        except Exception as e: err=e
    print("FALHA",c,y,m,err,flush=True); return []
rows=[]
with cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(get,[(c,y,m) for c in ST for y,m in months]): rows+=r
df=pd.DataFrame(rows).drop_duplicates(["c","t"])
df.to_csv("ana_hist.csv.gz",index=False)
print(len(df)); print(df.groupby("c")[["nivel_cm","vazao_m3s"]].count())
