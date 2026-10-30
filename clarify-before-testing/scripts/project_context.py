"""只读项目知识协议适配；不扫描历史目录、不修改状态。"""
import json
from pathlib import Path
import subprocess
import sys


def query(project_root, command, *, line=None, module=None):
    root=Path(project_root).resolve()
    tool=root/'tools/project-memory/project_memory.py'
    if not tool.is_file():
        raise ValueError('Project knowledge CLI is missing; initialize or finish the project migration first')
    if command not in {'discover','context','search'}:
        raise ValueError('Only read-only context commands are supported')
    args=[sys.executable,'-X','utf8',str(tool),'--root',str(root),command]
    if line: args += ['--line',line]
    if module: args += ['--module',module]
    if command=='search': args += ['']
    result=subprocess.run(args,cwd=root,text=True,encoding='utf-8',capture_output=True,check=False)
    if result.returncode:
        raise ValueError('Project knowledge resolution failed: '+result.stdout.strip())
    return json.loads(result.stdout)
