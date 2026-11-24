"""Treino final do modelo de previsão do nível em Governador Valadares (todas as temporadas)."""
import json, pickle, datetime as dt, numpy as np, pandas as pd, sklearn, warnings; warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor as HGB
from monitor import features as F
df=pd.read_pickle("base.pkl")
X=F.montar(df); X=X[(X.index.hour%3==0)&X.index.month.isin([10,11,12,1,2,3,4])]
feats=list(X.columns)
Q=[0.1,0.5,0.9]
mk=lambda q:HGB(loss="quantile",quantile=q,max_iter=300,learning_rate=0.05,max_leaf_nodes=31,min_samples_leaf=40,l2_regularization=1.0,random_state=0)
modelos={}
for H in F.HORIZONTES:
    y=F.alvo(df,H).reindex(X.index); ok=y.notna()&X.gv_h.notna()
    modelos[H]={q:mk(q).fit(X.loc[ok,feats],y[ok]) for q in Q}
    print("H",H,int(ok.sum()),"amostras",flush=True)
R=pd.read_pickle("cv_loso.pkl")
R["reg"]=np.where((R.h0>=280)|(R.p90>=300),"alto","normal")
E=np.maximum(R.p10-R.obs,R.obs-R.p90)
off={}
for (H,reg),e in E.groupby([R.H,R.reg]):
    off[f"{H}|{reg}"]=round(float(e.quantile(0.85 if reg=="alto" else 0.8)),1)
meta={"treinado_em":dt.datetime.now().isoformat(timespec="minutes"),"sklearn":sklearn.__version__,
      "features":feats,"horizontes":F.HORIZONTES,"quantis":Q,"offsets_cqr_cm":off,
      "temporadas":"out/2019–abr/2026 (meses out–abr)","regime_alto":"nível atual ≥280 cm ou P90 bruto ≥300 cm"}
pickle.dump(modelos,open("modelos/modelo_gv.pkl","wb"))
json.dump(meta,open("modelos/meta.json","w"),indent=1,ensure_ascii=False)
print(off)
