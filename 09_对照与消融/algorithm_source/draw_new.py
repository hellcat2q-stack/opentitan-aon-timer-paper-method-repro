import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from glob import glob
from tqdm import tqdm
import bs4
import re
import joblib

# 数据加载函数
cp_pattern = re.compile(r'<p class="summary_title">(CoverPoint|CoverCross) Details: (.*)</p >')
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



def load_data(data_dir, flag=False):

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

    ours_df = load_data('/export/billchen/uart/uart_nova_more_seq').reset_index(drop=True)

    ours_df = pd.concat([df, ours_df]).reset_index(drop=True).cumsum()

    ours_df['covered'] = (ours_df.drop(columns='runtime')>0).sum(axis=1)

    ours_df['coverage'] = ours_df['covered']/n_bins

    

    # 加载 random 数据

    rand_df = load_data('/export/billchen/uart/baseline_more_seq', True).reset_index(drop=True)

    rand_df = pd.concat([df, rand_df]).reset_index(drop=True).cumsum()

    rand_df['covered'] = (rand_df.drop(columns='runtime')>0).sum(axis=1)

    rand_df['coverage'] = rand_df['covered']/n_bins

    

    # 设置时间范围（可根据需要调整）

    time_lower = rand_df['runtime'].min()

    time_upper = rand_df['runtime'].max()

    

    # 过滤数据

    rand = rand_df[(rand_df['runtime']>=time_lower) & (rand_df['runtime']<=time_upper)]

    ours = ours_df[(ours_df['runtime']>=time_lower) & (ours_df['runtime']<=time_upper)]

    

    # 转换覆盖率为百分比

    rand['coverage'] *= 100

    ours['coverage'] *= 100

    

    # 创建图表

    plt.figure(figsize=(12, 6))

    

    # 绘制折线

    plt.plot(rand['runtime'], rand['coverage'], 'b-', label='Random', linewidth=2)

    plt.plot(ours['runtime'], ours['coverage'], 'r-', label='Ours', linewidth=2)

    

    # 标记最大覆盖率点

    rand_max_idx = rand['coverage'].idxmax()

    ours_max_idx = ours['coverage'].idxmax()

    
    plt.scatter(rand.loc[rand_max_idx, 'runtime'], rand.loc[rand_max_idx, 'coverage'], 
                color='blue', s=150, marker='^', zorder=5)
    plt.scatter(ours.loc[ours_max_idx, 'runtime'], ours.loc[ours_max_idx, 'coverage'], 
                color='red', s=150, marker='^', zorder=5)

    

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


    # 保存图表
    plt.tight_layout()
    plt.savefig('coverage_vs_runtime.png', dpi=300, bbox_inches='tight')
    plt.savefig('coverage_vs_runtime.svg', format='svg', bbox_inches='tight')
    print("图表已保存为 coverage_vs_runtime.png 和 coverage_vs_runtime.svg")



    plt.show()
if __name__ == "__main__":
    main()
