"""Local-only audit of tracked content and pack size; never publishes or deletes files."""
from pathlib import Path
import hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'maintenance/git_push_cleanup_local'
OUT.mkdir(exist_ok=True)

def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], cwd=ROOT, **kwargs)

def measure(ref):
    rows = git('diff', '--name-only', '-z', 'origin/main', ref).split(b'\0')
    files = [p.decode('utf8') for p in rows if p]
    objects = git('rev-list', '--objects', ref, '^origin/main').splitlines()
    sizes = git('cat-file', '--batch-check=%(objecttype) %(objectsize)', input=b'\n'.join(r.split(b' ')[0] for r in objects)+b'\n').splitlines()
    pack = git('pack-objects', '--stdout', '--revs', input=f'{ref}\n^origin/main\n'.encode())
    return dict(changed_files=len(files), new_objects=len(objects),
                uncompressed_object_bytes=sum(int(r.split()[1]) for r in sizes),
                estimated_pack_bytes=len(pack))

if sys.argv[1] == 'before':
    assert git('rev-parse', 'HEAD').decode().startswith('d5124fd')
    files = [p.decode('utf8') for p in git('ls-files', '-z').split(b'\0') if p]
    hashes = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files if (ROOT/p).is_file()}
    (OUT/'before_hashes.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding='utf8')
    ignored = subprocess.run(['git','check-ignore','--no-index','--stdin','-z'],cwd=ROOT,input=b'\0'.join(p.encode() for p in files)+b'\0',capture_output=True,check=False)
    assert ignored.returncode in (0,1), ignored.stderr
    remove = [p.decode('utf8') for p in ignored.stdout.split(b'\0') if p]
    (OUT/'untrack_paths.txt').write_bytes(b'\0'.join(p.encode() for p in remove)+b'\0')
    (OUT/'untrack.json').write_text(json.dumps(remove,ensure_ascii=False,indent=2),encoding='utf8')
    report = dict(commit=git('rev-parse','HEAD').decode().strip(), **measure('HEAD'),
                  untrack_files=len(remove), untrack_bytes=sum((ROOT/p).stat().st_size for p in remove))
    (OUT/'before.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
else:
    original=json.loads((OUT/'before_hashes.json').read_text(encoding='utf8'))
    changed=[p for p,h in original.items() if p not in ('.gitignore','test_maintenance.py') and (not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h)]
    report=dict(**measure('HEAD'),unexpected_file_changes=changed,
                all_untracked_files_retained=all((ROOT/p).is_file() for p in json.loads((OUT/'untrack.json').read_text(encoding='utf8'))))
    (OUT/'after.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
    assert not changed and report['all_untracked_files_retained']
    before=json.loads((OUT/'before.json').read_text(encoding='utf8'))
    tests=json.loads((OUT/'checkout_verified/maintenance/20261022/test_results/summary.json').read_text(encoding='utf8'))
    assert len(tests)==32 and all(t['exit_code']==0 for t in tests)
    (OUT/'test_summary.json').write_text(json.dumps(tests,indent=2),encoding='utf8')
    commit=git('rev-parse','--short','HEAD').decode().strip()
    mb=lambda n:f'{n/1_000_000:.2f}'
    saved=(1-report['estimated_pack_bytes']/before['estimated_pack_bytes'])*100
    text=f'''# Git 推送范围精简验收

原提交：`d5124fd`；替换提交：`{commit}`。父提交仍为已发布的 `f8f6245`。
远端通过只读 SSH 查询核对，未执行 push、force push 或改写已发布历史。

| 指标 | 精简前 | 精简后 |
| --- | ---: | ---: |
| 相对 origin/main 的变更文件数 | {before['changed_files']} | {report['changed_files']} |
| 新增 Git 对象未压缩体积（MB） | {mb(before['uncompressed_object_bytes'])} | {mb(report['uncompressed_object_bytes'])} |
| 估算待发送 Git pack（MB） | {mb(before['estimated_pack_bytes'])} | {mb(report['estimated_pack_bytes'])} |

估算压缩包减少 {saved:.1f}%。通过本地 `git pack-objects --stdout --revs`、排除
origin/main 已有历史测量；实际网络发送量还受远端已有对象、协商及传输协议影响。

## 追踪范围

- 取消追踪 {before['untrack_files']} 个原已追踪本地产物，约 {mb(before['untrack_bytes'])} MB。
  包括截图、日志、ZIP、浏览器下载、重复预览、旧 V1/V2 可再生 out_* 输出。
  完整清单见 untrack.json，所有本地文件仍存在且原始内容未改。
- 保留源码、完整 docs、图标、账本和回测引擎、研究原始/清洗数据及必要测试。
- 修正旧规则对所有 results/data_cache 目录一概忽略的问题，补齐研究打包、独立复核
  和离线测试依赖。因此新增了一批此前漏提交的必要数据，而非只追求文件数下降。
- 保留当前及回归测试使用的旧版 workspace_data；保留研究 daily/trades、汇总与元数据。
  无读取依赖的 *_signals.csv 不上传，可由对应 reaccept.py 再生成，原本地输出不变。
- .gitattributes 使按 SHA256 审计的历史快照保持原始字节，避免 Windows CRLF
  转换破坏校验。网站源码、正式页面及原研究数据本地内容均未修改。
- 归档测试仅在本地 ZIP/截图存在时校验；干净副本明确跳过这些非分发证据，
  其余数据仍强制存在并校验。本机带完整资料的归档及离线导出测试另行通过。

## 验收

只从暂存索引检出干净副本，未借用原工作目录的未追踪资料：32 组全通过，
包括 187 项 Python 测试、账本与预算、实际基金、历史黄金、375/320px、四页和 PWA。
完整摘要见 test_summary.json。检出校验过程中发现并修复旧规则漏数据及换行符问题，
解决后才允许重做提交。

本地恢复包 before-d5124fd.bundle 已通过 git bundle verify；包含旧提交，以 f8f6245
为前置历史。未创建会被普通推送附带上传的大文件备份分支；旧提交亦留在本地 reflog。
本目录所有恢复与验收文件均被忽略，不进入待推送提交。

另观察到本机 SSH 代理命令使用 exec，而 PowerShell 不识别它。临时使用 Git 自带
sh/ssh 后只读远端核对成功；本次没有修改全局 SSH 配置，也未实际测试推送。
'''
    (OUT/'REPORT.md').write_text(text,encoding='utf8')
