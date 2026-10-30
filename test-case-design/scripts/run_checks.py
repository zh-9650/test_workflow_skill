#!/usr/bin/env python3
"""Run unchanged 10/09 Case Contract and 3.3 -> 1.1 branch case audit together."""
import argparse, json
from pathlib import Path
from case_contract import validate as validate_legacy
from branch_case_audit import audit, AuditError
from standalone_cases import make_cases, DeliveryError, materialize


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--points',required=True)
    p.add_argument('--business',required=True)
    p.add_argument('--ledger',help='3.3 effect-ledger.json; strongly recommended')
    p.add_argument('--candidate',action='store_true',help='allow partial design but never imply final sign-off')
    p.add_argument('--legacy-input',action='store_true',help='read older test points for migration only')
    p.add_argument('--full',help='full.md, verify already generated')
    p.add_argument('--cards',help='case_cards.md, verify already generated')
    p.add_argument('--smoke',help='smoke.md, verify already generated')
    p.add_argument('--smoke-ids',help='JSON list of smoke standalone case IDs')
    p.add_argument('--standalone-json',help='完整独立用例机器交接正本，核对后交数据准备/执行')
    a=p.parse_args()
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    try:
        cases,points,business=map(read,(a.input,a.points,a.business))
        legacy=validate_legacy(cases,points,business,require_confirmed=not a.candidate)
        branch=audit(cases,points,read(a.ledger) if a.ledger else None,candidate=a.candidate,legacy=a.legacy_input)
        standalone=make_cases(cases,candidate=a.candidate or a.legacy_input)
        if not (a.candidate or a.legacy_input) and not all((a.full,a.cards,a.smoke,a.smoke_ids,a.standalone_json)):
            raise DeliveryError('正式门禁必须提交 --full --cards --smoke --smoke-ids --standalone-json')
        if any((a.full,a.cards,a.smoke,a.smoke_ids,a.standalone_json)):
            if not all((a.full,a.cards,a.smoke,a.smoke_ids,a.standalone_json)):raise DeliveryError('文档路径必须四项齐全')
            ids=read(a.smoke_ids)
            _,expected_full,expected_cards,expected_smoke,expected_json=materialize(cases,ids,candidate=a.candidate or a.legacy_input)
            for path,expected in ((a.full,expected_full),(a.cards,expected_cards),(a.smoke,expected_smoke),(a.standalone_json,expected_json)):
                if not Path(path).exists() or Path(path).read_text(encoding='utf-8')!=expected:
                    raise DeliveryError(f'文档缺少/与实际完整用例不同步: {path}')
        ready=bool(legacy.get('ready_for_confirmation')) and bool(branch.get('ready_for_handoff')) and bool(standalone) and all((a.full,a.cards,a.smoke,a.smoke_ids,a.standalone_json))
        print(json.dumps({'ok':True,'legacy_contract':legacy,'branch_audit':branch,'standalone_cases':len(standalone),
                          'ready_for_review':ready,
                          'formal_business_signoff':False,
                          'note':'仅结构/承接门禁；仍需源证据语义复核与实际数据准备、执行验证'},ensure_ascii=False,indent=2))
        if not ready and not (a.candidate or a.legacy_input):raise SystemExit(1)
    except (AssertionError,AuditError,DeliveryError,ValueError,KeyError,TypeError) as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False,indent=2))
        raise SystemExit(1)

if __name__=='__main__':main()
