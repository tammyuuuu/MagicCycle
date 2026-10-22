"""Complete local test entry; no refresh, publication or Git operations."""
from pathlib import Path
import argparse, json, os, subprocess, sys, time
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'maintenance/20261022/test_results'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',action='store_true',help='Verify current four-page UI at desktop/375px/320px and PWA')
    parser.add_argument("--group", action="append", help="Run only named groups; repeatable")
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    temporary=OUT/"tmp";temporary.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONWARNINGS':'ignore::DeprecationWarning','TEMP':str(temporary),'TMP':str(temporary)}
    commands=[('python_all',[sys.executable,'-B','-m','unittest','discover','-s','.','-p','test_*.py','-v'],ROOT)]
    commands += [(p.stem,[sys.executable,'-B',p.name],p.parent) for p in sorted((ROOT/'research_xingxun_v1').glob('test_*.py'))]
    commands += [(p.stem,['node',p.name],ROOT) for p in sorted(ROOT.glob('test_*.js'))]
    commands += [('protected_boundaries',[sys.executable,'-B','correctness_20261022/check_boundaries.py'],ROOT)]
    if args.browser:
        commands += [(p,['node','ui_optimization/'+p+'.js'],ROOT) for p in ['browser_etf_groups','browser_monitor_tabs','browser_compact_plan','browser_compact_review','browser_compact_lab','browser_pending_transactions','browser_executed_buy','browser_historical_gold','browser_account_cash']]
        commands += [('browser_asset_products',['node','product_mapping_audit/browser_products.js'],ROOT),('browser_budget',['node','ui_optimization/browser_budget.js'],ROOT)]
        commands += [('pwa',['node','maintenance/20261022/test_pwa.js'],ROOT)]
    if args.group:
        available={c[0] for c in commands}
        if set(args.group)-available:parser.error("Unknown test group")
        commands=[c for c in commands if c[0] in args.group]
    results=[]
    for name,cmd,cwd in commands:
        started=time.monotonic();run=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf8',errors='replace')
        (OUT/(name+'.log')).write_text(run.stdout+run.stderr,encoding='utf8')
        results.append({'name':name,'command':cmd,'exit_code':run.returncode,'seconds':round(time.monotonic()-started,2)})
        (OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        print(('PASS' if run.returncode==0 else 'FAIL'),name,flush=True)
        if run.returncode:
            print((run.stdout+run.stderr)[-6500:]);return 1
    print('ALL PASSED:',len(results),'groups',flush=True);return 0
if __name__=='__main__':sys.exit(main())
