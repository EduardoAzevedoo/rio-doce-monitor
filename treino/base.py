import pandas as pd, numpy as np
from monitor import features as F
def montar_base():
    a=pd.read_csv("ana_hist.csv.gz",parse_dates=["t"],dtype={"c":str})
    a=a[(a.nivel_cm.isna())|((a.nivel_cm>0)&(a.nivel_cm<2500))]
    def serie(c,col):
        s=a[a.c==c].set_index("t")[col].sort_index()
        s=s[~s.index.duplicated()]
        return s.resample("1h").mean()
    df=pd.DataFrame({"gv_h":serie("56850000","nivel_cm"),"gv_q":serie("56850000","vazao_m3s")})
    for k,c in F.POSTOS.items(): df[f"q_{k}"]=serie(c,"vazao_m3s")
    df["gv_h"]=F.limpar(df.gv_h,40); df["gv_q"]=F.limpar(df.gv_q,800)
    for k in F.POSTOS: df[f"q_{k}"]=F.limpar(df[f"q_{k}"],1500)
    r=pd.read_csv("chuva_obs.csv.gz",index_col=0,parse_dates=True)
    for s in F.SUBS+["gv"]: df[f"r_{s}"]=r[s].reindex(df.index)
    return df
if __name__=="__main__":
    df=montar_base(); df.to_pickle("base.pkl")
    print(df.shape); print(df.notna().mean().round(2).to_dict())
    print(df.gv_h.describe().round(1).to_dict())
