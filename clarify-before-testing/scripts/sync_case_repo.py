#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_case_repo.py - 测试用例与公司中枢 Git 仓库双向同步工具

功能：
1. pull: 自动拉取远端 master 防冲突；
2. copy: 将 deliverables/ 下的 full.md 和 smoke.md 覆盖拷贝到仓库对应模块目录；
3. index: 自动解析条目数并原子更新 projects/<project>/test/README.md 索引表格；
4. push: 自动执行 git commit 与 git push master（适配 Windows 证书环境）；
5. diff: 比对本地新文件与远端正本的条目差异。
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO_PATH = Path(r"C:\Users\17381\Desktop\ai-hub")
DEFAULT_PROJECT = "cangcloud-3.0"
GIT_OPTIONS = ["-c", "http.sslVerify=false", "-c", "http.schannelCheckRevoke=false"]


def run_cmd(cmd_list, cwd):
    """运行外部命令并返回结果"""
    res = subprocess.run(cmd_list, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def count_cases_in_file(file_path):
    """从 Markdown 用例中解析条目数声明或统计 Case ID"""
    if not file_path.exists():
        return "0条"
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    
    # 优先匹配正文开头的明确声明
    m = re.search(r"当前用例总数[：:]\s*(\d+)", text)
    if m:
        return f"{m.group(1)}条"
    m = re.search(r"用例主项[：:]\s*[\*]*(\d+)[\*]*", text)
    if m:
        m2 = re.search(r"(?:可独立执行数据组|独立执行数据组|实际可独立执行的数据组/场景|执行场景)[：:]\s*[\*]*(\d+)[\*]*", text)
        if m2:
            return f"{m.group(1)}主项/{m2.group(1)}场景"
        return f"{m.group(1)}主项"
    m_smoke = re.search(r"(?:共抽取|来源用例主项[：:]\s*[\*]*)\s*(\d+)", text)
    if m_smoke:
        m_scene = re.search(r"(?:实际执行数据组|执行数据组)[：:]\s*[\*]*(\d+)[\*]*", text)
        if m_scene:
            return f"{m_smoke.group(1)}主项/{m_scene.group(1)}场景"
        return f"{m_smoke.group(1)}条"
    
    # 兜底：统计唯一的 Case ID 数量
    ids = set(re.findall(r"(?:\||\#\#\#)\s*(?:`?)([A-Za-z0-9_-]+(?:CASE|TC|SM)[A-Za-z0-9_-]*)", text))
    if ids:
        return f"{len(ids)}条"
    
    # 统计表格行
    table_rows = [line for line in text.splitlines() if re.match(r"^\|\s*[A-Za-z0-9_-]+\s*\|", line)]
    if table_rows:
        return f"{len(table_rows)}条"
    return "已就绪"


def update_readme_index(readme_path, module, full_stat, smoke_stat):
    """原子更新 test/README.md 模块清单表格"""
    if not readme_path.exists():
        print(f"[WARN] README.md 不存在: {readme_path}")
        return False
    content = readme_path.read_text(encoding="utf-8")
    
    # 匹配表格行: | module | cases/module/full.md... | cases/module/smoke.md... | ... | ... |
    pattern = rf"(\|\s*{re.escape(module)}\s*\|\s*cases/{re.escape(module)}/full\.md[^\n]*\n)"
    new_row = f"| {module} | cases/{module}/full.md（{full_stat}） | cases/{module}/smoke.md（{smoke_stat}） | 待补 | ✅ 全量+冒烟已传 |\n"
    
    if re.search(pattern, content):
        content = re.sub(pattern, new_row, content)
        print(f"[OK] 已更新索引现有模块行: {module}")
    else:
        # 寻找表格末尾并追加
        marker = "## 文件命名约定"
        if marker in content:
            content = content.replace(marker, f"{new_row}\n{marker}")
            print(f"[OK] 已向索引追加新模块行: {module}")
        else:
            print("[WARN] 未能在 README.md 中找到表格锚点，跳过索引更新")
            return False
            
    readme_path.write_text(content, encoding="utf-8")
    return True


def diff_cases(local_file, remote_file):
    """提取 ID 比对新旧差异"""
    if not remote_file.exists():
        print(f"[INFO] 远端文件不存在，视为全新文件: {remote_file.name}")
        return
    local_txt = local_file.read_text(encoding="utf-8", errors="ignore")
    remote_txt = remote_file.read_text(encoding="utf-8", errors="ignore")
    
    id_pattern = r"(?:\||\#\#\#)\s*(?:`?)([A-Za-z0-9_-]+(?:CASE|TC|SM)[A-Za-z0-9_-]*)"
    local_ids = set(re.findall(id_pattern, local_txt))
    remote_ids = set(re.findall(id_pattern, remote_txt))
    
    added = local_ids - remote_ids
    removed = remote_ids - local_ids
    common = local_ids & remote_ids
    
    print(f"\n===== 比对结果: {local_file.name} =====")
    print(f"本地条目数: {len(local_ids)}, 远端正本条目数: {len(remote_ids)}")
    print(f"新增条目 ({len(added)}): {', '.join(sorted(added)) if added else '无'}")
    print(f"删除条目 ({len(removed)}): {', '.join(sorted(removed)) if removed else '无'}")
    print(f"重合稳定条目: {len(common)}")


def main():
    parser = argparse.ArgumentParser(description="同步测试用例到中枢 Git 仓库")
    parser.add_argument("--module", required=True, help="模块英文标识 (如 mcp, skill, platform)")
    parser.add_argument("--repo-path", default=str(DEFAULT_REPO_PATH), help="中枢仓库本地路径")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="项目名称目录")
    parser.add_argument("--full-file", help="全量用例源路径 (默认自动寻找 deliverables/full.md)")
    parser.add_argument("--smoke-file", help="冒烟用例源路径 (默认自动寻找 deliverables/smoke.md)")
    parser.add_argument("--run-dir", help="当前 Run 根目录")
    parser.add_argument("--message", help="Commit 提交信息")
    parser.add_argument("--diff-only", action="store_true", help="仅比对差异不覆盖推送")
    parser.add_argument("--no-push", action="store_true", help="仅本地更新不 push 远程")
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.exists() or not (repo / ".git").exists():
        print(f"[ERROR] 目标路径不是有效的 Git 仓库: {repo}")
        sys.exit(1)

    # 确定源文件
    full_src = None
    smoke_src = None
    if args.full_file:
        full_src = Path(args.full_file)
    elif args.run_dir:
        full_src = Path(args.run_dir) / "deliverables" / "full.md"
        if not full_src.exists():
            full_src = Path(args.run_dir) / "deliverables" / "03-test-cases.md"
            
    if args.smoke_file:
        smoke_src = Path(args.smoke_file)
    elif args.run_dir:
        smoke_src = Path(args.run_dir) / "deliverables" / "smoke.md"

    if not full_src or not full_src.exists():
        print(f"[ERROR] 未找到全量用例源文件: {full_src}")
        sys.exit(1)
    if not smoke_src or not smoke_src.exists():
        print(f"[ERROR] 未找到冒烟用例源文件: {smoke_src}")
        sys.exit(1)

    # 目标目录
    target_dir = repo / "projects" / args.project / "test" / "cases" / args.module
    target_full = target_dir / "full.md"
    target_smoke = target_dir / "smoke.md"
    readme_path = repo / "projects" / args.project / "test" / "README.md"

    # Step 1: Git pull
    print(f"\n[Step 1] 拉取中枢仓库最新代码 (pull origin master)...")
    code, out, err = run_cmd(["git"] + GIT_OPTIONS + ["pull", "origin", "master"], cwd=str(repo))
    if code != 0:
        print(f"[ERROR] Git pull 失败: {err or out}")
        sys.exit(1)
    print("[OK] 代码已是最新状态")

    # Step 2: 比对检查 (若指定 --diff-only)
    if args.diff_only:
        diff_cases(full_src, target_full)
        diff_cases(smoke_src, target_smoke)
        print("\n[INFO] 已完成差异比对，未修改任何文件。")
        return

    # Step 3: 覆盖写入
    print(f"\n[Step 2] 覆盖写入模块用例: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_full.write_bytes(full_src.read_bytes())
    target_smoke.write_bytes(smoke_src.read_bytes())
    print(f"[OK] 已写入 full.md ({full_src.stat().st_size} bytes)")
    print(f"[OK] 已写入 smoke.md ({smoke_src.stat().st_size} bytes)")

    # Step 4: 更新索引
    print(f"\n[Step 3] 解析条目数并更新 README.md 索引...")
    full_count = count_cases_in_file(target_full)
    smoke_count = count_cases_in_file(target_smoke)
    update_readme_index(readme_path, args.module, full_count, smoke_count)

    # Step 5: Git commit & push
    commit_msg = args.message or f"测试用例: {args.module}模块 — 更新全量({full_count})与冒烟({smoke_count})用例"
    print(f"\n[Step 4] 提交修改: {commit_msg}")
    run_cmd(["git", "add", f"projects/{args.project}/test/cases/{args.module}", f"projects/{args.project}/test/README.md"], cwd=str(repo))
    c_code, c_out, c_err = run_cmd(["git", "commit", "-m", commit_msg], cwd=str(repo))
    if c_code != 0:
        if "nothing to commit" in (c_out + c_err):
            print("[INFO] 没有内容变动，无需提交")
            return
        print(f"[ERROR] Commit 失败: {c_err or c_out}")
        sys.exit(1)
    print("[OK] 提交成功")

    if not args.no_push:
        print(f"\n[Step 5] 推送到远程 (push origin master)...")
        p_code, p_out, p_err = run_cmd(["git"] + GIT_OPTIONS + ["push", "origin", "master"], cwd=str(repo))
        if p_code != 0:
            print(f"[ERROR] Push 失败: {p_err or p_out}")
            sys.exit(1)
        print("[OK] 推送成功！")

    # Step 6: 回显链接
    web_base = "https://git.cangjieit.cn:8443/liting/ai-hub/-/blob/master"
    print("\n" + "=" * 60)
    print(f"🎉 模块 [{args.module}] 测试用例已成功同步入库！")
    print(f"全量用例: {web_base}/projects/{args.project}/test/cases/{args.module}/full.md")
    print(f"冒烟门禁: {web_base}/projects/{args.project}/test/cases/{args.module}/smoke.md")
    print(f"模块索引: {web_base}/projects/{args.project}/test/README.md")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
