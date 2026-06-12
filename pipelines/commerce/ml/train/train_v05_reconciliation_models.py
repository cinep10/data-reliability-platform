from __future__ import annotations
import argparse, json, os, urllib.parse
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import joblib

NUM_COLS = [
    'reconciliation_gap','orphan_ratio','duplicate_ratio','delivery_delay_ms','payment_state_gap','conversion_distortion',
    'transaction_without_state_ratio','behavior_only_ratio','transaction_only_ratio','coupon_reconciliation_gap',
    'semantic_base_score','overall_risk_score','predicted_severity_score','reconciliation_failure_probability','overall_ai_risk_score'
]
CAT_COLS = ['scenario_name','final_risk_level','dominant_semantic_risk','recommended_action','validation_status','ai_reliability_level']
LABEL_COL = 'final_risk_level'
TARGET_COL = 'overall_risk_score'

def parse_args():
    p=argparse.ArgumentParser(description='Train v0.5 reconciliation ML models from backfilled Phase5 feature dataset.')
    p.add_argument('--host', default=os.getenv('DB_HOST','127.0.0.1'))
    p.add_argument('--port', type=int, default=int(os.getenv('DB_PORT','3306')))
    p.add_argument('--user', default=os.getenv('DB_USER','nethru'))
    p.add_argument('--password', default=os.getenv('DB_PASSWORD', os.getenv('DB_PASS','nethru1234')))
    p.add_argument('--db', default=os.getenv('DB_NAME','weblog'))
    p.add_argument('--profile-id', required=True)
    p.add_argument('--dt-from', required=True)
    p.add_argument('--dt-to', required=True)
    p.add_argument('--view-name', default='vw_v05_phase5_ml_ai_feature_dataset')
    p.add_argument('--output-dir', default='artifacts/ml_v05')
    return p.parse_args()

def engine(args):
    pw=urllib.parse.quote_plus(args.password)
    return create_engine(f'mysql+pymysql://{args.user}:{pw}@{args.host}:{args.port}/{args.db}?charset=utf8mb4')

def normalize(df):
    for c in NUM_COLS:
        if c not in df.columns: df[c]=0.0
        df[c]=pd.to_numeric(df[c], errors='coerce')
    for c in CAT_COLS:
        if c not in df.columns: df[c]='none'
        df[c]=df[c].fillna('none').astype(str)
    if LABEL_COL not in df.columns: raise SystemExit(f'missing label column {LABEL_COL}')
    df[LABEL_COL]=df[LABEL_COL].fillna('unknown').astype(str)
    return df

def maybe_log_training_run(args, df, metrics, out, labels_count):
    try:
        eng = engine(args)
        payload = json.dumps(metrics, ensure_ascii=False)
        label_json = json.dumps(labels_count, ensure_ascii=False)
        with eng.begin() as con:
            con.execute(text('''CREATE TABLE IF NOT EXISTS v05_ml_training_run (
              training_run_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
              profile_id VARCHAR(128) NOT NULL, dt_from DATE NOT NULL, dt_to DATE NOT NULL, row_count INT NOT NULL DEFAULT 0,
              label_distribution_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(label_distribution_json)),
              classifier_path VARCHAR(1024) DEFAULT NULL, regressor_path VARCHAR(1024) DEFAULT NULL, report_path VARCHAR(1024) DEFAULT NULL,
              metrics_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(metrics_json)),
              training_status VARCHAR(64) NOT NULL DEFAULT 'unknown', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              KEY idx_v05_ml_training_scope(profile_id, dt_from, dt_to)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''))
            con.execute(text('''INSERT INTO v05_ml_training_run(profile_id,dt_from,dt_to,row_count,label_distribution_json,classifier_path,regressor_path,report_path,metrics_json,training_status)
              VALUES(:p,:a,:b,:n,:labels,:clf,:reg,:report,:metrics,:status)'''), {
              'p':args.profile_id,'a':args.dt_from,'b':args.dt_to,'n':int(len(df)),'labels':label_json,
              'clf':str(out/'v05_reconciliation_classifier.joblib'),'reg':str(out/'v05_reconciliation_score_regressor.joblib'),
              'report':str(out/'v05_classification_report.json'),'metrics':payload,'status':'PASS'
            })
    except Exception as e:
        print(f'[WARN] training registry insert skipped: {e}')

def main():
    args=parse_args()
    df=pd.read_sql(text(f"SELECT * FROM {args.view_name} WHERE profile_id=:p AND target_date BETWEEN :a AND :b ORDER BY target_date, run_id"), engine(args), params={'p':args.profile_id,'a':args.dt_from,'b':args.dt_to})
    if df.empty: raise SystemExit('training dataframe is empty')
    df=normalize(df)
    out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    X=df[NUM_COLS+CAT_COLS].copy(); y=df[LABEL_COL]
    pre=ColumnTransformer([
        ('num', Pipeline([('imputer', SimpleImputer(strategy='constant', fill_value=0.0))]), NUM_COLS),
        ('cat', Pipeline([('imputer', SimpleImputer(strategy='constant', fill_value='none')),('onehot', OneHotEncoder(handle_unknown='ignore'))]), CAT_COLS)
    ])
    clf=Pipeline([('pre',pre),('clf',RandomForestClassifier(n_estimators=300,max_depth=8,random_state=42,class_weight='balanced_subsample'))])
    stratify=y if y.nunique()>1 and y.value_counts().min()>=2 else None
    if len(df)>=10 and y.nunique()>1:
        Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=0.30,random_state=42,stratify=stratify)
    else:
        Xtr,Xte,ytr,yte=X,X,y,y
    clf.fit(Xtr,ytr); pred=clf.predict(Xte)
    labels=sorted(set(y.tolist())|set(pred.tolist()))
    report=classification_report(yte,pred,labels=labels,output_dict=True,zero_division=0)
    joblib.dump({'model':clf,'num_cols':NUM_COLS,'cat_cols':CAT_COLS,'label_col':LABEL_COL,'labels':labels,'model_version':'v05_reconciliation_classifier_interface'}, out/'v05_reconciliation_classifier.joblib')
    (out/'v05_classification_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    y_score=pd.to_numeric(df[TARGET_COL], errors='coerce').fillna(0.0)
    reg=Pipeline([('pre',pre),('reg',RandomForestRegressor(n_estimators=300,max_depth=8,random_state=42))])
    if len(df)>=10:
        Xtr,Xte,ytr,yte=train_test_split(X,y_score,test_size=0.30,random_state=42)
    else:
        Xtr,Xte,ytr,yte=X,X,y_score,y_score
    reg.fit(Xtr,ytr); sp=reg.predict(Xte)
    metrics={'rows':int(len(df)),'mae':float(mean_absolute_error(yte,sp)),'r2':float(r2_score(yte,sp)) if len(set(yte))>1 else None}
    joblib.dump({'model':reg,'num_cols':NUM_COLS,'cat_cols':CAT_COLS,'target_col':TARGET_COL,'model_version':'v05_reconciliation_score_regressor_interface'}, out/'v05_reconciliation_score_regressor.joblib')
    (out/'v05_regression_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    df[['profile_id','target_date','run_id','scenario_name','final_risk_level','overall_risk_score','predicted_risk_class']].to_csv(out/'v05_training_rows.csv',index=False)
    labels_count={str(k):int(v) for k,v in y.value_counts().to_dict().items()}
    maybe_log_training_run(args, df, metrics, out, labels_count)
    print(f'[OK] trained v0.5 reconciliation models rows={len(df)} labels={labels_count} output_dir={out}')
if __name__=='__main__': main()
