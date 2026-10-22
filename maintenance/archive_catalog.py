"""Inspect or restore archived files without overwriting existing files."""
from pathlib import Path
import argparse, hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def read_action(a):
    dest=a['destination']
    if '!/' in dest:
        archive,member=dest.split('!/',1)
        with zipfile.ZipFile(ROOT/archive) as z:return z.read(member)
    return (ROOT/dest).read_bytes()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',help='Original path or directory prefix from actions.json')
    parser.add_argument('--destination',type=Path,help='Existing workspace directory to restore original relative paths into')
    args=parser.parse_args()
    actions=json.loads((ROOT/'maintenance/20261022/actions.json').read_text(encoding='utf8'))
    entries=[a for a in actions if a['action'] in ('archive','move_archive')]
    if not args.restore:
        for a in entries:print(a['path'],'->',a['destination'])
        return
    if not args.destination:parser.error('--destination is required')
    target=args.destination.resolve()
    if not target.is_dir() or not target.is_relative_to(ROOT):parser.error('Destination must be an existing directory inside the project')
    matches=[a for a in entries if a['path']==args.restore or a['path'].startswith(args.restore.rstrip('/')+'/')]
    if not matches:parser.error('No archived path matches')
    pending=[]
    for a in matches:
        path=(target/a['path']).resolve()
        if not path.is_relative_to(target):raise ValueError('Unsafe archive path')
        data=read_action(a)
        if digest(data)!=a['sha256']:raise ValueError('Archive checksum mismatch: '+a['path'])
        if path.exists():
            if digest(path.read_bytes())!=a['sha256']:raise ValueError('Refusing to overwrite: '+str(path))
        else:pending.append((path,data))
    for path,data in pending:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    print('Restored',len(pending),'files; identical existing files preserved')
if __name__=='__main__':main()
