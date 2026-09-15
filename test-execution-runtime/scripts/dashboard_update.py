import json, os
from pathlib import Path
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat()
def read(path,default=None):
    p=Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else ({} if default is None else default)
def write(path,v):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,p)

def _recording_required(case):
    r=(case.get('evidence_plan') or {}).get('recording')
    return isinstance(r,dict) and r.get('required') is True

def _normalize_core_flows(plan):
    configured=plan.get('core_flows',[])
    if configured and all(isinstance(x,dict) for x in configured):
        return [dict(x,status=x.get('status','pending')) for x in configured]
    groups={}
    for c in plan.get('cases',[]):
        fid=c.get('core_flow_id')
        if fid or c.get('core_flow'):
            fid=fid or 'CORE'; g=groups.setdefault(fid,{'id':fid,'name':c.get('core_flow_name') or fid,'case_ids':[]})
            g['case_ids'].append(c['case_id'])
    return list(groups.values())

def init_dashboard(plan=None):
    plan=plan or {}; batches=[]; cases=[]; recordings={}
    for b in plan.get('batches',[]):
        batches.append({'id':b['id'],'name':b.get('name',b.get('goal','')),'status':'pending','done':0,'total':len(b.get('case_ids',[]))})
    for c in plan.get('cases',[]):
        cases.append({'id':c['case_id'],'status':'PENDING','batch_id':c.get('batch_id'),'planned_execution':c.get('primary_execution'),'actual_execution':None,'core_flow_id':c.get('core_flow_id') or ('CORE' if c.get('core_flow') else None)})
        rec=(c.get('evidence_plan') or {}).get('recording')
        if isinstance(rec,dict) and rec.get('required') is True:
            scope=rec.get('scope','case')
            ref=c.get('batch_id') if scope=='batch' else c['case_id']
            row=recordings.setdefault(ref,{'status':'pending','scope':scope,'source_case_ids':[]})
            if c['case_id'] not in row['source_case_ids']: row['source_case_ids'].append(c['case_id'])
    for b in plan.get('batches',[]):
        rec=b.get('recording')
        if isinstance(rec,dict) and rec.get('required') is True:
            row=recordings.setdefault(b['id'],{'status':'pending','scope':'batch','source_case_ids':[]})
            row['scope']='batch'
    d={'current_stage':'execution-runtime','current_batch':None,'current_case':None,'current_worker':None,'current_reviewer':None,'current_action':'pending','cases':cases,'batches':batches,'core_flows':_normalize_core_flows(plan),'defects':[],'reviewer_status':{},'recordings':recordings,'recent':[],'blocked_reason_stats':{},'metrics':{},'last_updated':now()}
    return recompute(d)

def recompute(d):
    cases=d.get('cases',[]); finals={'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}
    metrics={'total_cases':len(cases),'completed_cases':sum(1 for c in cases if c.get('status') in finals),'total_batches':len(d.get('batches',[])),'completed_batches':sum(1 for b in d.get('batches',[]) if b.get('status')=='completed')}
    for s in ['PASS','FAIL','BLOCKED','NEEDS_REVIEW','RUNNING','PENDING','PASS_AFTER_FIX']:
        metrics[s]=sum(1 for c in cases if c.get('status')==s)
    metrics['planned_execution']={k:sum(1 for c in cases if c.get('planned_execution')==k) for k in ['UI','API','人工']}
    metrics['actual_execution']={k:sum(1 for c in cases if c.get('actual_execution')==k and c.get('status') in finals) for k in ['UI','API','人工']}
    d['metrics']=metrics
    br={}
    for c in cases:
        if c.get('status')=='BLOCKED': br[c.get('blocked_reason_type','unknown')]=br.get(c.get('blocked_reason_type','unknown'),0)+1
    d['blocked_reason_stats']=br
    for b in d.get('batches',[]):
        rows=[c for c in cases if c.get('batch_id')==b['id']]
        b['done']=sum(1 for c in rows if c.get('status') not in {'PENDING','RUNNING',None})
        b['total']=len(rows) if rows else b.get('total',0)
    for f in d.get('core_flows',[]):
        ids=set(f.get('case_ids',[])); rows=[c for c in cases if c.get('id') in ids]
        f['done']=sum(1 for c in rows if c.get('status') in finals); f['total']=len(ids)
        f['status']='completed' if f['total'] and f['done']==f['total'] else ('running' if f['done'] else 'pending')
    d['last_updated']=now(); return d

def upsert_case(d,cid,**fields):
    row=next((c for c in d['cases'] if c.get('id')==cid),None)
    if row is None: raise AssertionError(f'case_id: {cid} was not initialized from execution plan')
    row.update(fields)
def update_batch(d,bid,**fields):
    row=next((b for b in d['batches'] if b.get('id')==bid),None)
    if row is None: raise AssertionError(f'batch_id: {bid} was not initialized from execution plan')
    row.update(fields)

def apply_event(d,event):
    typ=event.get('type'); bid=event.get('batch_id'); cid=event.get('case_id'); worker=event.get('worker_id')
    d['current_action']=event.get('current_action') or typ
    if event.get('stage'): d['current_stage']=event['stage']
    if worker is not None: d['current_worker']=worker
    if typ=='batch_started': d['current_batch']=bid; d['current_case']=None; update_batch(d,bid,status='running')
    elif typ=='case_started': d['current_batch']=bid; d['current_case']=cid; upsert_case(d,cid,status='RUNNING',batch_id=bid)
    elif typ=='case_finished':
        upsert_case(d,cid,status=event['status'],batch_id=bid,blocked_reason_type=event.get('blocked_reason_type'),actual_execution=event.get('actual_execution'))
        if d.get('current_case')==cid: d['current_case']=None
    elif typ=='case_blocked':
        upsert_case(d,cid,status='BLOCKED',batch_id=bid,blocked_reason_type=event.get('blocked_reason_type'),actual_execution=event.get('actual_execution'))
        if d.get('current_case')==cid: d['current_case']=None
    elif typ=='review_started':
        d['current_case']=None; d['current_worker']=None; d['current_reviewer']=event.get('reviewer_id'); d['reviewer_status'][bid]={'status':'reviewing','reviewer':event.get('reviewer_id')}
    elif typ=='review_finished':
        reviewer_id=event.get('reviewer_id'); d['reviewer_status'][bid]={'status':event.get('status'),'reviewer':reviewer_id,'retest_case_ids':event.get('retest_case_ids',[])}
        d['current_case']=None; d['current_worker']=None; d['current_reviewer']=None
        if event.get('status')=='passed': update_batch(d,bid,status='completed')
        elif event.get('status')=='rework_required': update_batch(d,bid,status='needs_rework')
    elif typ=='batch_completed':
        update_batch(d,bid,status='completed'); d['current_case']=None; d['current_worker']=None; d['current_reviewer']=None
    elif typ=='bug_submitted':
        ref=event.get('bug_ref')
        if not any(x.get('id')==ref for x in d['defects']): d['defects'].append({'id':ref,'case_ids':event.get('case_ids',[]),'status':'submitted'})
        if bid: update_batch(d,bid,status='waiting_bug_fix')
    elif typ=='bug_fixed_pending_regression':
        for b in d['defects']:
            if b.get('id')==event.get('bug_ref'): b['status']='pending_regression'
    elif typ=='regression_finished':
        for b in d['defects']:
            if b.get('id')==event.get('bug_ref'): b['status']='regression_'+str(event.get('status','')).lower()
        if event.get('status')=='PASS':
            for ucid in event.get('unblocked_case_ids',[]):
                upsert_case(d,ucid,status='PENDING',blocked_reason_type=None)
            source_batches=set(event.get('source_batch_ids',[]))
            source_batches.update(c.get('batch_id') for c in d.get('cases',[]) if c.get('id') in set(event.get('unblocked_case_ids',[])))
            for sbid in [x for x in source_batches if x]:
                rows=[c for c in d.get('cases',[]) if c.get('batch_id')==sbid]
                if any(c.get('status') in {'PENDING','RUNNING','NEEDS_REVIEW'} for c in rows): update_batch(d,sbid,status='needs_rework')
                elif rows and all(c.get('status') in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'} for c in rows): update_batch(d,sbid,status='completed')
    elif typ=='recording_updated':
        scope=event.get('scope')
        if scope is None:
            if event.get('scope_ref') in d['recordings']: scope=d['recordings'][event.get('scope_ref')].get('scope')
            elif bid in d['recordings'] and d['recordings'][bid].get('scope')=='batch': scope='batch'
            else: scope='case'
        ref=event.get('scope_ref') or (bid if scope=='batch' else cid)
        if not ref: raise AssertionError('recording_updated: scope_ref or matching batch_id/case_id required')
        if ref not in d['recordings']: d['recordings'][ref]={'scope':scope,'source_case_ids':[]}
        if isinstance(d['recordings'][ref],str): d['recordings'][ref]={'status':d['recordings'][ref],'scope':scope,'source_case_ids':[]}
        d['recordings'][ref]['scope']=scope; d['recordings'][ref]['status']=event.get('status')
    elif typ=='run_paused': d['current_stage']='paused'
    else: raise AssertionError(f'event.type: unsupported {typ}')
    d['recent'].insert(0,{'type':typ,'batch_id':bid,'case_id':cid,'at':now()}); return recompute(d)

def _dependency_maps(plan):
    batch_ids=[b['id'] for b in plan.get('batches',[])]; case_to_batch={c['case_id']:c.get('batch_id') for c in plan.get('cases',[])}
    batch_deps={bid:[] for bid in batch_ids}; case_deps={bid:[] for bid in batch_ids}
    for c in plan.get('cases',[]):
        bid=c.get('batch_id')
        for dep in c.get('dependencies',[]) or []:
            ub=case_to_batch.get(dep)
            if ub and ub!=bid:
                if ub not in batch_deps.setdefault(bid,[]): batch_deps[bid].append(ub)
                if dep not in case_deps.setdefault(bid,[]): case_deps[bid].append(dep)
    return batch_deps,case_deps

def initialize_runtime_files(run_status_path,dashboard_path,plan):
    d=init_dashboard(plan); s=read(run_status_path,{})
    batch_ids=[b['id'] for b in plan.get('batches',[])]
    batch_deps,case_deps=_dependency_maps(plan)
    s.update(current_stage='execution-runtime',current_batch=None,current_case=None,current_worker=None,current_reviewer=None,
             batch_status={bid:'pending' for bid in batch_ids},batch_order=batch_ids,batch_dependencies=batch_deps,batch_dependency_cases=case_deps,case_status={c['case_id']:'PENDING' for c in plan.get('cases',[])},open_defects=[],blocked_items=[],pending_resume_batches=[],
             last_event={'type':'runtime_initialized','at':d['last_updated']},current_action={'type':'pending'},
             next_action=({'type':'prepare_batch_data','batch_id':batch_ids[0]} if batch_ids else {'type':'result_review'}),updated_at=d['last_updated'])
    write(run_status_path,s); write(dashboard_path,d); return {'run_status':s,'dashboard':d}

def _select_runnable_batch(s):
    statuses=s.get('batch_status',{}); dep_cases=s.get('batch_dependency_cases',{}); case_status=s.get('case_status',{})
    for bid in s.get('batch_order',list(statuses)):
        if statuses.get(bid)!='pending': continue
        if all(case_status.get(cid) in {'PASS','PASS_AFTER_FIX'} for cid in dep_cases.get(bid,[])): return bid
    return None

def _resume_action(s):
    queue=s.get('pending_resume_batches',[])
    if not queue: return None
    item=queue[0]
    return {'type':'prepare_resumed_cases_data','batch_id':item['batch_id'],'case_ids':list(item.get('case_ids',[])),'bug_ref':item.get('bug_ref')}

def _queue_unblocked_cases(s,d,event):
    ids=[x for x in event.get('unblocked_case_ids',[]) if x]
    if not ids: return
    case_batch={c.get('id'):c.get('batch_id') for c in d.get('cases',[])}
    grouped={}
    for cid in ids:
        bid=case_batch.get(cid)
        if not bid: raise AssertionError(f'unblocked case {cid} has no planned batch')
        grouped.setdefault(bid,[]).append(cid)
    queue=s.setdefault('pending_resume_batches',[])
    by_batch={x.get('batch_id'):x for x in queue}
    order=s.get('batch_order',[])
    for bid in sorted(grouped,key=lambda x: order.index(x) if x in order else len(order)):
        item=by_batch.get(bid)
        if item is None:
            item={'batch_id':bid,'case_ids':[],'bug_ref':event.get('bug_ref')}; queue.append(item); by_batch[bid]=item
        for cid in grouped[bid]:
            if cid not in item['case_ids']: item['case_ids'].append(cid)
        if not item.get('bug_ref'): item['bug_ref']=event.get('bug_ref')

def _finish_resume_batch(s,batch_id):
    queue=s.get('pending_resume_batches',[])
    if any(x.get('batch_id')==batch_id for x in queue):
        s['pending_resume_batches']=[x for x in queue if x.get('batch_id')!=batch_id]
        if isinstance(s.get('pending_resume'),dict) and s['pending_resume'].get('batch_id')==batch_id:
            s['pending_resume']=None
        return True
    return False

def _unhandled_fail_cases(s,d):
    covered=set()
    for df in d.get('defects',[]):
        for cid in df.get('case_ids',[]):
            covered.add(cid)
    out=[]
    for c in d.get('cases',[]):
        if c.get('status')=='FAIL' and c.get('id') not in covered:
            out.append(c)
    return out

def _next_action(event):
    typ=event.get('type'); bid=event.get('batch_id'); cid=event.get('case_id')
    if typ=='batch_started': return {'type':'execute_case','batch_id':bid}
    if typ=='case_started': return {'type':'execute_case','batch_id':bid,'case_id':cid}
    if typ in {'case_finished','case_blocked'}: return {'type':'continue_batch','batch_id':bid}
    if typ=='review_started': return {'type':'review_batch','batch_id':bid}
    if typ=='review_finished':
        if event.get('status')=='rework_required': return {'type':'execute_retest','batch_id':bid,'case_ids':event.get('retest_case_ids',[])}
        if event.get('status')=='return_upstream': return {'type':'return_upstream','stage':event.get('return_stage')}
        if event.get('unhandled_fail_case_ids'):
            return {'type':'handle_defects','batch_id':bid,'case_ids':event.get('unhandled_fail_case_ids',[])}
        return {'type':'execute_next_batch'}
    if typ=='batch_completed': return {'type':'execute_next_batch'}
    if typ=='bug_submitted': return {'type':'wait_bug_fix','bug_ref':event.get('bug_ref')}
    if typ=='bug_fixed_pending_regression': return {'type':'execute_regression','bug_ref':event.get('bug_ref')}
    if typ=='regression_finished': return {'type':'resume_blocked_cases' if event.get('status')=='PASS' else 'review_regression_failure','bug_ref':event.get('bug_ref')}
    if typ=='run_paused': return {'type':'resume_run'}
    if typ=='recording_updated': return {'type':'continue_current_work'}
    return {'type':'continue_current_work'}

def apply_event_files(run_status_path,dashboard_path,event):
    s=read(run_status_path,{}); d=read(dashboard_path,None)
    if not d: raise AssertionError('dashboard-data.json must be initialized from execution plan before runtime events')
    event=dict(event); typ=event.get('type'); bid=event.get('batch_id'); cid=event.get('case_id')
    state_stage=s.get('current_stage','execution-runtime')
    event_stage=event.get('stage')
    if event_stage and event_stage!=state_stage:
        raise AssertionError(f'dashboard event cannot change Router stage {state_stage} -> {event_stage}')
    if typ in {'bug_submitted','bug_fixed_pending_regression','regression_finished'} and state_stage!='defect-handling':
        raise AssertionError(f'{typ} requires Router stage defect-handling, current stage is {state_stage}')
    target_stage=state_stage
    d['current_stage']=target_stage
    if typ=='regression_finished' and event.get('status')=='PASS':
        ref=event.get('bug_ref')
        event.setdefault('unblocked_case_ids',[x.get('case_id') for x in s.get('blocked_items',[]) if x.get('reason')==ref and x.get('case_id')])
    d=apply_event(d,event)
    s['current_stage']=target_stage; d['current_stage']=target_stage
    s['current_batch']=d.get('current_batch'); s['current_case']=d.get('current_case'); s['current_worker']=d.get('current_worker'); s['current_reviewer']=d.get('current_reviewer')
    s['last_event']={'type':typ,'batch_id':bid,'case_id':cid,'at':d['last_updated']}; s['current_action']={'type':d.get('current_action')}; s['next_action']=_next_action(event); s['updated_at']=d['last_updated']

    if typ=='bug_submitted':
        ref=event.get('bug_ref'); od=s.setdefault('open_defects',[])
        if ref and ref not in od: od.append(ref)
        for blocked_cid in event.get('blocked_case_ids',[]):
            item={'case_id':blocked_cid,'reason':ref}
            if item not in s.setdefault('blocked_items',[]): s['blocked_items'].append(item)
    elif typ=='regression_finished' and event.get('status')=='PASS':
        ref=event.get('bug_ref'); unblocked=set(event.get('unblocked_case_ids',[]))
        s['open_defects']=[x for x in s.get('open_defects',[]) if x!=ref]
        s['blocked_items']=[x for x in s.get('blocked_items',[]) if x.get('reason')!=ref]
        for ucid in unblocked: s.setdefault('case_status',{})[ucid]='PENDING'
    if typ in {'case_finished','case_blocked'} and cid:
        s.setdefault('case_status',{})[cid]=('BLOCKED' if typ=='case_blocked' else event.get('status'))
    if typ=='case_blocked' or (typ=='case_finished' and event.get('status')=='BLOCKED'):
        item={'case_id':cid,'reason':event.get('bug_ref') or event.get('blocked_reason') or event.get('blocked_reason_type')}
        if item not in s.setdefault('blocked_items',[]): s['blocked_items'].append(item)

    # Dashboard is the projection of current Case/Batch facts; mirror those statuses into run-status.
    s['batch_status']={b.get('id'):b.get('status') for b in d.get('batches',[]) if b.get('id')}
    s['case_status']={c.get('id'):c.get('status') for c in d.get('cases',[]) if c.get('id')}
    if typ=='batch_started' and bid: s.setdefault('batch_data_status',{})[bid]='in_use'
    if typ=='review_finished' and event.get('status')=='passed' and bid: s.setdefault('batch_data_status',{})[bid]='consumed'

    unhandled_fails=_unhandled_fail_cases(s,d)

    if typ=='regression_finished' and event.get('status')=='PASS':
        unblocked=event.get('unblocked_case_ids',[])
        if unblocked:
            _queue_unblocked_cases(s,d,event)
            s['next_action']=_resume_action(s)
        elif unhandled_fails:
            fail_bid=unhandled_fails[0].get('batch_id')
            fail_cids=[c['id'] for c in unhandled_fails if c.get('batch_id')==fail_bid]
            s['next_action']={'type':'handle_defects','batch_id':fail_bid,'case_ids':fail_cids}
        else:
            nxt=_select_runnable_batch(s)
            if nxt: s['next_action']={'type':'prepare_batch_data','batch_id':nxt}
            elif s.get('open_defects'): s['next_action']={'type':'wait_bug_fix','bug_ref':s['open_defects'][0]}
            else: s['next_action']={'type':'result_review'}
    elif typ=='review_finished' and event.get('status')=='passed':
        resumed_batch=_finish_resume_batch(s,bid)
        if unhandled_fails or event.get('unhandled_fail_case_ids'):
            fail_cids=event.get('unhandled_fail_case_ids') or [c['id'] for c in unhandled_fails if c.get('batch_id')==bid] or [c['id'] for c in unhandled_fails]
            fail_bid=bid or (unhandled_fails[0].get('batch_id') if unhandled_fails else None)
            s['next_action']={'type':'handle_defects','batch_id':fail_bid,'case_ids':fail_cids}
        elif resumed_batch:
            resume=_resume_action(s)
            if resume: s['next_action']=resume
            else:
                nxt=_select_runnable_batch(s)
                if nxt: s['next_action']={'type':'prepare_batch_data','batch_id':nxt}
                elif s.get('open_defects'): s['next_action']={'type':'wait_bug_fix','bug_ref':s['open_defects'][0]}
                else: s['next_action']={'type':'result_review'}
        else:
            nxt=_select_runnable_batch(s)
            if nxt: s['next_action']={'type':'prepare_batch_data','batch_id':nxt}
            elif s.get('open_defects'): s['next_action']={'type':'wait_bug_fix','bug_ref':s['open_defects'][0]}
            else: s['next_action']={'type':'result_review'}
    elif s.get('next_action',{}).get('type') in {'execute_next_batch','continue_current_work'} or typ=='bug_submitted':
        if unhandled_fails and typ!='bug_submitted':
            fail_bid=unhandled_fails[0].get('batch_id')
            fail_cids=[c['id'] for c in unhandled_fails if c.get('batch_id')==fail_bid]
            s['next_action']={'type':'handle_defects','batch_id':fail_bid,'case_ids':fail_cids}
        else:
            nxt=_select_runnable_batch(s)
            if nxt: s['next_action']={'type':'prepare_batch_data','batch_id':nxt}
            elif s.get('open_defects'): s['next_action']={'type':'wait_bug_fix','bug_ref':s['open_defects'][0]}
            elif unhandled_fails:
                fail_bid=unhandled_fails[0].get('batch_id')
                fail_cids=[c['id'] for c in unhandled_fails if c.get('batch_id')==fail_bid]
                s['next_action']={'type':'handle_defects','batch_id':fail_bid,'case_ids':fail_cids}
            else: s['next_action']={'type':'result_review'}
    write(run_status_path,s); write(dashboard_path,d); return {'run_status':s,'dashboard':d}



if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser(description='Initialize or update the run dashboard from canonical execution events.')
    sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('init'); p.add_argument('--run-dir',required=True); p.add_argument('--plan',required=True)
    p=sp.add_parser('event'); p.add_argument('--run-dir',required=True); p.add_argument('--event',required=True,help='JSON event file')
    x=a.parse_args(); base=Path(x.run_dir); state=base/'internal/state/run-status.json'; data=base/'dashboard/dashboard-data.json'
    if x.cmd=='init': out=initialize_runtime_files(state,data,json.loads(Path(x.plan).read_text(encoding='utf-8')))
    else: out=apply_event_files(state,data,json.loads(Path(x.event).read_text(encoding='utf-8')))
    print(json.dumps(out,ensure_ascii=False,indent=2))
