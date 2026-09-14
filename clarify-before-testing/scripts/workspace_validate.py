from pathlib import Path
import argparse,json
BAD_EXT={'.py','.js','.txt','.png','.jpg','.jpeg','.json'}
ALLOWED_ROOT={'deliverables','dashboard','internal','scripts','evidence','logs','downloads','scratch','.test-secrets.env'}
REQUIRED_DIRS={'deliverables','dashboard','internal','scripts','evidence','logs','downloads','scratch'}
STAGE_FILES={
    'business-modeling':{'deliverables/01-business-understanding.md'},
    'case-design':{'deliverables/01-business-understanding.md','deliverables/02-test-points.md','deliverables/03-test-cases.md'},
    'execution-planning':{'deliverables/01-business-understanding.md','deliverables/02-test-points.md','deliverables/03-test-cases.md','deliverables/04-execution-plan.md'},
    'result-review':{'deliverables/05-test-report.md'},
}
def validate(run,stage=None):
    run=Path(run); issues=[]
    if not run.exists() or not run.is_dir(): return {'ok':False,'issues':[f'run does not exist: {run}']}
    for name in REQUIRED_DIRS:
        if not (run/name).is_dir(): issues.append(f'missing required directory: {name}')
    for p in run.iterdir():
        if p.name not in ALLOWED_ROOT: issues.append(f'run root unexpected: {p.name}')
        if p.is_file() and p.suffix.lower() in BAD_EXT: issues.append(f'run root loose file: {p.name}')
    for p in run.rglob('__pycache__'): issues.append(f'cache: {p.relative_to(run)}')
    for p in run.rglob('.pytest_cache'): issues.append(f'cache: {p.relative_to(run)}')
    for rel in STAGE_FILES.get(stage,set()):
        if not (run/rel).is_file(): issues.append(f'missing deliverable for {stage}: {rel}')
    return {'ok':not issues,'issues':issues}
if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--run',required=True); a.add_argument('--stage'); x=a.parse_args(); r=validate(x.run,x.stage); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['ok'] else 1)
