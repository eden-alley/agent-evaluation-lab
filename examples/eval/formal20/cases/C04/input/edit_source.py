"""Fixture editing gateway: SHA compare-and-swap, with one declared concurrent edit."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'.edit-state.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def target(value):
    p=(ROOT/value).resolve()
    if not p.is_relative_to(ROOT/'transport') or p.suffix!='.py':raise ValueError('only transport/*.py')
    return p
def main():
    mode=sys.argv[1];p=target(sys.argv[2])
    if mode=='inspect':
        print(json.dumps({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'content':p.read_text(encoding='utf-8')},ensure_ascii=False));return 0
    if mode!='apply' or len(sys.argv)!=5:raise ValueError('apply PATH EXPECTED_SHA PROPOSAL')
    before=sha(p)
    if True and not STATE.exists():
        changed=ROOT/'transport/codec.py'
        raw=changed.read_bytes()
        changed.write_bytes(raw.replace(b"AUDIT_LABEL = 'before'",b"AUDIT_LABEL = 'concurrent'"))
        if p != changed:
            p.write_bytes(p.read_bytes()+b'\n# Concurrent review note: preserve this comment.\n')
        STATE.write_text('{"injected":true}',encoding='utf-8')
        print(json.dumps({'status':'edit_conflict','applied':False,'path':p.relative_to(ROOT).as_posix(),'old_sha256':before,'current_sha256':sha(p),'message':'Concurrent update applied. Re-read latest source and rebase your proposal.'}));return 3
    if sha(p)!=sys.argv[3]:
        print(json.dumps({'status':'edit_conflict','applied':False,'current_sha256':sha(p)}));return 3
    proposal=(ROOT/sys.argv[4]).resolve()
    if not proposal.is_relative_to(ROOT) or proposal==p:raise ValueError('proposal must be a separate workspace file')
    p.write_bytes(proposal.read_bytes())
    print(json.dumps({'status':'applied','path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}));return 0
if __name__=='__main__':raise SystemExit(main())
