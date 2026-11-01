import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import json
import re
from collections import defaultdict

class GenericHierarchicalClusterer:
    def __init__(self, max_cluster_size=50, dimension_weights=None):
        """
        通用分层聚类器
        
        参数:
        max_cluster_size: 单个聚类的最大大小，超过会进一步拆分
        dimension_weights: 维度权重配置
        """
        self.max_cluster_size = max_cluster_size
        self.dimension_weights = dimension_weights or self._get_default_weights()
        
    def _get_default_weights(self):
        """默认维度权重，从高到低"""
        return {
            'namespace': 100,      # 命名空间/模块分离
            'component': 50,       # 组件级分离
            'method_type': 25,     # 方法类型
            'primary_param': 20,   # 主要参数
            'secondary_param': 15, # 次要参数
            'tertiary_param': 10,  # 第三级参数
            'numeric_param': 5,    # 数值参数
            'structure_type': 8    # 结构类型
        }
    
    def extract_features(self, name):
        """从名称中提取通用特征，按维度基数优先级排序"""
        features = {}

        # 标准化旧格式中的 HTML 转义符，便于统一处理
        normalized_name = name.replace('&lt;', '<').replace('&gt;', '>')

        # 预拆分基础部分和参数部分
        base_part = normalized_name.split('-<', 1)[0]
        remainder = base_part

        # 1. 提取命名空间（仅在显式存在双冒号时）
        namespace_part = None
        if '::' in base_part:
            namespace_part, remainder = base_part.split('::', 1)
        features['namespace'] = hash(namespace_part) % 100 if namespace_part else 0

        # 2. 提取组件名（兼容无命名空间的格式）
        component_part = remainder
        method_source = ''

        if '.' in remainder:
            component_part, method_source = remainder.split('.', 1)
        elif '-' in remainder:
            component_part, method_source = remainder.split('-', 1)
        else:
            method_source = remainder

        features['component'] = hash(component_part) % 50 if component_part else 0

        # 3. 检测结构类型
        if 'cross_' in normalized_name:
            features['structure_type'] = 2
        elif '.cp_' in normalized_name or '-cp_' in normalized_name:
            features['structure_type'] = 1
        else:
            features['structure_type'] = 0

        # 4. 智能提取参数并按基数排序
        bracket_content = re.findall(r'\[([^\]]+)\]', normalized_name)
        
        # 分析每个参数的基数特征
        param_analysis = []
        for i, param in enumerate(bracket_content):
            analysis = {
                'param': param,
                'position': i,
                'estimated_cardinality': self._estimate_cardinality(param),
                'param_type': self._classify_param_type(param)
            }
            param_analysis.append(analysis)
        
        # 按基数排序：基数小的优先级高
        param_analysis.sort(key=lambda x: (x['estimated_cardinality'], x['position']))
        
        # 根据排序后的顺序分配到不同层级
        features['primary_param'] = 0
        features['secondary_param'] = 0  
        features['tertiary_param'] = 0
        features['numeric_param'] = 0
        
        for i, analysis in enumerate(param_analysis):
            param_hash = hash(analysis['param']) % 50
            
            if i == 0:  # 基数最小的参数优先级最高
                features['primary_param'] = param_hash
            elif i == 1:
                features['secondary_param'] = param_hash
            elif i == 2:
                features['tertiary_param'] = param_hash
            else:
                # 数值参数特殊处理
                if analysis['param_type'] == 'numeric':
                    try:
                        val = int(analysis['param'])
                        features['numeric_param'] += val // 10
                    except ValueError:
                        features['numeric_param'] += param_hash
                else:
                    features['numeric_param'] += param_hash
        
        # 5. 提取方法类型（点号之后，横线之前）
        method_name = ''
        if method_source:
            method_name = re.split(r'[-<]', method_source, 1)[0]
        elif '.' in normalized_name:
            method_name = normalized_name.split('.', 1)[-1]
            method_name = re.split(r'[-<]', method_name, 1)[0]

        features['method_type'] = hash(method_name) % 30 if method_name else 0

        return features
    
    def _estimate_cardinality(self, param):
        """估算参数的基数（可能的取值数量）"""
        # 数字范围参数
        if ':' in param:
            try:
                parts = param.split(':')
                start, end = int(parts[0]), int(parts[1])
                return end - start + 1
            except ValueError:
                return 50  # 默认中等基数
        
        # 纯数字参数 - 根据数字大小估算基数
        if param.isdigit():
            val = int(param)
            if val < 10:
                return 10  # 小数字，基数较小
            elif val < 100:
                return 50  # 中等数字，中等基数
            else:
                return 100  # 大数字，基数较大
        
        # 字母参数 - 根据常见模式估算
        if re.match(r'^[A-Za-z]+\d*$', param):
            # 类型参数，通常基数较小
            return 5
        
        # 复合参数，基数中等
        return 30
    
    def _classify_param_type(self, param):
        """分类参数类型"""
        if param.isdigit():
            return 'numeric'
        elif ':' in param:
            return 'range'  
        elif re.match(r'^[A-Za-z]+\d*$', param):
            return 'categorical'
        else:
            return 'mixed'
    
    def build_feature_vector(self, features):
        """根据权重构建特征向量"""
        vector = []
        for dim_name, weight in self.dimension_weights.items():
            value = features.get(dim_name, 0)
            vector.append(value * weight)
        return vector
    
    def perform_clustering(self, items, eps=0.2, min_samples=2):
        """执行DBSCAN聚类"""
        if len(items) <= self.max_cluster_size:
            return {"Cluster_0": items}
        
        # 构建特征矩阵
        feature_matrix = []
        for item in items:
            features = self.extract_features(item)
            vector = self.build_feature_vector(features)
            feature_matrix.append(vector)
        
        # 标准化
        feature_matrix = np.array(feature_matrix)
        if feature_matrix.shape[0] > 1:
            scaler = StandardScaler()
            feature_matrix = scaler.fit_transform(feature_matrix)
        
        # DBSCAN聚类
        dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean')
        cluster_labels = dbscan.fit_predict(feature_matrix)
        
        # 整理结果
        clusters = defaultdict(list)
        for i, label in enumerate(cluster_labels):
            if label == -1:
                clusters["noise"].append(items[i])
            else:
                clusters[f"group_{label}"].append(items[i])
        
        return dict(clusters)
    
    def hierarchical_split(self, items, base_id=0, level=0):
        """递归分层拆分"""
        if len(items) <= self.max_cluster_size or level > 3:  # 限制递归深度
            return {f"Cluster_{base_id}": items}
        
        # 根据层级调整eps值
        eps_values = [0.3, 0.2, 0.15, 0.1]
        eps = eps_values[min(level, len(eps_values) - 1)]
        
        # 执行聚类
        clusters = self.perform_clustering(items, eps=eps, min_samples=2)
        
        result = {}
        sub_id = 0
        
        for cluster_name, cluster_items in clusters.items():
            current_id = f"{base_id}_{sub_id}" if level > 0 else str(base_id + sub_id)
            
            if cluster_name == "noise":
                if len(cluster_items) > 0:
                    result[f"Cluster_{current_id}_noise"] = cluster_items
            elif len(cluster_items) > self.max_cluster_size:
                # 递归拆分
                sub_result = self.hierarchical_split(cluster_items, current_id, level + 1)
                result.update(sub_result)
            else:
                result[f"Cluster_{current_id}"] = cluster_items
            
            sub_id += 1
        
        return result

def perform_generic_clustering(csv_file_path, output_file_path, 
                             max_cluster_size=30, exclude_patterns=None, eps=0.2):
    """
    通用聚类函数
    
    参数:
    csv_file_path: 输入CSV文件路径
    output_file_path: 输出文件路径  
    max_cluster_size: 最大聚类大小
    exclude_patterns: 要排除的模式列表
    eps: 初始DBSCAN的eps参数
    """
    
    # 读取数据
    df = pd.read_csv(csv_file_path)
    
    # 过滤列
    columns_to_exclude = ['run', 'runtime']
    if df.columns[0].startswith('Unnamed') or df.columns[0] == '':
        columns_to_exclude.append(df.columns[0])
    
    # 应用排除模式
    coverage_columns = []
    exclude_patterns = exclude_patterns or []
    
    for col in df.columns:
        if col not in columns_to_exclude:
            exclude = False
            for pattern in exclude_patterns:
                if pattern in col:
                    exclude = True
                    break
            if not exclude:
                coverage_columns.append(col)
    
    print(f"找到 {len(coverage_columns)} 个项目用于聚类")
    
    # 创建聚类器并执行分层聚类
    clusterer = GenericHierarchicalClusterer(max_cluster_size=max_cluster_size)
    final_clusters = clusterer.hierarchical_split(coverage_columns)
    
    # 输出统计信息
    print(f"\n聚类结果:")
    total_items = sum(len(items) for items in final_clusters.values())
    for cluster_name, items in sorted(final_clusters.items()):
        print(f"{cluster_name}: {len(items)} 个项目")
    print(f"总计: {total_items} 个项目")
    
    # 保存CSV格式
    csv_output_path = output_file_path.replace('.json', '.csv')
    with open(csv_output_path, 'w', encoding='utf-8') as f:
        f.write("feature_name,cluster_id\n")
        
        for cluster_name, items in final_clusters.items():
            # 提取数字ID
            numbers = re.findall(r'\d+', cluster_name)
            if numbers:
                cluster_id = int(''.join(numbers[:2]))  # 最多取前两个数字
            elif 'noise' in cluster_name:
                cluster_id = -1
            else:
                cluster_id = hash(cluster_name) % 1000
            
            for item in items:
                escaped_name = item.replace('"', '""')
                f.write(f'"{escaped_name}",{cluster_id}\n')
    
    # 保存JSON格式
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(final_clusters, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果已保存到:")
    print(f"  CSV格式: {csv_output_path}")
    print(f"  JSON格式: {output_file_path}")
    
    return final_clusters

# 使用示例
if __name__ == "__main__":
    csv_file = "uart_10x_new_coverage.csv"
    output_file = "coverage_clustering_results.json"
    
    # 执行聚类
    results = perform_generic_clustering(
        csv_file, 
        output_file,
        max_cluster_size=256,
        exclude_patterns=['intr_test_cg'],  # 通用的排除模式
        eps=0.8
    )
