#!/usr/bin/env python3
"""
通用自适应测试运行器：基于真实覆盖率数据的自适应测试运行器（包含runtime惩罚）
Usage: python3 generic_adaptive_runner.py <config_file> <batch_size> <total_batches> <initial_csv> <result_dir> [--category-mapping FILE] [--seed SEED] [--ignore-initial-coverage] [--parallel N] [--runtime-penalty-weight WEIGHT]
"""

import os
import sys
import random
import argparse
import subprocess
import shutil
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import signal
import threading
import pandas as pd
import numpy as np
from collections import defaultdict, deque
from tqdm import tqdm
import re
from glob import glob
import bs4
import yaml

pkg_pattern = re.compile(r'.*::')
trace = []

class TestConfig:
    """测试配置类，包含seq和对应的run_cmd信息"""
    def __init__(self, config_file):
        self.config_file = config_file
        self.test_sequences = []
        self.test_variants = []
        self.verisim_config = {}
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

            # 测试变体（如果存在）
            self.test_variants = config.get('test_variants', [])

            print(f"Loaded config for {self.test_name}")
            print(f"  Test sequences: {len(self.test_sequences)}")
            print(f"  Test variants: {len(self.test_variants)}")
            print(f"  Base command length: {len(self.base_run_cmd)}")

        except Exception as e:
            print(f"Error loading config file {self.config_file}: {e}")
            sys.exit(1)

    def get_all_test_identifiers(self):
        """获取所有测试标识符"""
        all_tests = []

        # 添加所有序列
        for seq_config in self.test_sequences:
            all_tests.append(seq_config['name'])

        return all_tests

    def select_random_test(self):
        """随机选择一个测试"""
        selected_seq_config = random.choice(self.test_sequences)

        return {
            'type': 'original',
            'seq': selected_seq_config.get('seq', selected_seq_config['name']),
            'seq_config': selected_seq_config,
            'variant': None
        }

    def parse_test_identifier(self, test_id):
        """解析测试标识符，返回测试配置"""
        # 查找对应的序列配置
        for seq_config in self.test_sequences:
            if seq_config['name'] == test_id:
                return {
                    'type': 'original',
                    'seq': seq_config.get('seq', seq_config['name']),
                    'seq_config': seq_config,
                    'variant': None
                }

        return None

    def is_valid_test_identifier(self, test_id):
        """验证测试标识符是否有效"""
        # 检查序列
        for seq_config in self.test_sequences:
            if seq_config['name'] == test_id:
                return True

        return False

    def extract_sequence_name_from_path(self, dashboard_path):
        """Extract sequence name from dashboard file path"""
        try:
            parent_dir = os.path.dirname(dashboard_path)

            # Check for test_config.txt or similar files that might contain sequence info
            for file in ['test_config.txt', 'cmd.txt']:
                config_file = os.path.join(parent_dir, file)
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        content = f.read()

                        # 首先检查变体
                        for variant in self.test_variants:
                            if 'detect_params' in variant:
                                if all(param in content for param in variant['detect_params']):
                                    return f"{variant['base_sequence']}[{variant['name']}]"

                        # 然后检查原始序列
                        for seq_config in self.test_sequences:
                            if seq_config['name'] in content:
                                return seq_config['name']

            # Fallback: extract from path structure if available
            path_parts = dashboard_path.split(os.sep)
            for part in path_parts:
                for seq_config in self.test_sequences:
                    if seq_config['name'] in part:
                        return seq_config['name']

            return 'unknown'
        except:
            return 'unknown'

class HTMLCoverageAnalyzer:
    def __init__(self, test_config, category_mapping_file=None):
        self.test_config = test_config
        self.category_mapping = self.load_category_mapping(category_mapping_file)
        self.category_order = self._get_category_order()
        # Regex patterns for HTML parsing
        self.cp_pattern = re.compile(r'<p class="summary_title">(CoverPoint|CoverCross) Details: (.*)</p>')
        self.t_pattern = re.compile(r'">([^/]+)</t[hd]>')
        self.legal_pattern = re.compile(r'.*/[cp][0-9]*.html')
        self.runtime_pattern = re.compile(r'Times for simulation: run (\d+.\d+)s')



    def load_category_mapping(self, mapping_file):
        """Load feature name to category mapping from clustering results CSV"""
        if not mapping_file or not Path(mapping_file).exists():
            print("Warning: No category mapping file provided")
            return {}

        category_mapping = {}
        try:
            import csv
            with open(mapping_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row_num, row in enumerate(reader, start=2):
                    try:
                        if len(row) >= 2:
                            feature_name = row[0].strip()
                            category_id_str = row[1].strip()

                            try:
                                category_id = int(category_id_str)
                                category_mapping[feature_name] = category_id
                            except ValueError:
                                print(f"Warning: Invalid category_id '{category_id_str}' at row {row_num}, skipping")
                                continue
                        else:
                            print(f"Warning: Row {row_num} has insufficient columns, skipping")
                            continue
                    except Exception as e:
                        print(f"Warning: Error processing row {row_num}: {e}, skipping")
                        continue

            print(f"Loaded category mapping for {len(category_mapping)} features from {mapping_file}")

        except Exception as e:
            print(f"Error loading category mapping: {e}")
            return {}

        return category_mapping

    def _get_category_order(self):
        """Get ordered list of categories for consistent vector indexing"""
        if not self.category_mapping:
            print("Warning: No category mapping available, no bins will be processed")
            return []

        # Get unique category IDs and sort them
        category_ids = sorted(set(self.category_mapping.values()))
        category_order = [f"category_{cat_id}" for cat_id in category_ids]

        return category_order

    def collect_bin_cnt(self, report_dir):
        """Collect bin counts from HTML coverage report"""
        bin_cnt = {}
        htmls = list(sorted(filter(lambda s: re.fullmatch(self.legal_pattern, s),
                                 glob(f'{report_dir}/report/*.html'))))

        for html in htmls:
            try:
                with open(html, 'r') as f:
                    soup = bs4.BeautifulSoup(f, 'html.parser')
                    segs = soup.find_all(lambda tag: tag.get("id") == 'coverageTable' or
                                       (tag.has_attr("class") and 'summary_title' in tag.get("class")))

                    cp_name = None
                    for seg in segs:
                        if seg.name == 'p':
                            m = self.cp_pattern.match(str(seg))
                            if m:
                                cp_name = m.group(2)
                                cp_name = pkg_pattern.sub('', cp_name)
                                cp_name = cp_name.replace('.', '-')
                        elif seg.name == 'table' and cp_name:
                            for child in seg.children:
                                if child.name == 'thead':
                                    th = '/'.join(self.t_pattern.findall(str(child)))
                                    if not th.startswith('Count/At Least/Bin Type/Bin Name/Database Covered'):
                                        break
                                elif child.name == 'tbody':
                                    for c in child.children:
                                        # parts = self.t_pattern.findall(str(c))
                                        parts = list(map(lambda td: td.get_text(strip=True), c.find_all('td')))
                                        if len(parts) >= 4:
                                            cnt = int(parts[0])
                                            bin_name = parts[3]
                                            key = f'{cp_name}-{bin_name}'
                                            bin_cnt[key] = cnt
            except Exception as e:
                print(f"Error processing HTML file {html}: {e}")
                continue

        return bin_cnt

    def process_single_test_data(self, dashboard_path):
        """Process a single test's coverage data from dashboard.html"""
        try:
            report_dir = os.path.dirname(dashboard_path)
            bin_cnt = self.collect_bin_cnt(report_dir)

            # Extract runtime
            log_file = os.path.join(report_dir, 'run.log')
            runtime = 0.0
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r') as f:
                        runtime_match = self.runtime_pattern.search(f.read())
                        if runtime_match:
                            runtime = float(runtime_match.group(1))
                except:
                    pass

            bin_cnt['runtime'] = runtime
            return bin_cnt
        except Exception as e:
            print(f"Error processing {dashboard_path}: {e}")
            return {}

    def compute_category_coverage_from_accumulated_data(self, accumulated_coverage_dict):
        """从累积覆盖率字典计算类别覆盖率统计，只处理在聚类文件中的bins"""
        category_stats = {}

        # 只处理在category mapping中存在的bins
        valid_bins = [col for col in accumulated_coverage_dict.keys()
                     if col not in ['run', 'runtime'] and not col.startswith('Unnamed')
                     and col in self.category_mapping]

        if not valid_bins:
            print("Warning: No valid bins found in category mapping")
            return category_stats

        # 根据映射将bins分组到类别
        category_bins = defaultdict(list)

        for bin_name in valid_bins:
            category_id = self.category_mapping.get(bin_name)
            if category_id is not None:
                category_name = f"category_{category_id}"
                category_bins[category_name].append(bin_name)

        # 计算每个类别的统计信息
        for category, bin_names in category_bins.items():
            total_bins = len(bin_names)
            covered_bins = 0

            # 如果bin在累积覆盖率中被击中至少一次，则认为被覆盖
            for bin_name in bin_names:
                if accumulated_coverage_dict.get(bin_name, 0) > 0:
                    covered_bins += 1

            uncovered_bins = total_bins - covered_bins
            coverage_percent = (covered_bins / total_bins * 100) if total_bins > 0 else 0.0

            category_stats[category] = {
                'total_bins': total_bins,
                'covered_bins': covered_bins,
                'uncovered_bins': uncovered_bins,
                'coverage_percent': coverage_percent,
                'priority_score': uncovered_bins,
                'bin_names': bin_names
            }

        return category_stats

    def find_worst_category(self, category_stats):
        """Find the category with the most uncovered bins"""
        if not category_stats:
            return None

        worst_category = max(category_stats.items(), key=lambda x: x[1]['priority_score'])

        return {
            'name': worst_category[0],
            'total_bins': worst_category[1]['total_bins'],
            'covered_bins': worst_category[1]['covered_bins'],
            'uncovered_bins': worst_category[1]['uncovered_bins'],
            'coverage_percent': worst_category[1]['coverage_percent'],
            'priority_score': worst_category[1]['priority_score'],
            'bin_names': worst_category[1]['bin_names']
        }

    def get_all_bin_names_ordered(self):
        """获取所有在聚类文件中的bin名称的有序列表"""
        if not hasattr(self, '_all_bin_names_ordered'):
            # 只从category mapping中收集bin名称
            if self.category_mapping:
                all_bins = set(self.category_mapping.keys())
                # 按字母顺序排序确保一致性
                self._all_bin_names_ordered = sorted(list(all_bins))
            else:
                self._all_bin_names_ordered = []
        return self._all_bin_names_ordered

    def create_full_coverage_vector(self, bin_cnt):
        """创建记录所有bin覆盖状态(0/1)的向量，只包含聚类文件中的bins"""
        all_bin_names = self.get_all_bin_names_ordered()
        coverage_vector = np.zeros(len(all_bin_names), dtype=int)

        for i, bin_name in enumerate(all_bin_names):
            # 如果bin被覆盖（计数>0），则标记为1，否则为0
            coverage_vector[i] = 1 if bin_cnt.get(bin_name, 0) > 0 else 0

        return coverage_vector

    def extract_category_vector(self, full_coverage_vector, category_name):
        """从完整覆盖率向量中提取特定category的向量"""
        all_bin_names = self.get_all_bin_names_ordered()
        category_indices = []

        # 找到属于该category的bin的索引
        for i, bin_name in enumerate(all_bin_names):
            category_id = self.category_mapping.get(bin_name)
            if category_id is not None:
                expected_category = f"category_{category_id}"
                if expected_category == category_name:
                    category_indices.append(i)

        # 提取对应的向量元素
        if category_indices:
            return full_coverage_vector[category_indices]
        else:
            return np.array([])

    def select_best_sequence_for_category_with_fallback(self, target_category, historical_data, runtime_data, k_samples_per_category=5, runtime_penalty_weight=0.3):
        """为目标类别选择最佳序列，基于category-specific向量距离和runtime惩罚，返回(selected_test_config, all_scores_zero)"""
        category_name = target_category['name']

        print(f"Selecting sequence for category: {category_name}")
        print(f"Historical data available for {len(historical_data)} sequences")

        # 获取所有历史向量
        all_historical_vectors = []
        for test_id, vectors in historical_data.items():
            all_historical_vectors.extend(vectors)

        print(f"Using {len(all_historical_vectors)} historical full coverage vectors")

        if not all_historical_vectors:
            print("No historical data available, using random selection")
            return self.test_config.select_random_test(), False

        # 从所有历史向量中提取目标category的向量
        category_historical_vectors = []
        for full_vector in all_historical_vectors:
            category_vector = self.extract_category_vector(full_vector, category_name)
            if len(category_vector) > 0:
                category_historical_vectors.append(category_vector)

        if not category_historical_vectors:
            print(f"No historical coverage found for category {category_name}")
            return self.test_config.select_random_test(), False

        # 从覆盖了目标category的向量中采样
        covering_vectors = []
        for category_vector in category_historical_vectors:
            if np.any(category_vector > 0):  # 该向量在目标category有覆盖
                covering_vectors.append(category_vector)

        sampling_features = []
        if covering_vectors:
            # 从覆盖目标category的向量中采样
            num_samples = min(k_samples_per_category, len(covering_vectors))
            sampled_vectors = random.choices(covering_vectors, k=num_samples)
            sampling_features.extend(sampled_vectors)
        else:
            # 如果没有覆盖目标category的向量，从所有category向量中采样
            num_samples = min(k_samples_per_category, len(category_historical_vectors))
            sampled_vectors = random.choices(category_historical_vectors, k=num_samples)
            sampling_features.extend(sampled_vectors)

        if not sampling_features:
            print("Warning: No sampling features available")
            return self.test_config.select_random_test(), False

        sampling_features = np.array(sampling_features)
        print(f"Built sampling set with {len(sampling_features)} category-specific vectors of length {sampling_features.shape[1]}")

        # 计算runtime惩罚系数
        runtime_penalties = {}
        all_test_ids = self.test_config.get_all_test_identifiers()

        if runtime_data:
            max_runtime = max(runtime_data.values()) if runtime_data.values() else 1.0
            for test_id in all_test_ids:
                avg_runtime = runtime_data.get(test_id, 0.0)
                # 标准化runtime到[0,1]，然后计算惩罚
                normalized_runtime = avg_runtime / max_runtime if max_runtime > 0 else 0.0
                runtime_penalties[test_id] = normalized_runtime
            print(f"Runtime penalties: {runtime_penalties}")
        else:
            for test_id in all_test_ids:
                runtime_penalties[test_id] = 0.0

        # 为每个序列计算SP分数，使用category-specific向量
        sequence_scores = {}

        for test_id in all_test_ids:
            if test_id in historical_data and len(historical_data[test_id]) > 0:
                # 提取该序列的category-specific向量
                sequence_category_vectors = []
                for full_vector in historical_data[test_id]:
                    category_vector = self.extract_category_vector(full_vector, category_name)
                    if len(category_vector) > 0:
                        sequence_category_vectors.append(category_vector)

                print(f"{test_id}: {len(sequence_category_vectors)} category-specific vectors")

                if not sequence_category_vectors:
                    sequence_scores[test_id] = 0.0
                    continue

            else:
                sequence_scores[test_id] = 0.0
                print(f"{test_id}: No historical data")
                continue

            # 计算category-specific向量到采样集合的距离
            distances = []
            for seq_category_vector in sequence_category_vectors:
                seq_distances = []
                for ensemble_vector in sampling_features:
                    # 计算category-specific向量间的距离
                    dist = np.linalg.norm(seq_category_vector - ensemble_vector)
                    seq_distances.append(dist)
                if seq_distances:
                    distances.append(seq_distances)

            if distances:
                all_distances = [d for seq_dist in distances for d in seq_dist]
                print(f"{test_id} {all_distances}")
                top_k = max(1, int(len(all_distances) * 0.1))
                top_distances = sorted(all_distances, reverse=True)[:top_k]
                base_score = np.mean(top_distances)

                # 应用runtime惩罚
                runtime_penalty = runtime_penalties.get(test_id, 0.0)
                final_score = base_score * (1.0 - runtime_penalty_weight * runtime_penalty)
                sequence_scores[test_id] = final_score

                print(f"{test_id}: base_score={base_score:.4f}, runtime_penalty={runtime_penalty:.4f}, final_score={final_score:.4f}")
            else:
                sequence_scores[test_id] = 0.0

        if not sequence_scores:
            return self.test_config.select_random_test(), False

        print(f"Sequence scores (with runtime penalty): {sequence_scores}")

        # 检查是否所有分数都为0
        all_scores_zero = all(score == 0.0 for score in sequence_scores.values())

        if all_scores_zero:
            print(f"WARNING: All sequence scores are 0 for category {category_name}")
            # 仍然返回一个序列（随机选择），但标记所有分数为0
            return self.test_config.select_random_test(), True

        best_test_id = max(sequence_scores.items(), key=lambda x: x[1])[0]
        print(f"Selected test: {best_test_id} (score: {sequence_scores[best_test_id]:.4f})")

        return self.test_config.parse_test_identifier(best_test_id), False


class GenericAdaptiveRunner:
    def __init__(self, config_file, batch_size, total_batches, initial_csv_file, result_dir, category_mapping_file=None,
                 seed=42, ignore_initial_coverage=False, max_workers=4, runtime_penalty_weight=0.3):
        self.config_file = config_file
        self.batch_size = batch_size
        self.total_batches = total_batches
        self.result_dir = Path(result_dir)
        self.seed = seed
        self.ignore_initial_coverage = ignore_initial_coverage
        self.max_workers = max_workers
        self.runtime_penalty_weight = runtime_penalty_weight
        self.entropy_weight = 0.2
        self.running_processes = []
        self.lock = threading.Lock()

        random.seed(seed)
        np.random.seed(seed)


        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self.runtime = 0.
        self.wall_start_time = None

        # 加载测试配置
        self.test_config = TestConfig(config_file)

        # 初始化覆盖率分析器
        self.coverage_analyzer = HTMLCoverageAnalyzer(self.test_config, category_mapping_file)

        # 累积覆盖率数据 - 使用字典格式便于操作
        self.accumulated_coverage = {}

        # 加载初始历史数据并初始化累积覆盖率
        self.historical_data = defaultdict(list)

        # 添加runtime跟踪
        self.sequence_runtimes = defaultdict(list)  # [test_identifier] -> list of runtimes
        self.active_sequence_count = defaultdict(int)
        self.recent_sequence_history = deque(maxlen=max(4, 2 * max_workers))

        self.dynamic_information_history = []
        self.latest_dynamic_information_snapshot = {}

        self.load_initial_historical_data(initial_csv_file)
        self.initial_category_entropy_importance = self.compute_category_entropy_importance()
        self.category_entropy_importance = self.compute_dynamic_category_entropy_importance()
        self.record_dynamic_information_snapshot(event='initial')

        # 批次历史和运行计数器
        self.batch_history = []
        self.completed_run_history = []
        self.overall_run_counter = 0

        # 添加：记录每个 sequence 的覆盖率增益历史
        self.sequence_gain_history = defaultdict(list)  # test_id → [gain1, gain2, ...]

        # 添加：记录每个 sequence 的运行次数（方便 UCB）
        self.sequence_run_count = defaultdict(int)      # test_id -> count

        # 添加：记录每个 category 的覆盖率增益历史（用于 UCB）
        self.category_gain_history = defaultdict(list)      # category_name → [gain1, gain2, ...]
        self.sequence_category_gain_history = defaultdict(lambda: defaultdict(list))
        self.sequence_category_run_count = defaultdict(lambda: defaultdict(int))
        self.category_successful_run_count = defaultdict(int)

        # 添加：记录每个 category 被选中的次数（用于 UCB）

        # Mutual-information correction across clusters. Each historical run
        # is mapped to an information-rich coverage state per cluster so MI
        # remains meaningful even when almost every run hits every cluster.
        self.pool_sharing_top_k = 5
        self.mutual_information_penalty_weight = 0.25
        self.mutual_information_min_samples = 8
        self.mutual_information_covered_bin_weight = 0.25
        self.mutual_information_high_quantile = 0.50
        self.recent_target_category_history = deque(maxlen=max(3, max_workers))
        self.latest_category_candidate_pools = {}
        self.pool_sharing_history = []
        self.mutual_information_history = []
        self.pool_backup_history = []
        self.cluster_candidate_pool_history = []
        self.log_flush_positions = {}
        self.pool_backup_stall_window = 3
        self.pool_backup_top_categories = 2

        # 用于记录每次选择前的 coverage 快照（在 run_all_batches 中使用）
        self.accumulated_coverage_snapshot = {}



    def compute_category_entropy_importance(self):
        """Compute a category information prior from initial simulation history."""
        vectors = [
            np.asarray(vector, dtype=float)
            for sequence_vectors in self.historical_data.values()
            for vector in sequence_vectors
        ]
        if not vectors:
            print("Warning: no initial history available; entropy prior is neutral")
            return {}

        matrix = np.vstack(vectors)
        bin_names = self.coverage_analyzer.get_all_bin_names_ordered()
        raw_scores = {}
        for category_name in self.coverage_analyzer.category_order:
            category_id = int(category_name.replace('category_', ''))
            indices = [
                index for index, bin_name in enumerate(bin_names)
                if self.coverage_analyzer.category_mapping.get(bin_name) == category_id
            ]
            if not indices:
                continue

            frequencies = (matrix[:, indices] > 0).mean(axis=0)
            information = -np.log(np.clip(frequencies, 1e-10, 1.0))
            raw_scores[category_name] = float(np.mean(information))

        positive_scores = [score for score in raw_scores.values() if score > 0]
        if not positive_scores:
            print("Warning: entropy scores are empty; entropy prior is neutral")
            return {}

        mean_score = float(np.mean(positive_scores))
        normalized = {
            category_name: float(np.clip(score / mean_score, 0.25, 4.0))
            for category_name, score in raw_scores.items()
        }
        print(f"Loaded initial-history entropy prior for {len(normalized)} categories")
        for category_name, score in sorted(normalized.items()):
            print(f"  {category_name}: entropy_importance={score:.4f}")
        return normalized

    def get_category_bin_names(self, category_name):
        """Return all tracked bin names that belong to a category."""
        try:
            category_id = int(category_name.replace('category_', ''))
        except ValueError:
            return []

        return [
            bin_name for bin_name in self.coverage_analyzer.get_all_bin_names_ordered()
            if self.coverage_analyzer.category_mapping.get(bin_name) == category_id
        ]

    def compute_dynamic_category_entropy_importance(self):
        """
        Compute dynamic category information weights from current accumulated coverage.

        The initial-history entropy prior captures historical rarity. The dynamic
        residual term captures how much information remains uncovered in the
        current run. Combining both keeps the original prior while allowing the
        score to decay as a category becomes covered.
        """
        residual_scores = {}
        coverage_state = {}
        for category_name in self.coverage_analyzer.category_order:
            bin_names = self.get_category_bin_names(category_name)
            if not bin_names:
                continue

            covered_bins = sum(
                1 for bin_name in bin_names
                if self.accumulated_coverage.get(bin_name, 0) > 0
            )
            total_bins = len(bin_names)

            # Low covered ratio means the category still carries more residual
            # information. Add-one smoothing keeps early scores finite.
            covered_ratio = (covered_bins + 1.0) / (total_bins + 1.0)
            residual_scores[category_name] = float(-np.log(np.clip(covered_ratio, 1e-10, 1.0)))
            coverage_state[category_name] = {
                'covered_bins': covered_bins,
                'total_bins': total_bins,
                'covered_ratio': covered_bins / total_bins if total_bins > 0 else 0.0,
                'smoothed_covered_ratio': covered_ratio,
            }

        positive_scores = [score for score in residual_scores.values() if score > 0]
        if positive_scores:
            mean_residual = float(np.mean(positive_scores))
            dynamic_residual = {
                category_name: float(np.clip(score / mean_residual, 0.25, 4.0))
                for category_name, score in residual_scores.items()
            }
        else:
            dynamic_residual = {
                category_name: 1.0
                for category_name in self.coverage_analyzer.category_order
            }
            mean_residual = 0.0

        combined = {}
        snapshot = {}
        for category_name in self.coverage_analyzer.category_order:
            initial_prior = self.initial_category_entropy_importance.get(category_name, 1.0)
            residual_prior = dynamic_residual.get(category_name, 1.0)
            combined[category_name] = float(np.clip(initial_prior * residual_prior, 0.25, 4.0))
            state = coverage_state.get(category_name, {})
            snapshot[category_name] = {
                'initial_prior': initial_prior,
                'residual_raw': residual_scores.get(category_name, 0.0),
                'residual_mean_positive': mean_residual,
                'residual_prior': residual_prior,
                'combined_prior': combined[category_name],
                'covered_bins': state.get('covered_bins', 0),
                'total_bins': state.get('total_bins', 0),
                'covered_ratio': state.get('covered_ratio', 0.0),
                'smoothed_covered_ratio': state.get('smoothed_covered_ratio', 0.0),
            }

        self.latest_dynamic_information_snapshot = snapshot

        return combined

    def record_dynamic_information_snapshot(self, event, run_id=None, test_identifier=None,
                                            target_category=None, run_info=None):
        """Append the current dynamic information prior of every category to memory."""
        target_category_name = target_category.get('name') if isinstance(target_category, dict) else target_category
        run_info = run_info or {}
        completed_runs = sum(self.sequence_run_count.values()) if hasattr(self, 'sequence_run_count') else 0
        timestamp = time.time()

        for category_name in self.coverage_analyzer.category_order:
            info = self.latest_dynamic_information_snapshot.get(category_name, {})
            self.dynamic_information_history.append({
                'timestamp': timestamp,
                'event': event,
                'run_id': run_id,
                'completed_runs': completed_runs,
                'runtime': self.runtime,
                'test_identifier': test_identifier,
                'target_category': target_category_name,
                'category': category_name,
                'initial_prior': info.get('initial_prior', 1.0),
                'residual_raw': info.get('residual_raw', 0.0),
                'residual_mean_positive': info.get('residual_mean_positive', 0.0),
                'residual_prior': info.get('residual_prior', 1.0),
                'combined_prior': info.get('combined_prior', self.category_entropy_importance.get(category_name, 1.0)),
                'dynamic_information_score': info.get('combined_prior', self.category_entropy_importance.get(category_name, 1.0)),
                'covered_bins': info.get('covered_bins', 0),
                'total_bins': info.get('total_bins', 0),
                'covered_ratio': info.get('covered_ratio', 0.0),
                'smoothed_covered_ratio': info.get('smoothed_covered_ratio', 0.0),
                'new_bins': run_info.get('new_bins', 0),
                'target_category_gain': run_info.get('target_category_gain', 0),
                'weighted_info_gain': run_info.get('weighted_info_gain', 0.0),
            })

    def update_dynamic_category_entropy_importance(self, event='update', run_id=None,
                                                   test_identifier=None, target_category=None,
                                                   run_info=None):
        """Refresh dynamic entropy weights after coverage feedback is applied."""
        self.category_entropy_importance = self.compute_dynamic_category_entropy_importance()
        self.record_dynamic_information_snapshot(
            event=event,
            run_id=run_id,
            test_identifier=test_identifier,
            target_category=target_category,
            run_info=run_info,
        )

    # ```python src/main.py
    def compute_category_gain(self, test_identifier, category_name):
        """Mean online newly-covered bins for this sequence and target category.

        Initial corpus vectors remain candidate-discovery priors; they are not
        UCB reward observations because they were not generated online.
        """
        by_category = self.sequence_category_gain_history.get(test_identifier, {})
        gains = by_category.get(category_name, [])
        return float(np.mean(gains)) if gains else 0.0

    def record_successful_ucb_feedback(self, result, context, run_info):
        """Update UCB reward/counts only for successful parsed online feedback."""
        if result.get('status') != 'success' or not run_info.get('processed', False):
            return False

        test_identifier = context['test_identifier']
        self.sequence_gain_history[test_identifier].append(run_info['new_bins'])
        self.sequence_run_count[test_identifier] += 1
        target_category = context.get('target_category')
        if target_category is not None:
            category_name = target_category['name']
            target_gain = run_info['target_category_gain']
            self.category_gain_history[category_name].append(target_gain)
            self.sequence_category_gain_history[test_identifier][category_name].append(target_gain)
            self.sequence_category_run_count[test_identifier][category_name] += 1
            self.category_successful_run_count[category_name] += 1
        return True
    def compute_ucb_scores(self, exploration_weight=1.0):
        """
        Compute UCB scores for all test sequences.

        Args:
            exploration_weight (float): 控制探索强度，越大越倾向于探索新 sequence

        Returns:
            dict: {test_id: ucb_score}
        """
        ucb_scores = {}
        total_runs = sum(self.sequence_run_count.values())  # successful online runs

        all_test_ids = self.test_config.get_all_test_identifiers()

        for test_id in all_test_ids:
            n_i = self.sequence_run_count[test_id]  # successful online runs
            gains = self.sequence_gain_history.get(test_id, [])

            if len(gains) == 0:
                # 从未运行过 → 给最高优先级
                ucb_scores[test_id] = float('inf')
            else:
                avg_gain = np.mean(gains)  # \bar{x}_i
                # UCB 公式
                ucb = avg_gain + exploration_weight * np.sqrt(np.log(total_runs + 1) / (n_i + 1e-8))
                ucb_scores[test_id] = ucb

        return ucb_scores

    def signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}, cleaning up...")
        self.flush_runtime_logs()
        self.cleanup_processes()
        sys.exit(1)

    def cleanup_processes(self):
        with self.lock:
            for proc in self.running_processes:
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except:
                            proc.kill()
                    except Exception as e:
                        try:
                            proc.kill()
                        except:
                            pass

    def load_initial_historical_data(self, csv_file_path):
        """加载初始历史数据并初始化累积覆盖率，只处理聚类文件中的bins"""
        try:
            df = pd.read_csv(csv_file_path)
            print(f"Loading initial data from {csv_file_path}")
            print(f"Found {len(df)} initial test records")
            print(f"Ignore initial coverage: {self.ignore_initial_coverage}")

            # 只处理在category mapping中存在的bin列
            all_columns = [col for col in df.columns if col not in ['run', 'runtime'] and not col.startswith('Unnamed')]
            valid_bin_columns = [col for col in all_columns if col in self.coverage_analyzer.category_mapping]

            print(f"Total columns in CSV: {len(all_columns)}")
            print(f"Valid bins in category mapping: {len(valid_bin_columns)}")
            print(f"Filtered out bins: {len(all_columns) - len(valid_bin_columns)}")

            if not valid_bin_columns:
                print("Warning: No valid bins found that match category mapping")
                return

            # 初始化累积覆盖率字典（只包含有效的bins）
            for col in valid_bin_columns:
                self.accumulated_coverage[col] = 0.0

            # 处理每一行数据
            for _, row in df.iterrows():
                if 'run' not in row or pd.isna(row['run']):
                    continue

                test_identifier = str(row['run']).strip()

                # 验证测试标识符是否有效
                if not self.test_config.is_valid_test_identifier(test_identifier):
                    print(f"Skipping invalid test identifier: {test_identifier}")
                    continue

                bin_cnt = {}
                for bin_name in valid_bin_columns:
                    if bin_name in row:
                        value = float(row[bin_name])
                        bin_cnt[bin_name] = value
                        # 如果不忽略初始覆盖率，则累加到总覆盖率
                        if not self.ignore_initial_coverage:
                            self.accumulated_coverage[bin_name] += value
                    else:
                        bin_cnt[bin_name] = 0.0

                # 跟踪runtime
                if 'runtime' in row and not pd.isna(row['runtime']):
                    runtime = float(row['runtime'])
                    self.sequence_runtimes[test_identifier].append(runtime)

                # 构建历史向量数据
                coverage_vector = self.coverage_analyzer.create_full_coverage_vector(bin_cnt)

                if np.any(coverage_vector > 0):
                    self.historical_data[test_identifier].append(coverage_vector)

            print(f"\nInitial Historical Data Loaded:")
            total_vectors = 0
            all_bin_names = self.coverage_analyzer.get_all_bin_names_ordered()
            for test_id, vectors in self.historical_data.items():
                print(f"  {test_id}: {len(vectors)} coverage vectors (length: {len(all_bin_names)})")
                total_vectors += len(vectors)
            print(f"Total: {total_vectors} full coverage vectors loaded (each vector length: {len(all_bin_names)})")

            # 显示初始runtime统计
            print(f"\nInitial Runtime Statistics:")
            for test_id, runtimes in self.sequence_runtimes.items():
                if runtimes:
                    avg_runtime = np.mean(runtimes)
                    print(f"  {test_id}: {avg_runtime:.2f}s average (from {len(runtimes)} runs)")

            # 计算并显示初始累积覆盖率
            initial_category_stats = self.coverage_analyzer.compute_category_coverage_from_accumulated_data(self.accumulated_coverage)
            total_bins = sum(stats['total_bins'] for stats in initial_category_stats.values())
            total_covered = sum(stats['covered_bins'] for stats in initial_category_stats.values())
            initial_coverage = (total_covered / total_bins * 100) if total_bins > 0 else 0.0

            if self.ignore_initial_coverage:
                print(f"\n*** Initial cumulative coverage: 0.00% (0/{total_bins} bins) - IGNORED INITIAL DATA ***")
                print("Note: Historical data loaded for decision making, but coverage starts from 0")
            else:
                print(f"\n*** Initial cumulative coverage: {initial_coverage:.2f}% ({total_covered}/{total_bins} bins) ***")
                print("Initial coverage by category:")
                for category, stats in initial_category_stats.items():
                    print(f"  {category}: {stats['coverage_percent']:.2f}% ({stats['covered_bins']}/{stats['total_bins']} bins)")

        except Exception as e:
            print(f"Error loading initial historical data: {e}")

    def setup_result_directory(self):
        print(f"Setting up result directory: {self.result_dir}")

        if self.result_dir.exists():
            shutil.rmtree(self.result_dir)

        self.result_dir.mkdir(parents=True, exist_ok=True)
        (self.result_dir / 'batches').mkdir(exist_ok=True)
        (self.result_dir / 'logs').mkdir(exist_ok=True)
        self.log_flush_positions = {}
        self.flush_runtime_logs()

    def log_vericov_trace(self, message):
        """Print and persist Vericov diagnostics for post-run debugging."""
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        try:
            logs_dir = self.result_dir / 'logs'
            logs_dir.mkdir(parents=True, exist_ok=True)
            with open(logs_dir / 'vericov_trace.log', 'a') as f:
                f.write(line + '\n')
        except Exception as e:
            print(f"[vericov] Warning: failed to write vericov_trace.log: {e}")

    def cleanup_large_run_logs(self, run_dir):
        """Remove large per-run simulator logs after required data has been parsed."""
        run_dir = Path(run_dir)
        for log_name in ('run.log', 'verisim.log'):
            log_path = run_dir / log_name
            try:
                if log_path.exists():
                    size_mb = log_path.stat().st_size / (1024 * 1024)
                    log_path.unlink()
                    self.log_vericov_trace(f"[cleanup] Removed {log_path} ({size_mb:.2f} MB)")
            except Exception as e:
                self.log_vericov_trace(f"[cleanup] Warning: failed to remove {log_path}: {e}")

    def flush_runtime_logs(self):
        """Append newly collected scheduler records to CSV files."""
        logs_dir = self.result_dir / 'logs'
        if not logs_dir.exists():
            return

        log_specs = [
            (
                'trace',
                trace,
                self.result_dir / 'trace.csv',
                ['runtime', 'covered'],
            ),
            (
                'dynamic_information',
                self.dynamic_information_history,
                logs_dir / 'dynamic_information_trace.csv',
                [
                    'timestamp', 'event', 'run_id', 'completed_runs', 'runtime',
                    'test_identifier', 'target_category', 'category',
                    'initial_prior', 'residual_raw', 'residual_mean_positive',
                    'residual_prior', 'combined_prior', 'dynamic_information_score',
                    'covered_bins', 'total_bins', 'covered_ratio',
                    'smoothed_covered_ratio', 'new_bins', 'target_category_gain',
                    'weighted_info_gain',
                ],
            ),
            (
                'mi_adjusted_selection',
                self.pool_sharing_history,
                logs_dir / 'pool_sharing_trace.csv',
                [
                    'timestamp', 'event', 'selected_category', 'category',
                    'raw_ucb', 'adjusted_ucb', 'reference_category',
                    'mutual_information', 'normalized_mutual_information',
                    'mutual_information_penalty', 'candidate_pool',
                ],
            ),
            (
                'mutual_information',
                self.mutual_information_history,
                logs_dir / 'mutual_information_trace.csv',
                [
                    'timestamp', 'event', 'completed_runs', 'runtime', 'category',
                    'reference_category', 'sample_count', 'mutual_information',
                    'normalized_mutual_information', 'entropy_a', 'entropy_b',
                    'state_cardinality_a', 'state_cardinality_b',
                ],
            ),
            (
                'pool_backup',
                self.pool_backup_history,
                logs_dir / 'pool_backup_trace.csv',
                ['timestamp', 'target_category', 'source_categories', 'backup_sequences'],
            ),
            (
                'cluster_candidate_pool',
                self.cluster_candidate_pool_history,
                logs_dir / 'cluster_candidate_pool_trace.csv',
                [
                    'timestamp', 'event', 'completed_runs', 'runtime', 'category',
                    'rank', 'test_identifier', 'pool_weight',
                    'dynamic_information_score',
                ],
            ),
        ]

        for log_key, records, path, columns in log_specs:
            if not path.exists():
                pd.DataFrame(columns=columns).to_csv(path, index=False)

            start = self.log_flush_positions.get(log_key, 0)
            if start > len(records):
                start = 0
            new_records = records[start:]
            if new_records:
                pd.DataFrame(new_records).reindex(columns=columns).to_csv(
                    path,
                    mode='a',
                    header=False,
                    index=False,
                )
            self.log_flush_positions[log_key] = len(records)

    def get_current_coverage_stats(self):
        """获取当前累积覆盖率统计"""
        category_stats = self.coverage_analyzer.compute_category_coverage_from_accumulated_data(self.accumulated_coverage)
        total_bins = sum(stats['total_bins'] for stats in category_stats.values())
        total_covered = sum(stats['covered_bins'] for stats in category_stats.values())
        overall_coverage = (total_covered / total_bins * 100) if total_bins > 0 else 0.0

        return overall_coverage, total_covered, total_bins, category_stats

    def get_average_runtimes(self):
        """计算每个序列的平均runtime"""
        avg_runtimes = {}
        for test_id, runtimes in self.sequence_runtimes.items():
            if runtimes:
                avg_runtimes[test_id] = np.mean(runtimes)
            else:
                avg_runtimes[test_id] = 0.0
        return avg_runtimes

    def build_run_command(self, test_config, run_id, seed, run_dir, target_cg=None):
        """根据测试配置构建运行命令"""
        seq_config = test_config['seq_config']
        variant = test_config.get('variant')

        # 从基础命令模板开始
        cmd = self.test_config.base_run_cmd.copy()

        # 替换占位符
        verisim_config = self.test_config.verisim_config

        # 构建概率文件路径
        prob_file = verisim_config.get('dummy_prob_file', '')
        if target_cg is not None:
            prob_file_template = verisim_config.get('prob_file_template', '')
            if prob_file_template:
                prob_file = prob_file_template.replace('{test_seq}', test_config['seq']).replace('{target_cg}', str(target_cg))
                if not Path(prob_file).exists():
                    prob_file = verisim_config.get('dummy_prob_file', '')

        for i, arg in enumerate(cmd):
            if '{verisim_home}' in arg:
                cmd[i] = arg.replace('{verisim_home}', verisim_config.get('verisim_home', ''))
            if '{image_dir}' in arg:
                cmd[i] = arg.replace('{image_dir}', verisim_config.get('image_dir', ''))
            if '{test_name}' in arg:
                cmd[i] = arg.replace('{test_name}', verisim_config.get('test_name', ''))
            if '{test_seq}' in arg:
                cmd[i] = arg.replace('{test_seq}', test_config['seq'])
            if '{seed}' in arg:
                cmd[i] = arg.replace('{seed}', str(seed))
            if '{run_dir}' in arg:
                cmd[i] = arg.replace('{run_dir}', str(run_dir.absolute()))
            if '{prob_file}' in arg:
                cmd[i] = arg.replace('{prob_file}', prob_file)

        # 添加序列特定的额外参数
        additional_params = seq_config.get('additional_params', [])
        if additional_params:
            cmd.extend(additional_params)

        return cmd

    def run_single_test(self, run_id, test_config, seed, batch_dir, target_category=None):
        test_type = test_config['type']
        test_seq = test_config['seq']
        variant = test_config.get('variant')

        if test_type == 'variant':
            print(f"Starting test {run_id}: {test_seq} [{variant['name']}] (seed: {seed})")
            test_description = f"{test_seq}[{variant['name']}]"
        else:
            print(f"Starting test {run_id}: {test_seq} (seed: {seed})")
            test_description = test_seq

        try:
            run_dir = batch_dir / str(run_id)
            run_dir.mkdir(exist_ok=True)

            target_cg = None
            if target_category and target_category.get('name'):
                target_cg = int(str(target_category['name']).replace('category_', ''))

            # 构建运行命令
            cmd = self.build_run_command(test_config, run_id, seed, run_dir, target_cg)

            with open(run_dir / 'cmd.txt', 'w') as f:
                f.write(' '.join(cmd) + '\n')

            with open(run_dir / 'test_config.txt', 'w') as f:
                f.write(f"Run ID: {run_id}\n")
                f.write(f"Seed: {seed}\n")
                f.write(f"Test Type: {test_type}\n")
                f.write(f"Test Sequence: {test_seq}\n")
                if variant:
                    f.write(f"Variant: {variant['name']}\n")
                    f.write(f"Variant Params: {' '.join(variant.get('params', []))}\n")
                f.write(f"Base Seed: {self.seed}\n")
                f.write(f"Target Category: {target_cg}\n")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(run_dir),
                preexec_fn=os.setsid
            )

            with self.lock:
                self.running_processes.append(process)

            stdout, _ = process.communicate()

            with self.lock:
                if process in self.running_processes:
                    self.running_processes.remove(process)

            with open(run_dir / 'run.log', 'w') as f:
                f.write(stdout)

            with open(run_dir / 'python_runner.log', 'w') as f:
                f.write(f"Test {run_id} completed\n")
                f.write(f"Test Type: {test_type}\n")
                f.write(f"Test Sequence: {test_seq}\n")
                if variant:
                    f.write(f"Variant: {variant['name']}\n")
                f.write(f"Seed: {seed}\n")
                f.write(f"Target Category: {target_cg}\n")
                f.write(f"Return Code: {process.returncode}\n")
                f.write(f"Working Directory: {run_dir}\n")

            if process.returncode == 0:
                print(f"Test {run_id} completed successfully")
                return {
                    'run_id': run_id,
                    'status': 'success',
                    'test_config': test_config,
                    'test_description': test_description,
                    'coverage_db': run_dir / 'coverage.zdb'
                }
            else:
                print(f"Test {run_id} failed with return code {process.returncode}")
                return {
                    'run_id': run_id,
                    'status': 'failed',
                    'test_config': test_config,
                    'test_description': test_description,
                    'return_code': process.returncode
                }

        except Exception as e:
            print(f"Error running test {run_id}: {e}")
            return {
                'run_id': run_id,
                'status': 'error',
                'test_config': test_config,
                'test_description': test_description,
                'error': str(e)
            }

    def run_batch(self, batch_num, test_config):
        print(f"\n=== Running Batch {batch_num + 1}/{self.total_batches} ===")
        if test_config['type'] == 'variant':
            print(f"Test: {test_config['seq']} [{test_config['variant']['name']}]")
        else:
            print(f"Test Sequence: {test_config['seq']}")
        print(f"Batch Size: {self.batch_size}")

        batch_dir = self.result_dir / 'batches' / f'batch_{batch_num}'
        batch_dir.mkdir(parents=True, exist_ok=True)

        seed_generator = random.Random(self.seed)


        skip_count = self.overall_run_counter
        for _ in range(skip_count):
            seed_generator.randint(1, 2**31 - 1)
            self.test_config.select_random_test()  # 保持一致性

        batch_seeds = []
        for i in range(self.batch_size):
            seed = seed_generator.randint(1, 2**31 - 1)
            self.test_config.select_random_test()  # 跳过测试选择调用以保持一致性
            batch_seeds.append(seed)

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i in range(self.batch_size):
                run_id = self.overall_run_counter + i
                future = executor.submit(self.run_single_test, run_id, test_config, batch_seeds[i], batch_dir)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"Test generated exception: {e}")

        self.overall_run_counter += self.batch_size

        batch_summary = {
            'batch_num': batch_num,
            'test_config': test_config,
            'batch_size': self.batch_size,
            'seeds': batch_seeds,
            'results': results,
            'timestamp': time.time()
        }

        with open(batch_dir / 'batch_summary.json', 'w') as f:
            json.dump(batch_summary, f, indent=2, default=str)

        return results

    def generate_html_reports(self, batch_num):
        """Generate HTML coverage reports for all tests in the batch using vericov"""
        batch_dir = self.result_dir / 'batches' / f'batch_{batch_num}'
        vericov_cmd_template = self.test_config.verisim_config.get('vericov_cmd', [])

        # Find all coverage.zdb files in the batch
        coverage_dbs = []
        for run_dir in batch_dir.iterdir():
            if run_dir.is_dir() and run_dir.name.isdigit():
                coverage_db = run_dir / 'coverage.zdb'
                if coverage_db.exists():
                    coverage_dbs.append(coverage_db)

        if not coverage_dbs:
            print(f"Warning: No coverage databases found for batch {batch_num}")
            return False

        print(f"Generating HTML reports for {len(coverage_dbs)} tests in batch {batch_num}")

        # Generate individual HTML reports for each test
        for coverage_db in tqdm(coverage_dbs, desc="Generating HTML reports"):
            run_dir = coverage_db.parent

            # 构建vericov命令
            vericov_cmd = []
            for part in vericov_cmd_template:
                if '{coverage_db}' in part:
                    vericov_cmd.append(part.replace('{coverage_db}', str(coverage_db)))
                elif '{run_dir}' in part:
                    vericov_cmd.append(part.replace('{run_dir}', str(run_dir)))
                else:
                    vericov_cmd.append(part)

            try:
                result = subprocess.run(vericov_cmd, capture_output=True, text=True, timeout=300)

                if result.returncode == 0:
                    # Create dashboard.html file if it doesn't exist
                    dashboard_file = run_dir / 'dashboard.html'
                    report_dir = run_dir / 'report'
                    if report_dir.exists() and not dashboard_file.exists():
                        # Create a simple dashboard.html
                        with open(dashboard_file, 'w') as f:
                            f.write(f'<html><head><title>Coverage Report</title></head>')
                            f.write(f'<body><h1>Coverage Report</h1>')
                            f.write(f'<p>Report generated for {run_dir.name}</p>')
                            f.write(f'</body></html>')
                else:
                    print(f"Warning: vericov failed for {coverage_db}")

            except subprocess.TimeoutExpired:
                print(f"Warning: vericov timed out for {coverage_db}")
            except Exception as e:
                print(f"Warning: Error running vericov for {coverage_db}: {e}")

        return True

    def update_accumulated_coverage(self, batch_num):
        """Update accumulated coverage with current batch results"""
        # Find all dashboard.html files in the batch
        dashboard_files = glob(f'{self.result_dir}/batches/batch_{batch_num}/**/dashboard.html', recursive=True)

        for dashboard_file in dashboard_files:
            bin_cnt = self.coverage_analyzer.process_single_test_data(dashboard_file)

            if 'runtime' in bin_cnt:
                self.runtime += bin_cnt['runtime']
                del bin_cnt['runtime']  # Remove runtime from bin counts

            # 只更新在category mapping中存在的bins
            for bin_name, count in bin_cnt.items():
                if bin_name in self.coverage_analyzer.category_mapping:
                    if bin_name in self.accumulated_coverage:
                        self.accumulated_coverage[bin_name] += count
                    else:
                        self.accumulated_coverage[bin_name] = count

        print(f"Updated accumulated coverage with batch {batch_num} results")

    def update_historical_data_with_batch(self, test_identifier, batch_num):
        """Update historical data with batch results"""
        # Find all dashboard.html files in the batch
        dashboard_files = glob(f'{self.result_dir}/batches/batch_{batch_num}/**/dashboard.html', recursive=True)

        for dashboard_file in dashboard_files:
            bin_cnt = self.coverage_analyzer.process_single_test_data(dashboard_file)

            # 跟踪runtime
            if 'runtime' in bin_cnt:
                runtime = bin_cnt['runtime']
                self.sequence_runtimes[test_identifier].append(runtime)
                del bin_cnt['runtime']  # Remove runtime from bin counts

            # 只保留在category mapping中存在的bins
            filtered_bin_cnt = {bin_name: count for bin_name, count in bin_cnt.items()
                               if bin_name in self.coverage_analyzer.category_mapping}

            # Create full coverage vector (0/1 format)
            coverage_vector = self.coverage_analyzer.create_full_coverage_vector(filtered_bin_cnt)

            if np.any(coverage_vector > 0):
                self.historical_data[test_identifier].append(coverage_vector)


        print(f"Updated {test_identifier} with {len(dashboard_files)} new coverage vectors from batch {batch_num}")

    def generate_html_report_for_run(self, run_dir):
        """Generate an HTML coverage report for a single completed run."""
        run_dir = Path(run_dir)
        self.log_vericov_trace(f"[vericov] Start HTML generation for run_dir: {run_dir}")
        self.log_vericov_trace(f"[vericov] run_dir exists: {run_dir.exists()}")

        coverage_db = run_dir / 'coverage.zdb'
        self.log_vericov_trace(f"[vericov] Expected coverage DB: {coverage_db}")
        if not coverage_db.exists():
            self.log_vericov_trace("[vericov] Expected coverage DB not found; searching recursively under run_dir")
            candidates = sorted(run_dir.glob('**/coverage.zdb'))
            if not candidates:
                self.log_vericov_trace(f"Warning: No coverage database found for run {run_dir}")
                return None
            coverage_db = candidates[0]
            self.log_vericov_trace(f"[vericov] Using fallback coverage DB: {coverage_db}")
        else:
            self.log_vericov_trace(f"[vericov] Found coverage DB: {coverage_db}")

        vericov_cmd_template = self.test_config.verisim_config.get('vericov_cmd', [])
        if not vericov_cmd_template:
            self.log_vericov_trace("Warning: vericov_cmd is empty; cannot generate HTML report")
            return None

        vericov_cmd = []
        for part in vericov_cmd_template:
            if '{coverage_db}' in part:
                vericov_cmd.append(part.replace('{coverage_db}', str(coverage_db)))
            elif '{run_dir}' in part:
                vericov_cmd.append(part.replace('{run_dir}', str(run_dir)))
            else:
                vericov_cmd.append(part)

        self.log_vericov_trace(f"[vericov] Command: {' '.join(vericov_cmd)}")
        try:
            result = subprocess.run(vericov_cmd, capture_output=True, text=True, timeout=300)
            self.log_vericov_trace(f"[vericov] Return code: {result.returncode}")
            if result.stdout:
                self.log_vericov_trace(f"[vericov] stdout: {result.stdout.strip()[:1000]}")
            if result.stderr:
                self.log_vericov_trace(f"[vericov] stderr: {result.stderr.strip()[:1000]}")
            with open(run_dir / 'vericov.log', 'w') as f:
                f.write('Command: ' + ' '.join(vericov_cmd) + '\n')
                f.write(f'Return Code: {result.returncode}\n\n')
                f.write('STDOUT:\n')
                f.write(result.stdout or '')
                f.write('\n\nSTDERR:\n')
                f.write(result.stderr or '')
            if result.returncode != 0:
                self.log_vericov_trace(f"Warning: vericov failed for {coverage_db}")
                if result.stderr:
                    self.log_vericov_trace(result.stderr.strip())
                return None
        except subprocess.TimeoutExpired:
            self.log_vericov_trace(f"Warning: vericov timed out for {coverage_db}")
            return None
        except Exception as e:
            self.log_vericov_trace(f"Warning: Error running vericov for {coverage_db}: {e}")
            return None

        dashboard_file = run_dir / 'dashboard.html'
        report_dir = run_dir / 'report'
        report_htmls = list(report_dir.glob('*.html')) if report_dir.exists() else []
        all_htmls = sorted(run_dir.glob('**/*.html'))
        self.log_vericov_trace(f"[vericov] Expected dashboard: {dashboard_file}")
        self.log_vericov_trace(f"[vericov] report_dir exists: {report_dir.exists()}, report html count: {len(report_htmls)}")
        if all_htmls:
            self.log_vericov_trace("[vericov] HTML files found:")
            for html in all_htmls[:10]:
                self.log_vericov_trace(f"[vericov]   {html}")
            if len(all_htmls) > 10:
                self.log_vericov_trace(f"[vericov]   ... {len(all_htmls) - 10} more")
        else:
            self.log_vericov_trace(f"[vericov] No HTML files found under {run_dir}")

        if report_htmls and not dashboard_file.exists():
            with open(dashboard_file, 'w') as f:
                f.write(f'<html><head><title>Coverage Report</title></head>')
                f.write(f'<body><h1>Coverage Report</h1>')
                f.write(f'<p>Report generated for {run_dir.name}</p>')
                f.write(f'</body></html>')
            self.log_vericov_trace(f"[vericov] Created dashboard placeholder: {dashboard_file}")

        if dashboard_file.exists():
            self.log_vericov_trace(f"[vericov] HTML generation ready: {dashboard_file}")
            return dashboard_file

        self.log_vericov_trace(f"Warning: vericov finished but no HTML report was found under {run_dir}")
        return None

    def calculate_incremental_info(self, before_snapshot, bin_cnt, target_category):
        """Calculate coverage information gained by one completed run."""
        category_stats = self.coverage_analyzer.compute_category_coverage_from_accumulated_data(before_snapshot)
        new_bins = []
        target_category_name = target_category['name'] if target_category else None

        for bin_name, count in bin_cnt.items():
            if count <= 0 or bin_name not in self.coverage_analyzer.category_mapping:
                continue
            if before_snapshot.get(bin_name, 0) <= 0:
                new_bins.append(bin_name)

        target_category_gain = 0
        weighted_info_gain = 0.0
        for bin_name in new_bins:
            category_id = self.coverage_analyzer.category_mapping.get(bin_name)
            category_name = f"category_{category_id}"
            if category_name == target_category_name:
                target_category_gain += 1

            stats = category_stats.get(category_name)
            if stats and stats['total_bins'] > 0:
                uncovered_ratio = stats['uncovered_bins'] / stats['total_bins']
            else:
                uncovered_ratio = 1.0
            weighted_info_gain += 1.0 + uncovered_ratio

        return {
            'new_bins': len(new_bins),
            'target_category_gain': target_category_gain,
            'weighted_info_gain': weighted_info_gain,
            'new_bin_names': new_bins
        }

    def process_completed_run(self, result, context):
        """Process one finished simulation and update coverage/history state."""
        info = {
            'new_bins': 0,
            'target_category_gain': 0,
            'weighted_info_gain': 0.0,
            'new_bin_names': [],
            'runtime': 0.0,
            'processed': False
        }

        if result.get('status') != 'success':
            self.cleanup_large_run_logs(context['run_dir'])
            return info

        run_dir = context['run_dir']
        self.log_vericov_trace(f"[coverage] Successful run {context['run_id']} completed; generating HTML from {run_dir}")
        dashboard_file = self.generate_html_report_for_run(run_dir)
        if dashboard_file is None:
            self.cleanup_large_run_logs(run_dir)
            self.log_vericov_trace(f"[coverage] Skip coverage update for run {context['run_id']}: no dashboard.html")
            return info

        bin_cnt = self.coverage_analyzer.process_single_test_data(str(dashboard_file))
        self.cleanup_large_run_logs(run_dir)
        runtime = float(bin_cnt.pop('runtime', 0.0))
        info['runtime'] = runtime
        self.runtime += runtime
        self.sequence_runtimes[context['test_identifier']].append(runtime)

        filtered_bin_cnt = {
            bin_name: count for bin_name, count in bin_cnt.items()
            if bin_name in self.coverage_analyzer.category_mapping
        }

        before_update = dict(self.accumulated_coverage)
        info.update(self.calculate_incremental_info(before_update, filtered_bin_cnt, context['target_category']))

        for bin_name, count in filtered_bin_cnt.items():
            if bin_name in self.accumulated_coverage:
                self.accumulated_coverage[bin_name] += count
            else:
                self.accumulated_coverage[bin_name] = count

        coverage_vector = self.coverage_analyzer.create_full_coverage_vector(filtered_bin_cnt)
        if np.any(coverage_vector > 0):
            self.historical_data[context['test_identifier']].append(coverage_vector)

        self.update_dynamic_category_entropy_importance(
            event='completed_run',
            run_id=context.get('run_id'),
            test_identifier=context.get('test_identifier'),
            target_category=context.get('target_category'),
            run_info=info,
        )
        info['processed'] = True
        return info

    def reset_pending_info(self):
        return {
            'pending_new_bins': 0,
            'pending_target_category_gain': 0,
            'pending_weighted_info_gain': 0.0,
            'pending_completed_tests': 0
        }

    def is_sequence_repetition_blocked(self, test_identifier):
        """Allow repeat selections when UCB continues to rank the same sequence first."""
        return False
    def should_refresh_sequence_for_repetition(self, test_identifier):
        """Return True when the current sequence should be re-scored to avoid repetition."""
        return self.is_sequence_repetition_blocked(test_identifier)

    def should_trigger_reselection(self, pending_info):
        """Rescore after each completion so zero-gain feedback affects UCB promptly."""
        return pending_info['pending_completed_tests'] > 0

    def get_test_identifier(self, selected_test_config):
        if selected_test_config['type'] == 'variant':
            return f"{selected_test_config['seq']}[{selected_test_config['variant']['name']}]"
        return selected_test_config['seq']

    def submit_next_test(self, executor, run_id, test_config, test_identifier, target_category, seed):
        logical_batch_id = run_id // self.batch_size
        batch_dir = self.result_dir / 'batches' / f'batch_{logical_batch_id}'
        batch_dir.mkdir(parents=True, exist_ok=True)
        before_coverage, before_covered, before_total, _ = self.get_current_coverage_stats()

        context = {
            'run_id': run_id,
            'run_dir': batch_dir / str(run_id),
            'test_config': test_config,
            'test_identifier': test_identifier,
            'target_category': target_category,
            'before_snapshot': dict(self.accumulated_coverage),
            'before_coverage': before_coverage,
            'before_covered': before_covered,
            'before_total': before_total,
            'seed': seed,
            'logical_batch_id': logical_batch_id
        }
        future = executor.submit(self.run_single_test, run_id, test_config, seed, batch_dir, target_category)
        return future, context

    def record_cluster_candidate_pool(self, category_name, pool, event='pool_build'):
        """Record the tests that a cluster currently depends on."""
        timestamp = time.time()
        completed_runs = sum(self.sequence_run_count.values()) if hasattr(self, 'sequence_run_count') else 0
        for rank, (test_id, weight) in enumerate(
            sorted(pool.items(), key=lambda item: item[1], reverse=True),
            start=1,
        ):
            self.cluster_candidate_pool_history.append({
                'timestamp': timestamp,
                'event': event,
                'completed_runs': completed_runs,
                'runtime': self.runtime,
                'category': category_name,
                'rank': rank,
                'test_identifier': test_id,
                'pool_weight': weight,
                'dynamic_information_score': self.category_entropy_importance.get(category_name, 1.0),
            })

    def build_candidate_pool_for_category(self, category_name, all_test_ids=None, top_k=None, log_event='pool_build'):
        """Build a weighted top-K sequence pool for one target category."""
        all_test_ids = all_test_ids or self.test_config.get_all_test_identifiers()
        top_k = top_k or self.pool_sharing_top_k
        candidate_sequences = []

        for test_id in all_test_ids:
            has_hit = False
            for vec in self.historical_data.get(test_id, []):
                cat_vec = self.coverage_analyzer.extract_category_vector(vec, category_name)
                if len(cat_vec) > 0 and np.any(cat_vec > 0):
                    has_hit = True
                    break
            if has_hit:
                candidate_sequences.append(test_id)

        if not candidate_sequences:
            candidate_sequences = list(all_test_ids)

        raw_scores = {}
        total_runs = sum(self.sequence_category_run_count[test_id][category_name] for test_id in all_test_ids)
        avg_runtimes = self.get_average_runtimes()
        positive_runtimes = [runtime for runtime in avg_runtimes.values() if runtime > 0]
        max_runtime = max(positive_runtimes) if positive_runtimes else 1.0

        for test_id in candidate_sequences:
            avg_gain = float(self.compute_category_gain(test_id, category_name))
            n_i = self.sequence_category_run_count[test_id][category_name]
            if n_i == 0:
                exploration = np.sqrt(np.log(total_runs + 2))
            else:
                exploration = np.sqrt(np.log(total_runs + 1) / (n_i + 1e-8))

            runtime = avg_runtimes.get(test_id, 0.0)
            norm_runtime = runtime / max_runtime if max_runtime > 0 else 0.0
            runtime_factor = max(0.0, 1.0 - self.runtime_penalty_weight * norm_runtime)
            raw_scores[test_id] = max(0.0, (avg_gain + exploration) * runtime_factor)

        ranked = sorted(raw_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        max_score = max((score for _, score in ranked), default=0.0)
        if max_score <= 0:
            pool = {test_id: 1.0 for test_id, _ in ranked}
            self.record_cluster_candidate_pool(category_name, pool, event=log_event)
            return pool

        pool = {
            test_id: float(score / max_score)
            for test_id, score in ranked
            if score > 0
        }
        self.record_cluster_candidate_pool(category_name, pool, event=log_event)
        return pool

    def build_cluster_information_states(self, category_names=None):
        """Build aligned discrete cluster states for empirical MI.

        A run's cluster score is the sum of self-information weights of the
        bins it hits. Scores are discretized into no, low, and high information
        states. Already-covered bins are down-weighted so the states adapt as
        closure progresses without making all historical observations zero.
        """
        category_names = category_names or self.coverage_analyzer.category_order
        bin_names = self.coverage_analyzer.get_all_bin_names_ordered()
        vectors = [
            np.asarray(vector, dtype=float)
            for sequence_vectors in self.historical_data.values()
            for vector in sequence_vectors
            if len(vector) == len(bin_names)
        ]
        if not vectors:
            return {
                category_name: np.array([], dtype=np.int8)
                for category_name in category_names
            }

        matrix = (np.vstack(vectors) > 0).astype(float)
        frequencies = matrix.mean(axis=0)
        self_information = -np.log(np.clip(frequencies, 1e-10, 1.0))
        residual_multiplier = np.asarray([
            1.0
            if self.accumulated_coverage.get(bin_name, 0) <= 0
            else self.mutual_information_covered_bin_weight
            for bin_name in bin_names
        ], dtype=float)
        bin_weights = self_information * residual_multiplier

        states = {}
        for category_name in category_names:
            try:
                category_id = int(category_name.replace('category_', ''))
            except ValueError:
                states[category_name] = np.zeros(len(vectors), dtype=np.int8)
                continue

            category_indices = [
                index
                for index, bin_name in enumerate(bin_names)
                if self.coverage_analyzer.category_mapping.get(bin_name) == category_id
            ]
            if not category_indices:
                states[category_name] = np.zeros(len(vectors), dtype=np.int8)
                continue

            information_scores = matrix[:, category_indices] @ bin_weights[category_indices]
            positive_scores = information_scores[information_scores > 0]
            category_states = np.zeros(len(vectors), dtype=np.int8)
            if len(positive_scores) > 0:
                high_threshold = float(np.quantile(
                    positive_scores,
                    self.mutual_information_high_quantile,
                ))
                category_states[information_scores > 0] = 1
                category_states[information_scores > high_threshold] = 2
            states[category_name] = category_states

        return states

    def empirical_mutual_information(self, states_a, states_b):
        """Return empirical MI in nats and entropy-normalized MI."""
        states_a = np.asarray(states_a, dtype=np.int8)
        states_b = np.asarray(states_b, dtype=np.int8)
        sample_count = min(len(states_a), len(states_b))
        if sample_count < self.mutual_information_min_samples:
            return {
                'sample_count': sample_count,
                'mutual_information': 0.0,
                'normalized_mutual_information': 0.0,
                'entropy_a': 0.0,
                'entropy_b': 0.0,
                'state_cardinality_a': 0,
                'state_cardinality_b': 0,
            }

        states_a = states_a[:sample_count]
        states_b = states_b[:sample_count]
        values_a, inverse_a = np.unique(states_a, return_inverse=True)
        values_b, inverse_b = np.unique(states_b, return_inverse=True)
        joint_counts = np.zeros((len(values_a), len(values_b)), dtype=float)
        np.add.at(joint_counts, (inverse_a, inverse_b), 1.0)

        joint = joint_counts / sample_count
        marginal_a = joint.sum(axis=1)
        marginal_b = joint.sum(axis=0)
        mutual_information = 0.0
        for value_a in range(len(values_a)):
            for value_b in range(len(values_b)):
                probability = joint[value_a, value_b]
                independent_probability = marginal_a[value_a] * marginal_b[value_b]
                if probability > 0 and independent_probability > 0:
                    mutual_information += probability * np.log(probability / independent_probability)

        entropy_a = -sum(probability * np.log(probability) for probability in marginal_a if probability > 0)
        entropy_b = -sum(probability * np.log(probability) for probability in marginal_b if probability > 0)
        normalizer = np.sqrt(entropy_a * entropy_b)
        normalized = mutual_information / normalizer if normalizer > 0 else 0.0
        return {
            'sample_count': sample_count,
            'mutual_information': float(max(0.0, mutual_information)),
            'normalized_mutual_information': float(np.clip(normalized, 0.0, 1.0)),
            'entropy_a': float(entropy_a),
            'entropy_b': float(entropy_b),
            'state_cardinality_a': int(len(values_a)),
            'state_cardinality_b': int(len(values_b)),
        }

    def compute_mutual_information_penalty(self, category_name, information_states, all_test_ids=None):
        """Estimate redundancy with recently selected clusters using strict MI."""
        current_pool = self.build_candidate_pool_for_category(
            category_name,
            all_test_ids,
            log_event='mutual_information_selection',
        )
        self.latest_category_candidate_pools[category_name] = current_pool

        pair_scores = []
        for previous_category in dict.fromkeys(self.recent_target_category_history):
            if previous_category == category_name:
                continue
            mi_result = self.empirical_mutual_information(
                information_states.get(category_name, []),
                information_states.get(previous_category, []),
            )
            pair_scores.append((previous_category, mi_result))
            self.mutual_information_history.append({
                'timestamp': time.time(),
                'event': 'category_selection_candidate',
                'completed_runs': sum(self.sequence_run_count.values()),
                'runtime': self.runtime,
                'category': category_name,
                'reference_category': previous_category,
                **mi_result,
            })

        strongest = max(
            pair_scores,
            key=lambda item: item[1]['normalized_mutual_information'],
            default=(None, {
                'mutual_information': 0.0,
                'normalized_mutual_information': 0.0,
            }),
        )
        reference_category, strongest_mi = strongest
        penalty = (
            self.mutual_information_penalty_weight
            * strongest_mi['normalized_mutual_information']
        )
        return current_pool, reference_category, strongest_mi, penalty

    def is_category_stalled(self, category_name):
        """Return True when recent targeting of a cluster produced no new bins."""
        gains = self.category_gain_history.get(category_name, [])
        if len(gains) < self.pool_backup_stall_window:
            return False
        recent_gains = gains[-self.pool_backup_stall_window:]
        return all(gain <= 0 for gain in recent_gains)

    def get_pool_backup_sequences(self, category_name, category_stats, all_test_ids=None):
        """Borrow candidate tests from high-MI clusters when a target stalls."""
        all_test_ids = all_test_ids or self.test_config.get_all_test_identifiers()
        information_states = self.build_cluster_information_states(category_stats.keys())
        target_pool = self.build_candidate_pool_for_category(
            category_name,
            all_test_ids,
            log_event='pool_backup_target',
        )
        self.latest_category_candidate_pools[category_name] = target_pool

        similar_categories = []
        for other_category in category_stats:
            if other_category == category_name:
                continue
            other_pool = self.build_candidate_pool_for_category(
                other_category,
                all_test_ids,
                log_event='pool_backup_similar_candidate',
            )
            self.latest_category_candidate_pools[other_category] = other_pool
            mi_result = self.empirical_mutual_information(
                information_states.get(category_name, []),
                information_states.get(other_category, []),
            )
            normalized_mi = mi_result['normalized_mutual_information']
            self.mutual_information_history.append({
                'timestamp': time.time(),
                'event': 'stalled_cluster_backup',
                'completed_runs': sum(self.sequence_run_count.values()),
                'runtime': self.runtime,
                'category': category_name,
                'reference_category': other_category,
                **mi_result,
            })
            if normalized_mi > 0:
                similar_categories.append((other_category, mi_result, other_pool))

        similar_categories.sort(
            key=lambda item: item[1]['normalized_mutual_information'],
            reverse=True,
        )
        backup_sequences = []
        source_categories = []
        for other_category, mi_result, other_pool in similar_categories[:self.pool_backup_top_categories]:
            source_categories.append({
                'category': other_category,
                'mutual_information': mi_result['mutual_information'],
                'normalized_mutual_information': mi_result['normalized_mutual_information'],
            })
            for test_id, _ in sorted(other_pool.items(), key=lambda item: item[1], reverse=True):
                if test_id not in backup_sequences:
                    backup_sequences.append(test_id)

        self.pool_backup_history.append({
            'timestamp': time.time(),
            'target_category': category_name,
            'source_categories': json.dumps(source_categories, sort_keys=True),
            'backup_sequences': json.dumps(backup_sequences),
        })
        self.flush_runtime_logs()
        return backup_sequences, source_categories

    def select_target_category_with_ucb(self, category_stats, exploration_weight=2.0):
        if not category_stats:
            return None

        ucb_scores = {}
        adjusted_scores = {}
        pool_debug = {}
        all_test_ids = self.test_config.get_all_test_identifiers()
        information_states = self.build_cluster_information_states(category_stats.keys())
        total_selections = sum(self.category_successful_run_count.values()) + 1  # successful feedback only
        max_uncovered = max(stats['uncovered_bins'] for stats in category_stats.values()) if category_stats else 1

        for category_name, stats in category_stats.items():
            if stats['uncovered_bins'] == 0:
                continue  # 已全覆盖

            n_i = self.category_successful_run_count[category_name] + 1  # successful feedback only
            gains = self.category_gain_history[category_name]
            avg_gain = np.mean(gains) if gains else 0.0

            # ✅ 期望增益：未覆盖 bin 数 ×（基础命中率 + 历史平均增益）
            base_hit_rate = 0.05  # 假设每个 category 至少有点潜力
            expected_gain = stats['uncovered_bins'] * (base_hit_rate + avg_gain)

            # UCB 公式
            exploration_bonus = exploration_weight * np.sqrt(np.log(total_selections) / n_i)
            entropy_importance = self.category_entropy_importance.get(category_name, 1.0)
            entropy_bonus = self.entropy_weight * expected_gain * (entropy_importance - 1.0)
            ucb = expected_gain + exploration_bonus + entropy_bonus
            ucb_scores[category_name] = ucb
            candidate_pool, reference_category, mi_result, penalty = self.compute_mutual_information_penalty(
                category_name,
                information_states,
                all_test_ids,
            )
            adjusted_scores[category_name] = ucb * max(0.0, 1.0 - penalty)
            pool_debug[category_name] = {
                'raw_ucb': ucb,
                'adjusted_ucb': adjusted_scores[category_name],
                'reference_category': reference_category,
                'mutual_information': mi_result['mutual_information'],
                'normalized_mutual_information': mi_result['normalized_mutual_information'],
                'mutual_information_penalty': penalty,
                'candidate_pool': candidate_pool,
            }

        if not adjusted_scores:
            return None

        selected_category_name = max(adjusted_scores, key=adjusted_scores.get)
        selected_stats = category_stats[selected_category_name]


        print(f"UCB selected category: {selected_category_name} "
            f"(score: {adjusted_scores[selected_category_name]:.4f}, "
            f"raw: {ucb_scores[selected_category_name]:.4f}, "
            f"NMI: {pool_debug[selected_category_name]['normalized_mutual_information']:.4f}, "
            f"uncovered: {selected_stats['uncovered_bins']})")

        for category_name, debug in pool_debug.items():
            self.pool_sharing_history.append({
                'timestamp': time.time(),
                'event': 'category_selection',
                'selected_category': selected_category_name,
                'category': category_name,
                'raw_ucb': debug['raw_ucb'],
                'adjusted_ucb': debug['adjusted_ucb'],
                'reference_category': debug['reference_category'],
                'mutual_information': debug['mutual_information'],
                'normalized_mutual_information': debug['normalized_mutual_information'],
                'mutual_information_penalty': debug['mutual_information_penalty'],
                'candidate_pool': json.dumps(debug['candidate_pool'], sort_keys=True),
            })

        self.flush_runtime_logs()

        return {
            'name': selected_category_name,
            'total_bins': selected_stats['total_bins'],
            'covered_bins': selected_stats['covered_bins'],
            'uncovered_bins': selected_stats['uncovered_bins'],
            'coverage_percent': selected_stats['coverage_percent'],
            'bin_names': selected_stats['bin_names']
        }
    def select_next_sequence(self, batch_num):
        """选择下一个序列，如果目标类别所有score都为0则尝试下一个类别"""
        # 显示当前累积覆盖率状态
        current_coverage, current_covered, current_total, category_stats = self.get_current_coverage_stats()
        print(f"\nCurrent cumulative coverage: {current_coverage:.2f}% ({current_covered}/{current_total} bins)")
        target_category = None  # 默认值

        # === 新增：计算覆盖率进度（归一化到 0~1） ===
        if current_total > 0:
            coverage_progress = current_covered / current_total  # 范围：0.0 ~ 1.0
        else:
            coverage_progress = 0.0

        # === 动态计算 runtime 惩罚权重 ===
        min_weight = 0.1   # 早期惩罚轻
        max_weight = 0.5   # 后期惩罚重
        adaptive_runtime_penalty_weight = min_weight + (max_weight - min_weight) * coverage_progress

        print(f"Coverage progress: {coverage_progress:.2f}, "
              f"Using adaptive runtime penalty weight: {adaptive_runtime_penalty_weight:.3f}")

        # 显示当前runtime统计
        avg_runtimes = self.get_average_runtimes()
        print(f"Current average runtimes:")
        all_test_ids = self.test_config.get_all_test_identifiers()
        for test_id in all_test_ids:
            avg_runtime = avg_runtimes.get(test_id, 0.0)
            total_runs = len(self.sequence_runtimes.get(test_id, []))
            if total_runs > 0:
                print(f"  {test_id}: {avg_runtime:.2f}s (from {total_runs} runs)")

        if not category_stats:
            print("No category coverage data available, using random test")
            selected_test_config = self.test_config.select_random_test()
        else:
            print("All category statistics:")
            for category, stats in category_stats.items():
                print(f"  {category}: {stats['coverage_percent']:.2f}% "
                    f"({stats['covered_bins']}/{stats['total_bins']} bins)")

            # 获取按照uncovered bins数量排序的类别列表
            #sorted_categories = sorted(category_stats.items(),
            #                        key=lambda x: x[1]['priority_score'],
            #                       reverse=True)

            # sorted_categories = sorted(category_stats.items(),
            #                         key=lambda x: x[1]['coverage_percent'],  # 覆盖率最低优先
            #                         reverse=False)  # 升序：越低越靠前

            # if coverage_progress < 0.6:
            #     c = 4.0  # 早期大力探索
            # elif coverage_progress < 0.85:
            #     c = 2.5  # 中期适度探索
            # else:
            #     c = 1.0  # 后期聚焦利用

            # target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=c)

            # ✅ 混合策略：早期用 UCB，中期强制探索最差 category
            # if coverage_progress < 0.3:
            #     # 初期：UCB 探索
            #     c = 4.0
            #     target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=c)
            # elif coverage_progress < 0.8:
            #     # 中期：20% 概率强制选最差 category
            #     if random.random() < 0.2:
            #         print("\n💡 Forced selection: choosing worst category to break plateau")
            #         worst_category = self.coverage_analyzer.find_worst_category(category_stats)
            #         if worst_category:
            #             target_category = worst_category
            #             self.category_selection_count[worst_category['name']] += 1
            #         else:
            #             target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=3.0)
            #     else:
            #         target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=2.5)
            # else:
            #     # 后期：UCB 利用
            #     target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=1.0)

             # ✅ 使用 Sigmoid 曲线平滑调度策略


            # # 1. 强制选最差 category 的概率（Sigmoid 上升曲线）
            # force_prob = 0.4 / (1 + np.exp(-20 * (coverage_progress - 0.6)))

            # # 2. 探索权重 c（Sigmoid 下降曲线）
            # c = 1.2 + 3.8 / (1 + np.exp(-12 * (0.5 - coverage_progress)))

            # # 3. 高覆盖率兜底：30% 概率随机选未全覆盖 category
            # if coverage_progress > 0.9 and random.random() < 0.4:
            #     print(f"\n💡 FINAL STAGE: Randomly pick incomplete category (p=0.4)")
            #     incomplete_cats = [cat for cat, stats in category_stats.items() if stats['uncovered_bins'] > 0]
            #     if incomplete_cats:
            #         selected_name = random.choice(incomplete_cats)
            #         target_category = category_stats[selected_name]
            #         self.category_selection_count[selected_name] += 1
            #         return target_category

            # # 4. 主逻辑：以 force_prob 概率强制选最差 category
            # if random.random() < force_prob:
            #     print(f"\n💡 Forced selection (p={force_prob:.3f}): choosing worst category")
            #     worst_category = self.coverage_analyzer.find_worst_category(category_stats)
            #     if worst_category:
            #         target_category = worst_category
            #         self.category_selection_count[worst_category['name']] += 1
            #     else:
            #         target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=c)
            # else:
            #     target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=c)
            # ✅ 终极五阶段混合策略
            if coverage_progress < 0.25:
                # 初期：强探索
                target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=5.0)
            elif coverage_progress < 0.5:
                # 混合探索
                if random.random() < 0.15:
                    print("\n💡 Stage 2: Forced worst category")
                    worst_category = self.coverage_analyzer.find_worst_category(category_stats)
                    if worst_category:
                        target_category = worst_category
                    else:
                        target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=3.5)
                else:
                    target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=3.5)
            elif coverage_progress < 0.7:
                # 深度混合
                if random.random() < 0.25:
                    print("\n💡 Stage 3: Forced worst category")
                    worst_category = self.coverage_analyzer.find_worst_category(category_stats)
                    if worst_category:
                        target_category = worst_category
                    else:
                        target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=2.5)
                else:
                    target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=2.5)
            elif coverage_progress < 0.9:
                # 聚焦稀疏
                if random.random() < 0.35:
                    print("\n💡 Stage 4: Forced worst category")
                    worst_category = self.coverage_analyzer.find_worst_category(category_stats)
                    if worst_category:
                        target_category = worst_category
                    else:
                        target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=1.8)
                else:
                    target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=1.8)
            else:
                # 后期：贪心 + 随机重启
                if random.random() < 0.4:
                    print("\n💡 Stage 5: Randomly pick an incomplete category")
                    incomplete_cats = [cat for cat, stats in category_stats.items() if stats['uncovered_bins'] > 0]
                    if incomplete_cats:
                        selected_name = random.choice(incomplete_cats)
                        target_category = dict(category_stats[selected_name])
                        target_category['name'] = selected_name
                    else:
                        target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=1.2)
                else:
                    target_category = self.select_target_category_with_ucb(category_stats, exploration_weight=1.2)

            # Record every target decision, including forced-worst and random
            # branches that bypass the UCB helper. MI must see the actual recent
            # target history rather than only UCB-selected clusters.
            if target_category is not None:
                self.recent_target_category_history.append(target_category['name'])

            # === 使用 UCB 选出 target_category 后，继续选 sequence ===
            if target_category is None:
                print("No valid category found by UCB, using random sequence")
                selected_test_config = self.test_config.select_random_test()
                test_identifier = selected_test_config['seq']
                return selected_test_config, test_identifier, target_category

            print(f"\n=== Target Category Selected: {target_category['name']} ===")
            print(f"Coverage: {target_category['coverage_percent']:.2f}% ({target_category['covered_bins']}/{target_category['total_bins']} bins)")
            print(f"Uncovered bins: {target_category['uncovered_bins']}")
            # Step 1: 构建候选 sequence 集合 —— 曾 hit 过该 category 的
            candidate_sequences = []
            for test_id in all_test_ids:
                has_hit = False
                if test_id in self.historical_data:
                    for vec in self.historical_data[test_id]:
                        cat_vec = self.coverage_analyzer.extract_category_vector(vec, target_category['name'])
                        if len(cat_vec) > 0 and np.any(cat_vec > 0):
                            has_hit = True
                            break
                if has_hit:
                    candidate_sequences.append(test_id)

            if not candidate_sequences:
                print(f"No sequence has ever covered {target_category['name']}, using all sequences as fallback")
                candidate_sequences = all_test_ids

            if self.is_category_stalled(target_category['name']):
                backup_sequences, source_categories = self.get_pool_backup_sequences(
                    target_category['name'],
                    category_stats,
                    all_test_ids,
                )
                added = [test_id for test_id in backup_sequences if test_id not in candidate_sequences]
                if added:
                    candidate_sequences = list(candidate_sequences) + added
                    print(f"Pool-MI backup enabled for stalled {target_category['name']}: "
                          f"added {len(added)} sequences from similar pools {source_categories}")

            # Step 2: 计算每个候选 sequence 的 UCB Score
            ucb_scores = {}
            total_runs = sum(self.sequence_category_run_count[test_id][target_category["name"]] for test_id in all_test_ids)

            # 动态 exploration weight
            if coverage_progress < 0.3:
                c = 3.0
            elif coverage_progress < 0.7:
                c = 2.0
            else:
                c = 1.0

            for test_id in candidate_sequences:
                n_i = self.sequence_category_run_count[test_id][target_category["name"]]
                avg_gain = self.compute_category_gain(test_id, target_category['name'])
                if n_i == 0:
                    ucb_scores[test_id] = avg_gain + c * np.sqrt(np.log(total_runs + 2))
                else:
                    ucb = avg_gain + c * np.sqrt(np.log(total_runs + 1) / (n_i + 1e-8))
                    ucb_scores[test_id] = ucb

            # Step 3: 应用 runtime 惩罚
            final_scores = {}
            max_runtime = max(avg_runtimes.values()) if avg_runtimes else 1.0
            for test_id in candidate_sequences:
                ucb_score = ucb_scores[test_id]
                runtime = avg_runtimes.get(test_id, 0.0)
                norm_runtime = runtime / max_runtime if max_runtime > 0 else 0.0
                runtime_factor = max(0.0, 1.0 - adaptive_runtime_penalty_weight * norm_runtime)
                final_scores[test_id] = ucb_score * runtime_factor

            # Step 4: 找出最高分的 sequence
            finite_scores = {k: v for k, v in final_scores.items() if np.isfinite(v)}
            if not finite_scores:
                print(f"All scores are 0 or inf for category {target_category['name']}, using random selection")
                selected_test_config = self.test_config.select_random_test()
            else:
                eligible_scores = {
                    test_id: score
                    for test_id, score in finite_scores.items()
                    if not self.is_sequence_repetition_blocked(test_id)
                }
                if eligible_scores:
                    best_test_id = max(eligible_scores.items(), key=lambda x: x[1])[0]
                else:
                    best_test_id = max(finite_scores.items(), key=lambda x: x[1])[0]
                selected_test_config = self.test_config.parse_test_identifier(best_test_id)
                print(f"Selected sequence: {best_test_id} (score: {finite_scores[best_test_id]:.4f})")

            # 生成测试标识符
            if selected_test_config['type'] == 'variant':
                test_identifier = f"{selected_test_config['seq']}[{selected_test_config['variant']['name']}]"
            else:
                test_identifier = selected_test_config['seq']

            return selected_test_config, test_identifier, target_category

                # 选择最佳测试配置


        # 生成测试标识符
        if selected_test_config['type'] == 'variant':
            test_identifier = f"{selected_test_config['seq']}[{selected_test_config['variant']['name']}]"
        else:
            test_identifier = selected_test_config['seq']

        # return selected_test_config, test_identifier
        return selected_test_config, test_identifier, target_category

    def run_all_batches(self):
        """Run all tests with incremental information-triggered scheduling."""
        self.wall_start_time = time.time()
        print(f"\n{'='*80}")
        print(f"STARTING {self.test_config.test_name.upper()} ADAPTIVE SIMULATION RUNNER")
        print(f"{'='*80}")
        print(f"Batch size: {self.batch_size}")
        print(f"Total batches: {self.total_batches}")
        print(f"Seed: {self.seed}")
        print(f"Ignore initial coverage: {self.ignore_initial_coverage}")
        print(f"Max workers: {self.max_workers}")
        print(f"Runtime penalty weight: {self.runtime_penalty_weight}")
        all_bin_names = self.coverage_analyzer.get_all_bin_names_ordered()
        print(f"Total bins tracked: {len(all_bin_names)}")
        print(f"Categories: {self.coverage_analyzer.category_order}")
        print(f"Test sequences: {len(self.test_config.test_sequences)} original + {len(self.test_config.test_variants)} variants")

        self.setup_result_directory()

        total_tests = self.total_batches * self.batch_size
        submitted_tests = 0
        completed_tests = 0
        active_futures = {}
        pending_info = self.reset_pending_info()
        batch_windows = {}
        seed_generator = random.Random(self.seed)

        def ensure_batch_window(batch_num, context):
            if batch_num not in batch_windows:
                batch_windows[batch_num] = {
                    'batch_num': batch_num,
                    'test_config': context['test_config'],
                    'batch_size': self.batch_size,
                    'seeds': [],
                    'results': [],
                    'contexts': [],
                    'start_time': time.time(),
                    'before_coverage': context['before_coverage'],
                    'before_covered': context['before_covered']
                }
            return batch_windows[batch_num]

        def submit_selected_test(executor, test_config, test_identifier, target_category):
            nonlocal submitted_tests
            if submitted_tests >= total_tests:
                return False
            run_id = submitted_tests
            seed = seed_generator.randint(1, 2**31 - 1)
            future, context = self.submit_next_test(
                executor, run_id, test_config, test_identifier, target_category, seed
            )
            active_futures[future] = context
            self.active_sequence_count[test_identifier] += 1
            self.recent_sequence_history.append(test_identifier)
            window = ensure_batch_window(context['logical_batch_id'], context)
            window['seeds'].append(seed)
            window['contexts'].append(context)
            submitted_tests += 1
            return True

        def complete_batch_window_if_ready(batch_num):
            window = batch_windows.get(batch_num)
            if not window or len(window['results']) < self.batch_size:
                return
            if window.get('completed'):
                return

            after_coverage, after_covered, _, _ = self.get_current_coverage_stats()
            test_ids = [ctx['test_identifier'] for ctx in window['contexts']]
            unique_test_ids = sorted(set(test_ids))
            test_identifier = unique_test_ids[0] if len(unique_test_ids) == 1 else 'mixed'
            bins_increase = after_covered - window['before_covered']
            coverage_increase = after_coverage - window['before_coverage']

            batch_info = {
                'batch_num': batch_num,
                'test_config_used': window['test_config'],
                'test_identifier': test_identifier,
                'batch_size': self.batch_size,
                'before_coverage': window['before_coverage'],
                'after_coverage': after_coverage,
                'coverage_increase': coverage_increase,
                'bins_increase': bins_increase,
                'results': window['results'],
                'batch_time': time.time() - window['start_time'],
                'timestamp': time.time()
            }
            self.batch_history.append(batch_info)

            summary = {
                'batch_num': batch_num,
                'test_config': window['test_config'],
                'batch_size': self.batch_size,
                'seeds': window['seeds'],
                'results': window['results'],
                'timestamp': batch_info['timestamp']
            }
            batch_dir = self.result_dir / 'batches' / f'batch_{batch_num}'
            with open(batch_dir / 'batch_summary.json', 'w') as f:
                json.dump(summary, f, indent=2, default=str)

            success_count = sum(1 for r in window['results'] if r['status'] == 'success')
            print(f"Batch {batch_num + 1} completed: {success_count}/{self.batch_size} tests successful")
            window['completed'] = True

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            selected_test_config, test_identifier, target_category = self.select_next_sequence(0)
            for slot_idx in range(min(self.max_workers, total_tests)):
                if slot_idx > 0 and self.should_refresh_sequence_for_repetition(test_identifier):
                    selected_test_config, test_identifier, target_category = self.select_next_sequence(0)
                submit_selected_test(executor, selected_test_config, test_identifier, target_category)

            while completed_tests < total_tests and active_futures:
                for future in as_completed(list(active_futures.keys())):
                    context = active_futures.pop(future)
                    completed_test_identifier = context['test_identifier']
                    if self.active_sequence_count.get(completed_test_identifier, 0) > 0:
                        self.active_sequence_count[completed_test_identifier] -= 1
                    completed_tests += 1

                    try:
                        result = future.result()
                    except Exception as e:
                        print(f"Test generated exception: {e}")
                        result = {
                            'run_id': context['run_id'],
                            'status': 'error',
                            'test_config': context['test_config'],
                            'test_description': context['test_identifier'],
                            'error': str(e)
                        }

                    before_coverage, before_covered, _, _ = self.get_current_coverage_stats()
                    run_info = self.process_completed_run(result, context)
                    after_coverage, after_covered, after_total, _ = self.get_current_coverage_stats()

                    pending_info['pending_new_bins'] += run_info['new_bins']
                    pending_info['pending_target_category_gain'] += run_info['target_category_gain']
                    pending_info['pending_weighted_info_gain'] += run_info['weighted_info_gain']
                    pending_info['pending_completed_tests'] += 1

                    self.record_successful_ucb_feedback(result, context, run_info)

                    window = batch_windows[context['logical_batch_id']]
                    window['results'].append(result)
                    self.completed_run_history.append({
                        'test_identifier': context['test_identifier'],
                        'result': result
                    })

                    coverage_increase = after_coverage - before_coverage
                    bins_increase = after_covered - before_covered
                    print(f"\nUpdated cumulative coverage: {after_coverage:.2f}% ({after_covered}/{after_total} bins)")
                    print(f"  Runtime: {self.runtime:.2f} seconds")
                    print(f"  Coverage increase: +{coverage_increase:.2f}% (+{bins_increase} bins)")
                    print(f"  Pending info: bins={pending_info['pending_new_bins']}, "
                          f"target_gain={pending_info['pending_target_category_gain']}, "
                          f"weighted={pending_info['pending_weighted_info_gain']:.2f}, "
                          f"completed={pending_info['pending_completed_tests']}")

                    trace.append({
                        'runtime': self.runtime,
                        'covered': after_covered
                    })
                    self.flush_runtime_logs()

                    complete_batch_window_if_ready(context['logical_batch_id'])

                    should_reselect = self.should_trigger_reselection(pending_info)
                    if should_reselect:
                        pending_info = self.reset_pending_info()
                        selected_test_config, test_identifier, target_category = self.select_next_sequence(completed_tests // self.batch_size)
                    elif self.should_refresh_sequence_for_repetition(test_identifier):
                        selected_test_config, test_identifier, target_category = self.select_next_sequence(completed_tests // self.batch_size)

                    if submitted_tests < total_tests:
                        submit_selected_test(executor, selected_test_config, test_identifier, target_category)
                    break

        for batch_num in sorted(batch_windows):
            complete_batch_window_if_ready(batch_num)

        self.flush_runtime_logs()
        print(f"Incremental scheduler logs saved under: {self.result_dir / 'logs'}")
        self.generate_final_report()

    def generate_final_report(self):
        """生成最终报告"""
        print(f"\n{'='*80}")
        print("FINAL REPORT")
        print(f"{'='*80}")

        total_tests = self.total_batches * self.batch_size
        total_successful = sum(
            sum(1 for r in batch['results'] if r['status'] == 'success')
            for batch in self.batch_history
        )
        all_bin_names = self.coverage_analyzer.get_all_bin_names_ordered()

        print(f"Total batches completed: {len(self.batch_history)}")
        print(f"Total tests run: {total_tests}")
        print(f"Successful tests: {total_successful}")
        print(f"Success rate: {total_successful/total_tests*100:.2f}%")
        print(f"Seed used: {self.seed}")
        print(f"Ignore initial coverage: {self.ignore_initial_coverage}")
        print(f"Runtime penalty weight: {self.runtime_penalty_weight}")
        print(f"Total runtime: {self.runtime:.2f} seconds")
        total_walltime = time.time() - self.wall_start_time if self.wall_start_time else 0.0
        print(f"Total walltime: {total_walltime:.2f} seconds")

        # 测试使用统计
        test_usage = defaultdict(int)
        if self.completed_run_history:
            for item in self.completed_run_history:
                test_usage[item['test_identifier']] += 1
        else:
            for batch in self.batch_history:
                test_id = batch['test_identifier']
                test_usage[test_id] += 1

        print(f"\nTest usage:")
        all_test_ids = self.test_config.get_all_test_identifiers()
        for test_id in all_test_ids:
            count = test_usage.get(test_id, 0)
            print(f"  {test_id}: {count} batches")

        # 添加runtime统计
        avg_runtimes = self.get_average_runtimes()
        print(f"\nAverage runtime by test:")
        for test_id in all_test_ids:
            avg_runtime = avg_runtimes.get(test_id, 0.0)
            total_runs = len(self.sequence_runtimes.get(test_id, []))
            if total_runs > 0:
                print(f"  {test_id}: {avg_runtime:.2f}s (from {total_runs} runs)")

        # 覆盖率增长历史
        if self.batch_history:
            print(f"\nCoverage growth history:")
            for batch in self.batch_history:
                print(f"  Batch {batch['batch_num']+1}: {batch['before_coverage']:.2f}% -> {batch['after_coverage']:.2f}% "
                      f"(+{batch['coverage_increase']:.2f}%, +{batch['bins_increase']} bins) [{batch['test_identifier']}]")

        # 最终覆盖率统计
        final_coverage, final_covered, final_total, final_category_stats = self.get_current_coverage_stats()

        print(f"\nFinal coverage by category:")
        for category, stats in final_category_stats.items():
            print(f"  {category}: {stats['coverage_percent']:.2f}% "
                  f"({stats['covered_bins']}/{stats['total_bins']} bins)")

        if self.ignore_initial_coverage:
            print(f"\n*** FINAL OVERALL COVERAGE: {final_coverage:.2f}% ({final_covered}/{final_total} bins) ***")
            print("    (Coverage calculated from 0, ignoring initial data)")
        else:
            print(f"\n*** FINAL OVERALL COVERAGE: {final_coverage:.2f}% ({final_covered}/{final_total} bins) ***")
            print("    (Coverage includes initial data)")

        print(f"\nNote: Only bins present in category mapping file are tracked and reported.")

        # 保存详细报告到文件
        report_file = self.result_dir / 'final_report.txt'

        with open(report_file, 'w') as f:
            f.write(f"{self.test_config.test_name.title()} Adaptive Simulation Runner - Final Report\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Configuration:\n")
            f.write(f"  Test Name: {self.test_config.test_name}\n")
            f.write(f"  Config File: {self.config_file}\n")
            f.write(f"  Batch Size: {self.batch_size}\n")
            f.write(f"  Total Batches: {self.total_batches}\n")
            f.write(f"  Total Tests: {total_tests}\n")
            f.write(f"  Max Workers: {self.max_workers}\n")
            f.write(f"  Base Seed: {self.seed}\n")
            f.write(f"  Ignore Initial Coverage: {self.ignore_initial_coverage}\n")
            f.write(f"  Runtime Penalty Weight: {self.runtime_penalty_weight}\n")
            f.write(f"  Categories: {len(self.coverage_analyzer.category_order)}\n")
            f.write(f"  Vector Length: {len(all_bin_names)}\n")
            f.write(f"  Original Sequences: {len(self.test_config.test_sequences)}\n")
            f.write(f"  Test Variants: {len(self.test_config.test_variants)}\n")
            f.write(f"  Total Test Types: {len(all_test_ids)}\n")
            f.write(f"  Note: Only bins in category mapping file are tracked\n\n")

            f.write(f"Results Summary:\n")
            f.write(f"  Completed Batches: {len(self.batch_history)}\n")
            f.write(f"  Successful Tests: {total_successful}/{total_tests}\n")
            f.write(f"  Success Rate: {total_successful/total_tests*100:.2f}%\n")
            f.write(f"  Total Runtime: {self.runtime:.2f} seconds\n")
            f.write(f"  Total Walltime: {total_walltime:.2f} seconds\n")
            f.write(f"  Final Coverage: {final_coverage:.2f}%\n\n")

            f.write("Batch Details:\n")
            for batch in self.batch_history:
                batch_success = sum(1 for r in batch['results'] if r['status'] == 'success')
                f.write(f"  Batch {batch['batch_num'] + 1}: {batch['test_identifier']} - "
                       f"{batch_success}/{self.batch_size} successful "
                       f"({batch['batch_time']:.1f}s) - "
                       f"{batch['before_coverage']:.2f}% -> {batch['after_coverage']:.2f}%\n")

            f.write(f"\nTest Usage:\n")
            for test_id, count in sorted(test_usage.items()):
                f.write(f"  {test_id}: {count} batches\n")

            # 在文件报告中也添加runtime信息
            f.write(f"\nRuntime Statistics:\n")
            for test_id, avg_runtime in sorted(avg_runtimes.items()):
                total_runs = len(self.sequence_runtimes.get(test_id, []))
                if total_runs > 0:
                    f.write(f"  {test_id}: {avg_runtime:.2f}s average (from {total_runs} runs)\n")

        print(f"\nFinal report saved to: {report_file}")


def main():
    parser = argparse.ArgumentParser(description='Generic Adaptive Simulation-based Coverage Test Runner with Runtime Penalty')
    parser.add_argument('config_file', help='YAML configuration file containing test sequences and run commands')
    parser.add_argument('batch_size', type=int, help='Number of tests per batch')
    parser.add_argument('total_batches', type=int, help='Total number of batches to run')
    parser.add_argument('initial_csv', help='CSV file containing initial historical coverage data')
    parser.add_argument('result_dir', help='Result directory path')
    parser.add_argument('--category-mapping', help='CSV file containing feature name to category mapping')
    parser.add_argument('--seed', type=int, default=42, help='Random seed (default: 42)')
    parser.add_argument('--ignore-initial-coverage', action='store_true',
                       help='Ignore initial CSV coverage data and start coverage calculation from 0')
    parser.add_argument('--parallel', type=int, default=4, help='Number of parallel workers (default: 4)')
    parser.add_argument('--runtime-penalty-weight', type=float, default=0.3,
                       help='Weight for runtime penalty in sequence selection (default: 0.3)')

    args = parser.parse_args()

    if args.batch_size <= 0:
        print("Error: batch_size must be positive")
        return 1

    if args.total_batches <= 0:
        print("Error: total_batches must be positive")
        return 1

    if args.parallel <= 0:
        print("Error: parallel workers must be positive")
        return 1

    if not (0.0 <= args.runtime_penalty_weight <= 1.0):
        print("Error: runtime-penalty-weight must be between 0.0 and 1.0")
        return 1

    runner = GenericAdaptiveRunner(
        config_file=args.config_file,
        batch_size=args.batch_size,
        total_batches=args.total_batches,
        initial_csv_file=args.initial_csv,
        result_dir=args.result_dir,
        category_mapping_file=args.category_mapping,
        seed=args.seed,
        ignore_initial_coverage=args.ignore_initial_coverage,
        max_workers=args.parallel,
        runtime_penalty_weight=args.runtime_penalty_weight
    )

    try:
        runner.run_all_batches()
        print("All batches completed successfully!")
        return 0

    except KeyboardInterrupt:
        runner.flush_runtime_logs()
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        runner.flush_runtime_logs()
        print(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
