import json,time,urllib.request,pandas as pd
P={"piranga":(-20.42,-42.92),"piracicaba":(-19.72,-43.12),"santoantonio":(-19.05,-42.90),"docemedio":(-19.40,-42.45),"gv":(-18.88,-41.95)}
def get(u):
    for i in range(5):
        try: return json.loads(urllib.request.urlopen(u,timeout=120).read())
        except Exception as e: err=e; time.sleep(5*(i+1))
    raise err
obs={}
for k,(la,lo) in P.items():
    d=get(f"https://archive-api.open-meteo.com/v1/archive?latitude={la}&longitude={lo}&start_date=2019-09-25&end_date=2026-11-22&hourly=precipitation&timezone=America%2FSao_Paulo")
    obs[k]=pd.Series(d["hourly"]["precipitation"],index=pd.to_datetime(d["hourly"]["time"]))
pd.DataFrame(obs).to_csv("chuva_obs.csv.gz"); print("obs ok",len(obs["gv"]))
# previsões arquivadas por antecedência (dias), por temporada de teste
fc={}
for k,(la,lo) in P.items():
    if k=="gv": continue
    parts=[]
    for a,b in [("2024-09-25","2025-04-30"),("2025-09-25","2026-04-30"),("2026-09-25","2026-11-23")]:
        vars_=",".join(["precipitation"]+[f"precipitation_previous_day{i}" for i in range(1,6)])
        d=get(f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}&start_date={a}&end_date={b}&hourly={vars_}&timezone=America%2FSao_Paulo")
        parts.append(pd.DataFrame(d["hourly"]).set_index("time"))
    f=pd.concat(parts); f.index=pd.to_datetime(f.index)
    for c in f.columns: fc[(k,c)]=f[c]
F=pd.DataFrame(fc); F.columns=[f"{a}|{b}" for a,b in F.columns]
F.to_csv("chuva_prev_arquivo.csv.gz"); print("prev ok",F.shape, F.isna().mean().round(2).to_dict())
