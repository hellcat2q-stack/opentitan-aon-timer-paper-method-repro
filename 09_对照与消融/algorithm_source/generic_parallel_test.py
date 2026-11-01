#!/usr/bin/env python3
"""
Generic Parallel Test Runner with YAML Configuration Support
Usage: python3 generic_parallel_test.py <config_file> <n_repeat> <result_dir> [--seed SEED] [--parallel N]
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
    
    def get_all_test_options(self):
        """获取所有测试选项"""
        all_tests = []
        
        # 添加所有序列
        for seq_config in self.test_sequences:
            all_tests.append({
                'seq': seq_config.get('seq', seq_config['name']),
                'seq_config': seq_config
            })
        
        return all_tests

class GenericParallelTestRunner:
    def __init__(self, config_file, n_repeat, result_dir, base_seed=42, max_workers=4):
        self.test_config = TestConfig(config_file)
        self.n_repeat = n_repeat
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
        
        # Create subdirectories for each test run
        for i in range(self.n_repeat):
            run_dir = self.result_dir / str(i)
            run_dir.mkdir(exist_ok=True)
    
    def generate_test_config(self, run_id):
        """Generate test configuration for a specific run"""
        # Generate seed for this specific run
        run_seed = random.randint(1, 2**31 - 1)
        
        # Get all test options and randomly select one
        all_test_options = self.test_config.get_all_test_options()
        selected_test = random.choice(all_test_options)
        
        run_dir = self.result_dir / str(run_id)
        
        config = {
            'run_id': run_id,
            'run_dir': run_dir,
            'seed': run_seed,
            'test_seq': selected_test['seq'],
            'seq_config': selected_test['seq_config']
        }
        
        # Write config to file for reference
        config_file = run_dir / 'test_config.txt'
        with open(config_file, 'w') as f:
            f.write(f"Run ID: {run_id}\n")
            f.write(f"Seed: {run_seed}\n")
            f.write(f"Test Name: {selected_test['seq_config']['name']}\n")
            f.write(f"Test Sequence: {selected_test['seq']}\n")
            additional_params = selected_test['seq_config'].get('additional_params', [])
            if additional_params:
                f.write(f"Additional Params: {' '.join(additional_params)}\n")
            f.write(f"Base Seed: {self.base_seed}\n")
        
        return config

    def build_run_command(self, test_config, run_id, seed, run_dir):
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
                cmd[i] = arg.replace('{seed}', str(seed))
            if '{run_dir}' in arg:
                cmd[i] = arg.replace('{run_dir}', str(run_dir.absolute()))
        
        # 添加序列特定的额外参数
        additional_params = seq_config.get('additional_params', [])
        if additional_params:
            # 在verisim可执行文件后面插入额外参数
            cmd = cmd[:1] + additional_params + cmd[1:]
        
        return cmd
    
    def run_single_test(self, config):
        """Run a single test with the given configuration"""
        run_id = config['run_id']
        run_dir = config['run_dir']
        seed = config['seed']
        test_seq = config['test_seq']
        
        print(f"Starting test {run_id}: {config['seq_config']['name']} -> {test_seq} (seed: {seed})")
        test_description = config['seq_config']['name']
        
        try:
            # 构建运行命令
            cmd = self.build_run_command(config, run_id, seed, run_dir)
            
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
                f.write(f"Test {run_id} completed\n")
                f.write(f"Test Name: {config['seq_config']['name']}\n")
                f.write(f"Test Sequence: {test_seq}\n")
                additional_params = config['seq_config'].get('additional_params', [])
                if additional_params:
                    f.write(f"Additional Params: {' '.join(additional_params)}\n")
                f.write(f"Seed: {seed}\n")
                f.write(f"Return Code: {process.returncode}\n")
                f.write(f"Working Directory: {run_dir}\n")
                f.write(f"Command: {' '.join(cmd)}\n")
            
            if process.returncode == 0:
                print(f"Test {run_id} completed successfully")
                return {
                    'run_id': run_id, 
                    'status': 'success', 
                    'test_seq': test_seq,
                    'test_description': test_description
                }
            else:
                print(f"Test {run_id} failed with return code {process.returncode}")
                return {
                    'run_id': run_id, 
                    'status': 'failed', 
                    'test_seq': test_seq,
                    'test_description': test_description,
                    'return_code': process.returncode
                }
                
        except Exception as e:
            print(f"Error running test {run_id}: {e}")
            return {
                'run_id': run_id, 
                'status': 'error', 
                'test_seq': test_seq,
                'test_description': test_description,
                'error': str(e)
            }
    
    def run_all_tests(self):
        """Run all tests in parallel"""
        all_test_options = self.test_config.get_all_test_options()
        total_test_types = len(all_test_options)
        
        total_sequences = len(self.test_config.test_sequences)
        
        print(f"Starting {self.n_repeat} tests with {self.max_workers} parallel workers")
        print(f"Test configuration: {self.test_config.test_name}")
        print(f"Base seed: {self.base_seed}")
        print(f"Available tests: {total_sequences} test sequences")
        print(f"Each test type has probability 1/{total_test_types} of being selected")
        
        # Setup directory structure
        self.setup_result_directory()
        
        # Generate test configurations
        configs = []
        for i in range(self.n_repeat):
            config = self.generate_test_config(i)
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
                    test_description = config['seq_config']['name']
                    print(f"Test {config['run_id']} generated exception: {e}")
                    results.append({
                        'run_id': config['run_id'], 
                        'status': 'exception', 
                        'test_seq': config['test_seq'],
                        'test_description': test_description,
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
            f.write(f"Test Summary Report\n")
            f.write(f"==================\n")
            f.write(f"Test Configuration: {self.test_config.test_name}\n")
            f.write(f"Total Tests: {len(results)}\n")
            f.write(f"Successful: {success_count}\n")
            f.write(f"Failed: {failed_count}\n")
            f.write(f"Errors: {error_count}\n")
            f.write(f"Base Seed: {self.base_seed}\n")
            f.write(f"Max Workers: {self.max_workers}\n\n")
            
            # Test sequence distribution
            total_sequences = len(self.test_config.test_sequences)
            
            f.write("Test Sequence Distribution:\n")
            f.write(f"  Total sequences: {total_sequences}\n")
            f.write(f"  Each sequence probability: 1/{total_sequences}\n\n")
            
            # Test description distribution
            desc_count = {}
            for r in results:
                desc = r.get('test_description', 'unknown')
                desc_count[desc] = desc_count.get(desc, 0) + 1
            
            f.write("Test Description Distribution:\n")
            for desc, count in sorted(desc_count.items()):
                f.write(f"  {desc}: {count}\n")
            f.write("\n")
            
            # Detailed results
            f.write("Detailed Results:\n")
            for r in sorted(results, key=lambda x: x['run_id']):
                f.write(f"  Run {r['run_id']:2d}: {r['status']:10s} - {r.get('test_description', 'unknown')}\n")
        
        print(f"\nTest Summary:")
        print(f"Total: {len(results)}, Success: {success_count}, Failed: {failed_count}, Errors: {error_count}")
        print(f"Summary report saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(description='Generic Parallel Test Runner with YAML Configuration Support')
    parser.add_argument('config_file', help='YAML configuration file containing test sequences and run commands')
    parser.add_argument('n_repeat', type=int, help='Number of tests to run')
    parser.add_argument('result_dir', help='Result directory path')
    parser.add_argument('--seed', type=int, default=42, help='Base seed for random number generation (default: 42)')
    parser.add_argument('--parallel', type=int, default=4, help='Number of parallel workers (default: 4)')
    
    args = parser.parse_args()
    
    if args.n_repeat <= 0:
        print("Error: n_repeat must be positive")
        sys.exit(1)
    
    if args.parallel <= 0:
        print("Error: parallel workers must be positive")
        sys.exit(1)
    
    runner = GenericParallelTestRunner(
        config_file=args.config_file,
        n_repeat=args.n_repeat,
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