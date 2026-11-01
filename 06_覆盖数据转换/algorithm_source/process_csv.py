#!/usr/bin/env python3
"""
覆盖率CSV生成工具
从测试结果目录生成覆盖率数据CSV文件
Usage: python3 process_csv.py <results_dir> [output_csv]
"""

import os
import sys
import subprocess
import pandas as pd
import numpy as np
from glob import glob
from tqdm import tqdm
import bs4
import re
import joblib
from pathlib import Path
import argparse

# 定义正则表达式模式
cp_pattern = re.compile(r'<p class="summary_title">(CoverPoint|CoverCross) Details: (.*)</p>')
t_pattern = re.compile(r'">([^/]+)</t[hd]>')
pkg_pattern = re.compile(r'.*::')
legal_pattern = re.compile(r'.*/[cp][0-9]*.html')
runtime_pattern = re.compile(r'Times for simulation: run (\d+.\d+)s')

def collect_bin_cnt(report):
    """从HTML报告中收集bin计数"""
    bin_cnt = {}
    htmls = list(sorted(filter(lambda s: re.fullmatch(legal_pattern, s), glob(f'{report}/report/*.html'))))
    for html in htmls:
        try:
            with open(html, 'r') as f:
                soup = bs4.BeautifulSoup(f, 'html.parser')
                segs = soup.find_all(lambda tag: tag.get("id") == 'coverageTable' or
                                      (tag.has_attr("class") and 'summary_title' in tag.get("class")))
                
                cp_name = None
                for seg in segs:
                    if seg.name == 'p':
                        m = cp_pattern.match(str(seg))
                        if m:
                            cp_name = m.group(2)
                            cp_name = pkg_pattern.sub('', cp_name)
                            cp_name = cp_name.replace('.', '-')
                    elif seg.name == 'table' and cp_name:
                        for child in seg.children:
                            if child.name == 'thead':
                                th = '/'.join(t_pattern.findall(str(child)))
                                if th != 'Count/At Least/Bin Type/Bin Name/Database Covered':
                                    break
                            elif child.name == 'tbody':
                                for c in child.children:
                                    parts = list(map(lambda td: td.get_text(strip=True), c.find_all('td')))
                                    if len(parts) >= 4:
                                        cnt = int(parts[0])
                                        bin_name = parts[3]
                                        key = f'{cp_name}-{bin_name}'
                                        bin_cnt[key] = cnt
        except Exception as e:
            print(f"Warning: Error processing {html}: {e}")
            continue
    return bin_cnt

def extract_sequence_name(test_dir):
    """从测试目录中提取序列名称"""
    import re
    
    # 尝试从配置文件中提取序列名称
    for config_file in ['test_config.txt', 'python_runner.log']:
        config_path = os.path.join(test_dir, config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    content = f.read()
                    
                    # 检查Test Name字段
                    for line in content.split('\n'):
                        if line.startswith('Test Name:'):
                            test_name = line.split(':', 1)[1].strip()
                            if test_name and test_name != 'unknown':
                                return test_name
                    
                    # 检查Test Sequence字段
                    for line in content.split('\n'):
                        if line.startswith('Test Sequence:'):
                            sequence_name = line.split(':', 1)[1].strip()
                            if sequence_name and sequence_name != 'unknown':
                                return sequence_name
                        
            except Exception as e:
                print(f"Warning: Error reading {config_path}: {e}")
                continue
    
    # 尝试从cmd.txt文件中提取序列信息
    cmd_file = os.path.join(test_dir, 'cmd.txt')
    if os.path.exists(cmd_file):
        try:
            with open(cmd_file, 'r') as f:
                cmd_content = f.read()
                
                # 查找UVM_TEST_SEQ参数
                seq_match = re.search(r'\+UVM_TEST_SEQ=([^\s]+)', cmd_content)
                if seq_match:
                    return seq_match.group(1)
                    
        except Exception as e:
            print(f"Warning: Error reading cmd.txt: {e}")
    
    # 尝试从目录路径中提取信息
    try:
        parent_dirs = test_dir.split(os.sep)
        for dir_name in reversed(parent_dirs):
            if dir_name.isdigit():
                continue
            if '_vseq' in dir_name:
                return dir_name
                
    except Exception as e:
        print(f"Warning: Error extracting from path: {e}")
    
    return 'unknown'

def process_data(dashboard_dir):
    """处理单个测试的数据"""
    try:
        test_dir = os.path.dirname(dashboard_dir)
        bin_cnt = collect_bin_cnt(dashboard_dir)
        
        # 提取runtime
        log_file = os.path.join(test_dir, 'run.log')
        runtime = 0.0
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    content = f.read()
                    runtime_match = runtime_pattern.search(content)
                    if runtime_match:
                        runtime = float(runtime_match.group(1))
            except:
                pass
        
        bin_cnt['runtime'] = runtime
        
        # 提取序列名称
        sequence_name = extract_sequence_name(test_dir)
        bin_cnt['run'] = sequence_name
        
        return bin_cnt
    except Exception as e:
        print(f"Error processing {test_dir}: {e}")
        return {'runtime': 0.0, 'run': 'unknown'}

def generate_html_reports(results_dir):
    """为所有coverage.zdb文件生成HTML报告"""
    print("Generating HTML reports using vericov...")
    
    # 查找所有coverage.zdb文件
    coverage_dbs = glob(f'{results_dir}/**/coverage.zdb', recursive=True)
    
    if not coverage_dbs:
        print("Warning: No coverage.zdb files found")
        return False
    
    print(f"Found {len(coverage_dbs)} coverage databases")
    
    # 为每个coverage.zdb生成HTML报告
    for coverage_db in tqdm(coverage_dbs, desc="Generating HTML reports"):
        test_dir = os.path.dirname(coverage_db)
        dashboard_dir = os.path.join(test_dir, 'dashboard.html')
        
        # 如果dashboard.html已存在，跳过
        if os.path.exists(dashboard_dir):
            continue
        
        vericov_cmd = [
            'vericov', # 请注意 source activate.sh，确保使用正确的vericov版本
            '-lcov',
            '-report',
            coverage_db,
            '-out', dashboard_dir
        ]
        
        try:
            result = subprocess.run(vericov_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, timeout=300)
            
            if result.returncode != 0:
                print(f"Warning: vericov failed for {coverage_db}")
                
        except subprocess.TimeoutExpired:
            print(f"Warning: vericov timed out for {coverage_db}")
        except Exception as e:
            print(f"Warning: Error running vericov for {coverage_db}: {e}")
    
    return True

def load_data(results_dir):
    """从results目录加载数据"""
    # 查找所有dashboard.html文件
    dashboard_dirs = list(sorted(glob(f'{results_dir}/**/dashboard.html', recursive=True)))
    
    if not dashboard_dirs:
        print("No dashboard.html files found")
        return pd.DataFrame()
    
    print(f'Processing {len(dashboard_dirs)} test cases...')
    
    # 并行处理数据
    raw_data = joblib.Parallel(n_jobs=8)(
        joblib.delayed(process_data)(dashboard_dir) for dashboard_dir in tqdm(dashboard_dirs)
    )
    
    # 转换为DataFrame
    df = pd.DataFrame(raw_data)
    
    # 确保run列在最前面
    if 'run' in df.columns:
        cols = ['run'] + [col for col in df.columns if col != 'run']
        df = df[cols]
    
    return df

def main():
    parser = argparse.ArgumentParser(description='Coverage CSV Generator - Process test results and generate CSV file')
    parser.add_argument('results_dir', help='Test results directory path')
    parser.add_argument('output_csv', nargs='?', default='coverage_data.csv', 
                       help='Output CSV file path (default: coverage_data.csv)')
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        return 1
    
    print(f"Processing results directory: {results_dir}")
    print(f"Output CSV file: {args.output_csv}")
    
    # 生成HTML报告
    if not generate_html_reports(results_dir):
        print("Failed to generate HTML reports")
        return 1
    
    # 加载数据
    df = load_data(results_dir)
    
    if df.empty:
        print("No data loaded. Please check if HTML reports exist.")
        return 1
    
    # 保存CSV
    df.to_csv(args.output_csv, index=False)
    
    print(f"\nData processing completed!")
    print(f"Output saved to: {args.output_csv}")
    print(f"Data shape: {df.shape}")
    print(f"Columns: {len(df.columns)}")
    print(f"Test cases: {len(df)}")
    
    if 'run' in df.columns:
        print(f"\nSequence distribution:")
        sequence_counts = df['run'].value_counts()
        for seq, count in sequence_counts.items():
            print(f"  {seq}: {count} tests")
    
    if 'runtime' in df.columns:
        print(f"\nRuntime statistics:")
        print(f"  Total runtime: {df['runtime'].sum():.2f}s")
        print(f"  Average runtime: {df['runtime'].mean():.2f}s")
        print(f"  Min runtime: {df['runtime'].min():.2f}s")
        print(f"  Max runtime: {df['runtime'].max():.2f}s")
    
    print(f"\nFirst few rows:")
    print(df.head())
    
    return 0

if __name__ == '__main__':
    exit(main())
