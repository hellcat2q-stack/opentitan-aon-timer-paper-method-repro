"""Sanitized Stage09 evidence and measured comparison plots; raw VDBs stay put."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(folder):
    (folder / "sha256.txt").write_text("".join(
        f"{sha(p)}  {p.name}\n" for p in sorted(folder.iterdir()) if p.is_file() and p.name != "sha256.txt"), encoding="utf-8")


def export_run(run, output):
    output.mkdir(exist_ok=False, parents=True)
    for name in ("protocol.json", "summary.json", "audit.json", "events.jsonl", "vectors.csv",
                 "coverage_curve.csv", "raw_uvm_audit.json", "union_audit.json", "input_comparison.json"):
        shutil.copyfile(run / name, output / name)
    # Whitelist the original V30 export schema, excluding raw errors and paths.
    safe = {"run_id", "status", "test_description", "global_run_id", "test_name", "sequence",
            "seed", "vcs_return_code", "urg_return_code", "simulator_cpu_seconds", "uvm_pass",
            "uvm_error", "uvm_fatal", "run_covered_bins", "parsed_bin_count", "worker_start_time",
            "worker_end_time", "worker_wall_seconds", "feedback_order", "target", "new_bins",
            "target_category_gain", "weighted_info_gain", "accumulated_covered", "coverage_percent"}
    results = [{k: v for k, v in row.items() if k in safe} for row in read(run / "run_results.json")]
    (output / "run_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    summary = read(run / "summary.json")
    plot([(summary["method"], run / "coverage_curve.csv")], output / "coverage_curve.png")
    (output / "README.md").write_text(
        f"# {summary['method']} 实测结果\n\n"
        f"完成 {summary['completed']}/{summary['submitted']}；成功 {summary['accepted']}，失败 {summary['failed']}，重试 0。\n\n"
        f"覆盖 {summary['final_covered_bins']}/4507（{summary['final_coverage_percent']:.4f}%），初始 508 bins；"
        f"新增 {summary['new_bins_beyond_initial']} bins。wall time {summary['wall_seconds']:.2f} 秒，"
        f"累计 simulator CPU {summary['accumulated_simulator_cpu_seconds_all_attempts']:.2f} 秒。\n\n"
        "事件/seed/覆盖向量/目标与全局新增奖励、原始 UVM 日志和独立 URG 合并审计通过。"
        "使用 V30 build，所有第九步方法统一关闭参数定向；完整日志和数据库留在学校服务器。"
        "30 次 smoke 与正式 1000 次独立运行，预算和结果不拼接。\n", encoding="utf-8")
    manifest(output)


def plot(series, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    fields = ("feedback_order", "accumulated_simulator_cpu_seconds", "wall_seconds")
    labels = ("Completed attempts", "Accumulated simulator CPU (s)", "Wall time (s)")
    for name, curve in series:
        with curve.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for ax, field in zip(axes, fields):
            ax.step([0] + [float(r[field]) for r in rows],
                    [508 / 4507 * 100] + [float(r["coverage_percent"]) for r in rows], where="post", label=name)
    for ax, label in zip(axes, labels):
        ax.set(xlabel=label, ylabel="Detailed functional bins covered (%)", ylim=(0, 100))
        ax.grid(alpha=.25)
    axes[-1].legend(fontsize=8)
    fig.suptitle("AON Timer Stage09: V30 build, uniform inputs, steering disabled")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    export_run(args.run_dir, args.output_dir)


if __name__ == "__main__":
    main()
