import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from glob import glob
from tqdm import tqdm
import bs4
import re
import joblib

# 数据加载函数
cp_pattern = re.compile(r'<p class="summary_title">(CoverPoint|CoverCross) Details: (.*)</p>')
t_pattern = re.compile(r'">([^/]+)</t[hd]>')
legal_pattern = re.compile(r'.*/[cp][0-9]*.html')
runtime_pattern = re.compile(r'Times for simulation: run (\d+.\d+)s')
pkg_pattern = re.compile(r'.*::')

def collect_bin_cnt(report):
    bin_cnt = {}
    htmls = list(sorted(filter(lambda s: re.fullmatch(legal_pattern, s), glob(f'{report}/report/*.html'))))
    for html in htmls:
        with open(html, 'r') as f:
            soup = bs4.BeautifulSoup(f, 'html.parser')
            segs = soup.find_all(lambda tag: tag.get("id") == 'coverageTable' or 
                                 (tag.has_attr("class") and 'summary_title' in tag.get("class")))
            for seg in segs:
                if seg.name == 'p':
                    m = cp_pattern.match(str(seg))
                    cp_name = m.group(2)
                    cp_name = pkg_pattern.sub('', cp_name)
                    cp_name = cp_name.replace('.', '-')
                elif seg.name == 'table':
                    for child in seg.children:
                        if child.name == 'thead':
                            th = '/'.join(t_pattern.findall(str(child)))
                            if th != 'Count/At Least/Bin Type/Bin Name/Database Covered':
                                break
                        elif child.name == 'tbody':
                            for c in child.children:
                                parts = list(map(lambda td: td.get_text(strip=True), c.find_all('td')))
                                cnt = 1 if int(parts[0])>0 else 0
                                bin = parts[3]
                                key = f'{cp_name}-{bin}'
                                bin_cnt[key] = cnt
    return bin_cnt

def process_data(d, flag):
    bin_cnt = collect_bin_cnt(d[:-len('dashboard.html')] if flag else d)
    bin_cnt['run'] = int(d.split('/')[-2])
    with open(d[:-len('dashboard.html')]+'run.log','r') as f:
        runtime = float(runtime_pattern.search(f.read()).group(1))
        bin_cnt['runtime'] = runtime
    return bin_cnt

def load_data(data_dir, flag=True):
    data = list(sorted(glob(f'{data_dir}/**/dashboard.html', recursive=True)))
    print(f"Found {len(data)} files")
    raw = joblib.Parallel(n_jobs=32)(joblib.delayed(process_data)(i, flag) for i in data)
    df = pd.DataFrame(raw).set_index('run').sort_index()
    return df

# 主函数
def main():
    # 加载基础数据
    df = pd.read_csv('/export/billchen/uart_more_seq_coverage.csv').drop(['run'], axis=1)
    n_bins = len(df.columns) - 1
    
    # 加载 ours 数据
    ours_df = load_data('/export/billchen/uart/uart_nova_more_seq', True).reset_index(drop=True)
    ours_df = pd.concat([df, ours_df]).reset_index(drop=True).cumsum()
    ours_df['covered'] = (ours_df.drop(columns='runtime')>0).sum(axis=1)
    ours_df['coverage'] = ours_df['covered']/n_bins
    # 加载 random 数据
    rand_df = load_data('/export/billchen/uart/baseline_more_seq', False).reset_index(drop=True)
    rand_df = pd.concat([df, rand_df]).reset_index(drop=True).cumsum()
    rand_df['covered'] = (rand_df.drop(columns='runtime')>0).sum(axis=1)
    rand_df['coverage'] = rand_df['covered']/n_bins
    # 加载 random 数据后，新增验证代码
    
    # 设置时间范围（可根据需要调整）
    time_lower = rand_df['runtime'].min()
    time_upper = rand_df['runtime'].max()
    
    # 过滤数据
    rand = rand_df[(rand_df['runtime']>=time_lower) & (rand_df['runtime']<=time_upper)]
    ours = ours_df[(ours_df['runtime']>=time_lower) & (ours_df['runtime']<=time_upper)]
    
    # 转换覆盖率为百分比
    rand['coverage'] *= 100
    ours['coverage'] *= 100
    print("="*50)
    print(f"Ours 数据行数：{len(ours)}")
    print(f"Ours 覆盖点列数：{len(ours.columns)-2}")
    print(f"Ours runtime 范围：{ours['runtime'].min():.2f} ~ {ours['runtime'].max():.2f}（应是合理时间，比如1e5~1e6秒）")
    print(f"Ours 初始覆盖率：{ours['coverage'].iloc[0]:.2f}%")
    print(f"Ours 最大覆盖率：{ours['coverage'].max():.2f}%")
    print("="*50)
    print("="*50)
    print("Random 数据异常验证：")
    print(f"Random 数据行数：{len(rand_df)}（应和 Ours 接近）")
    print(f"Random 覆盖点列数：{len(rand_df.columns)-2}（应和 Ours 一致，Ours 是 {len(ours_df.columns)-2}）")
    print(f"Random runtime 范围：{rand['runtime'].min():.2f} ~ {rand_df['runtime'].max():.2f}（应是合理时间，比如1e5~1e6秒）")
    print(f"Random 初始覆盖率：{rand['coverage'].iloc[0]:.2f}%（应从0或低数值开始）")
    print(f"Random 最大覆盖率：{rand['coverage'].max():.2f}%（应和 Ours 接近，比如95%左右）")
    # 创建图表
    plt.figure(figsize=(12, 6))
    
    # 绘制折线
    plt.plot(rand['runtime'], rand['coverage'], 'b-', label='Random', linewidth=2)
    plt.plot(ours['runtime'], ours['coverage'], 'r-', label='Ours', linewidth=2)
    
    # 标记最大覆盖率点
    rand_max_idx = rand['coverage'].idxmax()
    ours_max_idx = ours['coverage'].idxmax()
    
    plt.scatter(rand.loc[rand_max_idx, 'runtime'], rand.loc[rand_max_idx, 'coverage'], 
                color='blue', s=100, marker='o', zorder=5)
    plt.scatter(ours.loc[ours_max_idx, 'runtime'], ours.loc[ours_max_idx, 'coverage'], 
                color='red', s=100, marker='o', zorder=5)
    
    # 添加文字标注
    plt.text(rand.loc[rand_max_idx, 'runtime'], rand.loc[rand_max_idx, 'coverage'], 
             f'{rand.loc[rand_max_idx, "coverage"]:.2f}%', 
             verticalalignment='bottom', horizontalalignment='left', fontsize=10)
    plt.text(ours.loc[ours_max_idx, 'runtime'], ours.loc[ours_max_idx, 'coverage'], 
             f'{ours.loc[ours_max_idx, "coverage"]:.2f}%', 
             verticalalignment='bottom', horizontalalignment='left', fontsize=10)
    
    # 设置标签和标题
    plt.xlabel('Runtime (s)', fontsize=12)
    plt.ylabel('Coverage (%)', fontsize=12)
    plt.title('Coverage vs. Runtime', fontsize=14, fontweight='bold')
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.ylim(0,100)
    #plt.xlim(0.15*1e6,None)
    # 保存图表
    plt.tight_layout()
    plt.savefig('more_seq_coverage_vs_runtime_full.png', dpi=300, bbox_inches='tight')
    plt.savefig('more_seq_coverage_vs_runtime_full.svg', format='svg', bbox_inches='tight')
    print("图表已保存为 more_seq_coverage_vs_runtime_full.png 和 more_seq_coverage_vs_runtime_full.svg")
    plt.close()


    plt.figure(figsize=(12, 6))
    
    # 绘制折线
    plt.plot(rand['runtime'], rand['coverage'], 'b-', label='Random', linewidth=2)
    plt.plot(ours['runtime'], ours['coverage'], 'r-', label='Ours', linewidth=2)
    
    # 标记最大覆盖率点
    rand_max_idx = rand['coverage'].idxmax()
    ours_max_idx = ours['coverage'].idxmax()
    
    plt.scatter(rand.loc[rand_max_idx, 'runtime'], rand.loc[rand_max_idx, 'coverage'], 
                color='blue', s=100, marker='o', zorder=5)
    plt.scatter(ours.loc[ours_max_idx, 'runtime'], ours.loc[ours_max_idx, 'coverage'], 
                color='red', s=100, marker='o', zorder=5)

# 1. 合并数据：根据‘runtime’时间列进行合并，只保留双方都有的时间点（内连接）
# ================================================
    max_time = max(ours['runtime'].max(), rand['runtime'].max())
    common_times = np.linspace(0, max_time, 1000)
    ours_interp = np.interp(common_times, ours['runtime'], ours['coverage'])
    rand_interp = np.interp(common_times, rand['runtime'], rand['coverage'])
    coverage_diff = ours_interp - rand_interp
    max_diff = np.max(coverage_diff)
    max_diff_idx = np.argmax(coverage_diff)
    corresponding_runtime = common_times[max_diff_idx]
    rand_cov_at_max = rand_interp[max_diff_idx]
    ours_cov_at_max = ours_interp[max_diff_idx]

# ========== 新增：图上标注最大差值 ==========

# 标注位置：x=对应runtime，y=Ours的覆盖率（略向上偏移，避免遮挡曲线）

    annotation_text = f'max difference value: {max_diff:.4f}%'
    plt.annotate(
        annotation_text,  # 标注文字内容
        xy=(corresponding_runtime, ours_cov_at_max),  # 箭头指向的点（最大差值对应的位置）
        xytext=(corresponding_runtime * 1.2, ours_cov_at_max + 0.1),  # 标注文字的位置（偏移1.2倍x、+0.1y）
        fontsize=11,
        color='darkgreen',  # 标注文字颜色
        fontweight='bold',
        arrowprops=dict(
            arrowstyle='->',  # 箭头样式
            color='darkgreen',  # 箭头颜色
            lw=2,  # 箭头粗细
            alpha=0.8  # 透明度
        ),
        bbox=dict(
            boxstyle='round,pad=0.3',  # 文字框样式（圆角）
            facecolor='lightgreen',  # 文字框背景色
            alpha=0.7  # 文字框透明度
        )
    )
    # 添加文字标注
    plt.text(rand.loc[rand_max_idx, 'runtime'], rand.loc[rand_max_idx, 'coverage'], 
             f'{rand.loc[rand_max_idx, "coverage"]:.2f}%', 
             verticalalignment='bottom', horizontalalignment='left', fontsize=10)
    plt.text(ours.loc[ours_max_idx, 'runtime'], ours.loc[ours_max_idx, 'coverage'], 
             f'{ours.loc[ours_max_idx, "coverage"]:.2f}%', 
             verticalalignment='bottom', horizontalalignment='left', fontsize=10)
    
    # 设置标签和标题
    plt.xlabel('Runtime (s)', fontsize=12)
    plt.ylabel('Coverage (%)', fontsize=12)
    plt.title('Coverage vs. Runtime', fontsize=14, fontweight='bold')
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.ylim(94,100)
    plt.xlim(0*1e6,None)
    # 保存图表
    plt.tight_layout()
    plt.savefig('more_seq_coverage_vs_runtime_partial.png', dpi=300, bbox_inches='tight')
    plt.savefig('more_seq_coverage_vs_runtime_partial.svg', format='svg', bbox_inches='tight')
    print("图表已保存为 more_seq_coverage_vs_runtime_partial.png 和 more_seq_coverage_vs_runtime_partial.svg")
    plt.close()

if __name__ == "__main__":
    main()
