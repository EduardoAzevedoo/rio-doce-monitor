import pandas as pd, numpy as np, sys
R=pd.read_pickle(sys.argv[1] if len(sys.argv)>1 else "cv_loso.pkl")
def m(g):
    e=(g.p50-g.obs).abs(); ep=(g.h0-g.obs).abs()
    cov=((g.obs>=g.p10)&(g.obs<=g.p90)).mean()
    return pd.Series({"n":len(g),"MAE":e.mean(),"MAE_pers":ep.mean(),"P90err":e.quantile(.9),"cobert80":cov,"larg":(g.p90-g.p10).mean()})
print("== Todas as horas"); print(R.groupby("H").apply(m).round(1).to_string())
alto=R[(R.obs>=300)|(R.h0>=300)]
print("\n== Água alta (obs ou atual ≥300 cm)"); print(alto.groupby("H").apply(m).round(1).to_string())
# detecção de cruzar 341 (rua) e 360
for lim in (341,360):
    print(f"\n== Prever nível ≥{lim} no horizonte (eventos novos: atual <{lim})")
    rows=[]
    for H,g in R.groupby("H"):
        g=g[g.h0<lim]
        ev=g.obs>=lim
        for nome,col in [("P50",g.p50),("P90",g.p90)]:
            al=col>=lim
            pod=(al&ev).sum()/max(ev.sum(),1); far=(al&~ev).sum()/max(al.sum(),1)
            rows.append((H,nome,int(ev.sum()),round(pod,2),round(far,2)))
    print(pd.DataFrame(rows,columns=["H","gatilho","casos","acerto(POD)","alarme_falso(FAR)"]).pivot(index="H",columns="gatilho",values=["casos","acerto(POD)","alarme_falso(FAR)"]).to_string())
