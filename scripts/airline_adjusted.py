# Airline ranking on equal terms: linear probability model with route fixed effects, departure-hour bands and month dummies,
# route-clustered standard errors. Run from the repo root: python scripts/airline_adjusted.py
import pandas as pd, numpy as np, glob, json
D='data/full_2025/'
cols=['MONTH','OP_UNIQUE_CARRIER','ORIGIN','DEST','CRS_DEP_TIME','ARR_DELAY','CANCELLED','DIVERTED']
df=pd.concat([pd.read_csv(f,usecols=cols,dtype={'OP_UNIQUE_CARRIER':'category','ORIGIN':'category','DEST':'category'}) for f in sorted(glob.glob(D+'*.csv'))],ignore_index=True)
c=df.CANCELLED==1; d=df.DIVERTED==1; fl=~c&~d&df.ARR_DELAY.notna()
df['y']=(c|d|(fl&(df.ARR_DELAY>=15))).astype('float32')
keep=df.OP_UNIQUE_CARRIER.value_counts(); keep=keep[keep>=50000].index
df=df[df.OP_UNIQUE_CARRIER.isin(keep)].copy()
df['car']=df.OP_UNIQUE_CARRIER.astype(str)
df['hour']=(df.CRS_DEP_TIME//100).clip(upper=23)
df['route']=(df.ORIGIN.astype(str)+'-'+df.DEST.astype(str)).astype('category').cat.codes
df=df[['y','car','hour','MONTH','route']]
cars=sorted(df.car.unique()); base='DL'
df['hb']=pd.cut(df.hour,[-1,9,13,16,19,23],labels=False)
X=pd.concat([pd.get_dummies(df.car,dtype='float32').drop(columns=base),
             pd.get_dummies(df.hb,prefix='h',dtype='float32').iloc[:,1:],
             pd.get_dummies(df.MONTH,prefix='m',dtype='float32').iloc[:,1:]],axis=1)
names=list(X.columns)
Xv=X.values; del X
y=df.y.values.astype('float64'); r=df.route.values.astype(np.int64)
import gc; gc.collect()
# absorb route fixed effects by within-route demeaning (exact for one FE, Frisch-Waugh)
n=np.bincount(r).astype(float)
def dm(v):
    m=np.bincount(r,weights=v)/n; return (v-m[r]).astype('float32')
yd=dm(y)
for j in range(Xv.shape[1]): Xv[:,j]=dm(Xv[:,j].astype('float64'))
Xd=Xv
XtX=(Xd.T.astype('float64')@Xd.astype('float64')); Xty=Xd.T.astype('float64')@yd.astype('float64'); beta=np.linalg.solve(XtX,Xty)
res=yd-Xd@beta
# cluster-robust SE by route
k=Xd.shape[1]; G=r.max()+1
S=np.column_stack([np.bincount(r,weights=Xd[:,j]*res,minlength=G) for j in range(k)])
inv=np.linalg.inv(XtX); V=inv@(S.T@S)@inv
b={c:0.0 for c in cars}; 
for i,nm in enumerate(names):
    if nm in b: b[nm]=beta[i]
share=df.car.value_counts(normalize=True)
ybar=y.mean(); wb=sum(share[c]*b[c] for c in cars)
raw=df.groupby('car').y.mean()*100
out=[{'car':c,'raw':raw[c],'adj':(ybar+b[c]-wb)*100,'n':int((df.car==c).sum())} for c in cars]
# pairwise test vs best adjusted
idx={nm:i for i,nm in enumerate(names)}
def var_diff(a,c):
    v=np.zeros(k)
    if a in idx: v[idx[a]]+=1
    if c in idx: v[idx[c]]-=1
    return v@V@v
o=sorted(out,key=lambda z:z['adj']); best=o[0]['car']
for z in o:
    if z['car']==best: z['p']=None; continue
    diff=b[z['car']]-b[best]; se=np.sqrt(var_diff(z['car'],best)); z['diff_pts']=diff*100; z['z']=diff/se
json.dump(o,open('results/airline_adjusted.json','w'),indent=1,default=float)
for z in o: print(z)
