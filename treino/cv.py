import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor as HGB
from monitor import features as F
df=pd.read_pickle("base.pkl")
X=F.montar(df)
X=X[X.index.hour%3==0]
X=X[X.index.month.isin([10,11,12,1,2,3,4])]
temp=np.where(X.index.month<=4,X.index.year,X.index.year+1)
X["temp"]=temp
X=X[X.temp<=2026]
feats=[c for c in X.columns if c!="temp"]
Q=[0.1,0.5,0.9]
def modelo(q): return HGB(loss="quantile",quantile=q,max_iter=300,learning_rate=0.05,max_leaf_nodes=31,min_samples_leaf=40,l2_regularization=1.0,random_state=0)
res=[]
for H in F.HORIZONTES:
    y=F.alvo(df,H).reindex(X.index)
    ok=y.notna()&X.gv_h.notna()
    for s in sorted(set(X.temp[ok])):
        tr=ok&(X.temp!=s); te=ok&(X.temp==s)
        if te.sum()<100: continue
        p={q:modelo(q).fit(X.loc[tr,feats],y[tr]).predict(X.loc[te,feats]) for q in Q}
        h0=X.gv_h[te].values; obs=h0+y[te].values
        res.append(pd.DataFrame({"H":H,"temp":s,"t":X.index[te],"h0":h0,"obs":obs,"p10":h0+p[0.1],"p50":h0+p[0.5],"p90":h0+p[0.9]}))
    print("H",H,"ok",flush=True)
R=pd.concat(res); R.to_pickle("cv_loso.pkl")
