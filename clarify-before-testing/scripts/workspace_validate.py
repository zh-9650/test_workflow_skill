from pathlib import Path
import argparse,json
BAD_EXT={'.py','.js','.txt','.png','.jpg','.jpeg','.json'}
ALLOWED_ROOT={'deliverables','dashboard','internal','scripts','evidence','logs','downloads','scratch','.test-secrets.env'}
def validate(run):
    run=Path(run); issues=[]
    for p in run.iterdir():
        if p.name not in ALLOWED_ROOT: issues.append(f'run root unexpected: {p.name}')
        if p.is_file() and p.suffix.lower() in BAD_EXT: issues.append(f'run root loose file: {p.name}')
    for p in run.rglob('__pycache__'): issues.append(f'cache: {p.relative_to(run)}')
    for p in run.rglob('.pytest_cache'): issues.append(f'cache: {p.relative_to(run)}')
    return {'ok':not issues,'issues':issues}
if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--run',required=True); x=a.parse_args(); r=validate(x.run); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['ok'] else 1)
