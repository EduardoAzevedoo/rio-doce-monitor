import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor as HGB
from monitor import features as F
df=pd.read_pickle("base.pkl")
def prep(X):
    X=X[(X.index.hour%3==0)&X.index.month.isin([10,11,12,1,2,3,4])].copy()
    X["temp"]=np.where(X.index.month<=4,X.index.year,X.index.year+1); return X
X=prep(F.montar(df)); feats=[c for c in X.columns if c!="temp"]
# versão com chuva futura = previsão arquivada (antecedência k dias para o bloco k)
fc=pd.read_csv("chuva_prev_arquivo.csv.gz",index_col=0,parse_dates=True).reindex(df.index)
Xf=X.copy()
for k in range(1,6):
    ini,fim=24*(k-1),24*k
    subs={}
    for s in F.SUBS:
        r=fc[f"{s}|precipitation_previous_day{k}"]
        c=r.fillna(0).cumsum(); subs[s]=(c.shift(-fim)-c.shift(-ini)).reindex(Xf.index)
        # sem previsão arquivada -> NaN
        subs[s][r.reindex(Xf.index).isna()]=np.nan
    M=pd.DataFrame(subs)
    Xf[f"rb_f{k}"]=M.mean(axis=1); Xf[f"rmax_f{k}"]=M.max(axis=1)
    if k<=3:
        for s in F.SUBS: Xf[f"r_{s}_f{k}"]=M[s]
Q=[0.1,0.5,0.9]
mk=lambda q:HGB(loss="quantile",quantile=q,max_iter=300,learning_rate=0.05,max_leaf_nodes=31,min_samples_leaf=40,l2_regularization=1.0,random_state=0)
# offsets de calibração (CQR) a partir do CV leave-one-season-out restrito a temporadas <=2024
R=pd.read_pickle("cv_loso.pkl"); R=R[R.temp<=2024]
def regime(h0,p90): return np.where((h0>=280)|(p90>=300),"alto","normal")
R["reg"]=regime(R.h0,R.p90)
E=np.maximum(R.p10-R.obs,R.obs-R.p90)
off=E.groupby([R.H,R.reg]).quantile(0.8).to_dict()
print("offsets CQR (cm):",{k:round(v,1) for k,v in off.items()})
out=[]
for H in F.HORIZONTES:
    y=F.alvo(df,H).reindex(X.index)
    tr=y.notna()&X.gv_h.notna()&(X.temp<=2024)
    ms={q:mk(q).fit(X.loc[tr,feats],y[tr]) for q in Q}
    for nome,XX in [("chuva_observada",X),("chuva_prevista",Xf)]:
        te=y.notna()&XX.gv_h.notna()&XX.temp.isin([2025,2026])
        if nome=="chuva_prevista": te&=XX["rb_f1"].notna()
        P=np.sort(np.column_stack([ms[q].predict(XX.loc[te,feats]) for q in Q]),axis=1)
        h0=XX.gv_h[te].values
        d=pd.DataFrame({"H":H,"cenario":nome,"t":XX.index[te],"h0":h0,"obs":h0+y[te].values,"p10":h0+P[:,0],"p50":h0+P[:,1],"p90":h0+P[:,2]})
        reg=regime(d.h0,d.p90); o=np.array([off[(H,r)] for r in reg])
        d["c10"]=d.p10-o; d["c90"]=d.p90+o
        out.append(d)
T=pd.concat(out); T.to_pickle("teste_honesto.pkl")
def m(g):
    e=(g.p50-g.obs).abs()
    return pd.Series({"n":len(g),"MAE":e.mean(),"MAE_pers":(g.h0-g.obs).abs().mean(),
        "cob_bruta":((g.obs>=g.p10)&(g.obs<=g.p90)).mean(),"cob_calib":((g.obs>=g.c10)&(g.obs<=g.c90)).mean(),"larg_calib":(g.c90-g.c10).mean()})
for nome,g in T.groupby("cenario"):
    print("\n==",nome,"— todas as horas"); print(g.groupby("H").apply(m).round(2).to_string())
    a=g[(g.obs>=300)|(g.h0>=300)]
    print("==",nome,"— água alta"); print(a.groupby("H").apply(m).round(2).to_string())
