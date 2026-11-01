#!/usr/bin/env python3
"""
Sequence-Based Parallel Test Runner with YAML Configuration Support
每个测试序列运行指定次数，而不是总共运行指定次数
Usage: python3 sequence_based_parallel_test.py <config_file> <runs_per_sequence> <result_dir> [--seed SEED] [--parallel N]
"""

import os
import sys
import random
import argparse
import subprocess
import shutil
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import signal
import threading

class TestConfig:
    """测试配置类，从YAML文件加载配置"""
    def __init__(self, config_file):
        self.config_file = config_file
        self.test_name = "generic_test"
        self.test_sequences = []
        self.verisim_config = {}
        self.base_run_cmd = []
        self.load_config()
    
    def load_config(self):
        """从配置文件加载测试序列和运行命令配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 基本配置
            self.test_name = config.get('test_name', 'generic_test')
            self.verisim_config = config.get('verisim_config', {})
            
            # 基础运行命令模板
            self.base_run_cmd = config.get('base_run_cmd', [])
            
            # 测试序列
            self.test_sequences = config.get('test_sequences', [])
            
            print(f"Loaded config for {self.test_name}")
            print(f"  Test sequences: {len(self.test_sequences)}")
            
        except Exception as e:
            print(f"Error loading config file {self.config_file}: {e}")
            sys.exit(1)
    
    def get_all_test_jobs(self, runs_per_sequence):
        """获取所有测试任务（每个序列运行runs_per_sequence次）"""
        all_jobs = []
        
        for seq_config in self.test_sequences:
            seq_name = seq_config.get('seq', seq_config['name'])
            for run_idx in range(runs_per_sequence):
                job = {
                    'seq': seq_name,
                    'seq_config': seq_config,
                    'sequence_run_index': run_idx  # 该序列的第几次运行
                }
                all_jobs.append(job)
        
        return all_jobs

class SequenceBasedParallelTestRunner:
    def __init__(self, config_file, runs_per_sequence, result_dir, base_seed=42, max_workers=4):
        self.test_config = TestConfig(config_file)
        self.runs_per_sequence = runs_per_sequence
        # 确保结果目录是绝对路径，避免工作目录切换问题
        self.result_dir = Path(result_dir).resolve()
        self.base_seed = base_seed
        self.max_workers = max_workers
        self.running_processes = []
        self.lock = threading.Lock()
        
        # Set random seed for reproducibility
        random.seed(base_seed)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle interrupt signals and cleanup processes"""
        print(f"\nReceived signal {signum}, cleaning up...")
        self.cleanup_processes()
        sys.exit(1)
    
    def cleanup_processes(self):
        """Terminate all running processes"""
        with self.lock:
            for proc in self.running_processes:
                if proc.poll() is None:  # Process is still running
                    try:
                        # Kill the entire process group to ensure child processes are also terminated
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except:
                            proc.kill()
                    except Exception as e:
                        print(f"Error cleaning up process: {e}")
                        try:
                            proc.kill()
                        except:
                            pass
    
    def setup_result_directory(self):
        """Setup the result directory structure"""
        print(f"Setting up result directory: {self.result_dir}")
        
        # Remove existing directory if it exists
        if self.result_dir.exists():
            shutil.rmtree(self.result_dir)
        
        # Create main result directory
        self.result_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for each sequence
        for seq_config in self.test_config.test_sequences:
            seq_name = seq_config['name']
            seq_dir = self.result_dir / seq_name
            seq_dir.mkdir(exist_ok=True)
            
            # Create subdirectories for each run of this sequence
            for run_idx in range(self.runs_per_sequence):
                run_dir = seq_dir / str(run_idx)
                run_dir.mkdir(exist_ok=True)
    
    def generate_test_config(self, job, global_run_id):
        """Generate test configuration for a specific job"""
        # Generate seed for this specific test
        test_seed = random.randint(1, 2**31 - 1)
        
        seq_config = job['seq_config']
        seq_name = seq_config['name']
        sequence_run_index = job['sequence_run_index']
        
        run_dir = self.result_dir / seq_name / str(sequence_run_index)
        
        config = {
            'global_run_id': global_run_id,
            'run_dir': run_dir,
            'seed': test_seed,
            'test_seq': job['seq'],
            'seq_config': seq_config,
            'sequence_name': seq_name,
            'sequence_run_index': sequence_run_index
        }
        
        # Write config to file for reference
        config_file = run_dir / 'test_config.txt'
        with open(config_file, 'w') as f:
            f.write(f"Global Run ID: {global_run_id}\n")
            f.write(f"Seed: {test_seed}\n")
            f.write(f"Test Name: {seq_config['name']}\n")
            f.write(f"Test Sequence: {job['seq']}\n")
            f.write(f"Sequence Run Index: {sequence_run_index} (第{sequence_run_index + 1}次运行)\n")
            additional_params = seq_config.get('additional_params', [])
            if additional_params:
                f.write(f"Additional Params: {' '.join(additional_params)}\n")
            f.write(f"Base Seed: {self.base_seed}\n")
        
        return config

    def build_run_command(self, test_config):
        """根据测试配置构建运行命令"""
        seq_config = test_config['seq_config']
        
        # 从基础命令模板开始
        cmd = self.test_config.base_run_cmd.copy()
        
        # 替换占位符
        verisim_config = self.test_config.verisim_config
        
        for i, arg in enumerate(cmd):
            if '{verisim_home}' in arg:
                cmd[i] = arg.replace('{verisim_home}', verisim_config.get('verisim_home', ''))
            if '{image_dir}' in arg:
                cmd[i] = arg.replace('{image_dir}', verisim_config.get('image_dir', ''))
            if '{test_name}' in arg:
                cmd[i] = arg.replace('{test_name}', verisim_config.get('test_name', ''))
            if '{test_seq}' in arg:
                cmd[i] = arg.replace('{test_seq}', test_config['test_seq'])
            if '{seed}' in arg:
                cmd[i] = arg.replace('{seed}', str(test_config['seed']))
            if '{run_dir}' in arg:
                cmd[i] = arg.replace('{run_dir}', str(test_config['run_dir'].absolute()))
        
        # 添加序列特定的额外参数
        additional_params = seq_config.get('additional_params', [])
        if additional_params:
            # 在verisim可执行文件后面插入额外参数
            cmd = cmd[:1] + additional_params + cmd[1:]
        
        return cmd
    
    def run_single_test(self, test_config):
        """Run a single test with the given configuration"""
        global_run_id = test_config['global_run_id']
        run_dir = test_config['run_dir']
        seed = test_config['seed']
        test_seq = test_config['test_seq']
        sequence_name = test_config['sequence_name']
        sequence_run_index = test_config['sequence_run_index']
        
        print(f"Starting test {global_run_id}: {sequence_name} (run {sequence_run_index + 1}/{self.runs_per_sequence}) -> {test_seq} (seed: {seed})")
        
        try:
            # 构建运行命令
            cmd = self.build_run_command(test_config)
            
            # Write command to file for reference
            cmd_file = run_dir / 'cmd.txt'
            with open(cmd_file, 'w') as f:
                f.write(' '.join(cmd) + '\n')
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(run_dir),  # Change working directory to run_dir
                preexec_fn=os.setsid  # Create new process group for better signal handling
            )
            
            # Track the process
            with self.lock:
                self.running_processes.append(process)
            
            # Wait for completion
            stdout, _ = process.communicate()
            
            # Remove from tracking
            with self.lock:
                if process in self.running_processes:
                    self.running_processes.remove(process)
            
            # Write run log
            run_log_file = run_dir / 'run.log'
            with open(run_log_file, 'w') as f:
                f.write(stdout)
            
            # Log results
            log_file = run_dir / 'python_runner.log'
            with open(log_file, 'w') as f:
                f.write(f"Global Test {global_run_id} completed\n")
                f.write(f"Test Name: {test_config['seq_config']['name']}\n")
                f.write(f"Test Sequence: {test_seq}\n")
                f.write(f"Sequence Run Index: {sequence_run_index}\n")
                additional_params = test_config['seq_config'].get('additional_params', [])
                if additional_params:
                    f.write(f"Additional Params: {' '.join(additional_params)}\n")
                f.write(f"Seed: {seed}\n")
                f.write(f"Return Code: {process.returncode}\n")
                f.write(f"Working Directory: {run_dir}\n")
                f.write(f"Command: {' '.join(cmd)}\n")
            
            if process.returncode == 0:
                print(f"Test {global_run_id} completed successfully: {sequence_name} run {sequence_run_index + 1}")
                return {
                    'global_run_id': global_run_id, 
                    'status': 'success', 
                    'test_seq': test_seq,
                    'sequence_name': sequence_name,
                    'sequence_run_index': sequence_run_index
                }
            else:
                print(f"Test {global_run_id} failed: {sequence_name} run {sequence_run_index + 1} (return code {process.returncode})")
                return {
                    'global_run_id': global_run_id, 
                    'status': 'failed', 
                    'test_seq': test_seq,
                    'sequence_name': sequence_name,
                    'sequence_run_index': sequence_run_index,
                    'return_code': process.returncode
                }
                
        except Exception as e:
            print(f"Error running test {global_run_id}: {e}")
            return {
                'global_run_id': global_run_id, 
                'status': 'error', 
                'test_seq': test_seq,
                'sequence_name': sequence_name,
                'sequence_run_index': sequence_run_index,
                'error': str(e)
            }
    
    def run_all_tests(self):
        """Run all tests - each sequence runs runs_per_sequence times"""
        # Get all test jobs
        all_jobs = self.test_config.get_all_test_jobs(self.runs_per_sequence)
        total_tests = len(all_jobs)
        
        print(f"Starting {total_tests} tests with {self.max_workers} parallel workers")
        print(f"Test configuration: {self.test_config.test_name}")
        print(f"Base seed: {self.base_seed}")
        print(f"Sequences: {len(self.test_config.test_sequences)}")
        print(f"Runs per sequence: {self.runs_per_sequence}")
        print(f"Total tests: {len(self.test_config.test_sequences)} × {self.runs_per_sequence} = {total_tests}")
        
        # Setup directory structure
        self.setup_result_directory()
        
        # Generate test configurations
        configs = []
        for global_run_id, job in enumerate(all_jobs):
            config = self.generate_test_config(job, global_run_id)
            configs.append(config)
        
        # Run tests in parallel
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_config = {
                executor.submit(self.run_single_test, config): config 
                for config in configs
            }
            
            # Collect results
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"Test {config['global_run_id']} generated exception: {e}")
                    results.append({
                        'global_run_id': config['global_run_id'], 
                        'status': 'exception', 
                        'test_seq': config['test_seq'],
                        'sequence_name': config['sequence_name'],
                        'sequence_run_index': config['sequence_run_index'],
                        'error': str(e)
                    })
        
        # Generate summary report
        self.generate_summary_report(results)
        
        return results
    
    def generate_summary_report(self, results):
        """Generate a summary report of all test results"""
        summary_file = self.result_dir / 'test_summary.txt'
        
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        error_count = sum(1 for r in results if r['status'] in ['error', 'exception'])
        
        with open(summary_file, 'w') as f:
            f.write(f"Sequence-Based Parallel Test Summary Report\n")
            f.write(f"==========================================\n")
            f.write(f"Test Configuration: {self.test_config.test_name}\n")
            f.write(f"Total Tests: {len(results)}\n")
            f.write(f"Successful: {success_count}\n")
            f.write(f"Failed: {failed_count}\n")
            f.write(f"Errors: {error_count}\n")
            f.write(f"Base Seed: {self.base_seed}\n")
            f.write(f"Max Workers: {self.max_workers}\n")
            f.write(f"Runs per Sequence: {self.runs_per_sequence}\n\n")
            
            # Sequence-based distribution
            total_sequences = len(self.test_config.test_sequences)
            
            f.write("Test Execution Summary:\n")
            f.write(f"  Total Sequences: {total_sequences}\n")
            f.write(f"  Runs per Sequence: {self.runs_per_sequence}\n")
            f.write(f"  Expected Total Tests: {total_sequences * self.runs_per_sequence}\n")
            f.write(f"  Actual Total Tests: {len(results)}\n\n")
            
            # Per-sequence results
            f.write("Results by Sequence:\n")
            for seq_config in self.test_config.test_sequences:
                seq_name = seq_config['name']
                seq_results = [r for r in results if r['sequence_name'] == seq_name]
                seq_success = sum(1 for r in seq_results if r['status'] == 'success')
                seq_failed = sum(1 for r in seq_results if r['status'] == 'failed')
                seq_errors = sum(1 for r in seq_results if r['status'] in ['error', 'exception'])
                
                f.write(f"  {seq_name}: {seq_success}/{len(seq_results)} successful")
                if seq_failed > 0 or seq_errors > 0:
                    f.write(f" ({seq_failed} failed, {seq_errors} errors)")
                f.write(f"\n")
            f.write("\n")
            
            # Detailed results
            f.write("Detailed Results:\n")
            # Group by sequence for better readability
            for seq_config in self.test_config.test_sequences:
                seq_name = seq_config['name']
                seq_results = [r for r in results if r['sequence_name'] == seq_name]
                seq_results.sort(key=lambda x: x['sequence_run_index'])
                
                f.write(f"  {seq_name}:\n")
                for r in seq_results:
                    f.write(f"    Run {r['sequence_run_index'] + 1}: {r['status']}")
                    if 'return_code' in r:
                        f.write(f" (code: {r['return_code']})")
                    if 'error' in r:
                        f.write(f" (error: {r['error']})")
                    f.write(f"\n")
                f.write(f"\n")
        
        print(f"\nTest Summary:")
        print(f"Total: {len(results)}, Success: {success_count}, Failed: {failed_count}, Errors: {error_count}")
        print(f"Per-sequence execution: {len(self.test_config.test_sequences)} sequences × {self.runs_per_sequence} runs each")
        print(f"Summary report saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(description='Sequence-Based Parallel Test Runner with YAML Configuration Support')
    parser.add_argument('config_file', help='YAML configuration file containing test sequences and run commands')
    parser.add_argument('runs_per_sequence', type=int, help='Number of times to run each sequence')
    parser.add_argument('result_dir', help='Result directory path')
    parser.add_argument('--seed', type=int, default=42, help='Base seed for random number generation (default: 42)')
    parser.add_argument('--parallel', type=int, default=4, help='Number of parallel workers (default: 4)')
    
    args = parser.parse_args()
    
    if args.runs_per_sequence <= 0:
        print("Error: runs_per_sequence must be positive")
        sys.exit(1)
    
    if args.parallel <= 0:
        print("Error: parallel workers must be positive")
        sys.exit(1)
    
    runner = SequenceBasedParallelTestRunner(
        config_file=args.config_file,
        runs_per_sequence=args.runs_per_sequence,
        result_dir=args.result_dir,
        base_seed=args.seed,
        max_workers=args.parallel
    )
    
    try:
        results = runner.run_all_tests()
        
        # Exit with error code if any tests failed
        failed_tests = sum(1 for r in results if r['status'] != 'success')
        if failed_tests > 0:
            print(f"Warning: {failed_tests} tests did not complete successfully")
            sys.exit(1)
        else:
            print("All tests completed successfully!")
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()