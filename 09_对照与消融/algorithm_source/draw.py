import marimo

__generated_with = "0.14.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    from glob import glob
    from tqdm import tqdm
    import bs4
    import re
    import joblib
    import altair as alt
    return alt, bs4, glob, joblib, mo, pd, re


@app.cell
def _(bs4, glob, joblib, pd, re):
    # loading data
    cp_pattern = re.compile(r'<p class="summary_title">(CoverPoint|CoverCross) Details: (.*)</p>')
    t_pattern = re.compile(r'">([^/]+)</t[hd]>')
    legal_pattern = re.compile(r'.*/[cp][0-9]*.html')
    runtime_pattern = re.compile(r'Times for simulation: run (\d+.\d+)s')
    pkg_pattern = re.compile(r'.*::')

    def collect_bin_cnt(report):
        bin_cnt = {}
        htmls = list(sorted(filter(lambda s: re.fullmatch(legal_pattern, s),glob(f'{report}/report/*.html'))))
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
                                    # parts = t_pattern.findall(str(c))
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
        data=list(sorted(glob(f'{data_dir}/**/dashboard.html', recursive=True)))
        print(data[:10])
        raw = joblib.Parallel(n_jobs=32)(joblib.delayed(process_data)(i, flag) for i in data)
        df = pd.DataFrame(raw).set_index('run').sort_index()
        # acc = pd.DataFrame(raw).set_index('run').fillna(0).cumsum()
        # coverage = (acc.drop(columns='runtime')>0).sum(axis=1)/(len(acc.columns)-1)
        # acc['coverage'] = coverage
        return df
    return (load_data,)


@app.cell
def _(pd):
    # df = pd.read_csv('/home/linb/bayes-uartcg/opentitan-verisim/bayes_opt/evaluate/bin_data.csv').drop(['run'], axis=1)
    df = pd.read_csv('/export/billchen/uart_coverage.csv').drop(['run'], axis=1)
    df
    return (df,)


@app.cell
def _(df):
    n_bins = len(df.columns)-1
    n_bins
    return (n_bins,)


@app.cell
def _(df):
    acc = df.cumsum()
    covered = (acc.drop(columns='runtime') > 0).sum(axis=1)
    acc['covered'] = covered
    acc
    return (acc,)


@app.cell
def _(acc):
    acc.iloc[-1]['runtime']
    return


@app.cell
def _(acc):
    acc[['covered','runtime']]
    return


@app.cell
def _(df, load_data, n_bins, pd):
    # ours_df=load_data('/home/linb/bayes-uartcg/opentitan-verisim/bayes_opt/evaluate/real_result_with_time', True).reset_index(drop=True).cumsum()
    # ours_df=load_data('/home/linb/bayes-uartcg/opentitan-verisim/bayes_opt/evaluate/real_result_with_time_45', True).reset_index(drop=True)
    ours_df=load_data('/export/billchen/result', True).reset_index(drop=True)
    print(ours_df)
    ours_df=pd.concat([df, ours_df]).reset_index(drop=True).cumsum()
    # ours_df=ours_df.cumsum()
    ours_df['covered'] = (ours_df.drop(columns='runtime')>0).sum(axis=1)
    ours_df['coverage'] = ours_df['covered']/n_bins
    return (ours_df,)


@app.cell
def _(ours_df):
    ours_df[ours_df['coverage']>=0.90][['runtime','covered','coverage']]-{'runtime':44053.34300000001+12347.451000000015, 'covered':0,'coverage':0}
    return


@app.cell
def _(df, load_data, n_bins, pd):
    # rand_df=load_data('/home/weijiepeng/pro/veri/data/25.07.24-ours')
    # rand_df=load_data('/home/weijiepeng/pro/veri/data/25.08.03-rand')
    # rand_df=load_data('/home/weijiepeng/pro/veri/data/25.07.24-rand').reset_index(drop=True)
    # rand_df=load_data('/home/linb/bayes-uartcg/opentitan-verisim/bayes_opt/evaluate/rand_45',True).reset_index(drop=True)
    rand_df=load_data('/export/billchen/baseline_uart_42_new',True).reset_index(drop=True)
    print(rand_df)
    rand_df=pd.concat([df, rand_df]).reset_index(drop=True).cumsum()
    # rand_df=rand_df.cumsum()

    # print(rand_df)
    # rand_df=pd.DataFrame(rand_df).reset_index(drop=True).cumsum()
    # rand_df=pd.concat([df, rand_df.sample(frac=1.).reset_index(drop=True)]).reset_index(drop=True).cumsum()
    rand_df['covered'] = (rand_df.drop(columns='runtime')>0).sum(axis=1)
    rand_df['coverage'] = rand_df['covered']/n_bins
    return (rand_df,)


@app.cell
def _(mo, ours_df, pd, rand_df):
    # 获取runtime范围
    all_runtime = pd.concat([rand_df['runtime'], ours_df['runtime']])
    min_runtime = all_runtime.min()
    max_runtime = all_runtime.max()
    
    # 时间范围滑块
    time_lower_slider = mo.ui.slider(start=min_runtime, stop=max_runtime, value=min_runtime, step=1, label="Runtime lower bound")
    time_upper_slider = mo.ui.slider(start=min_runtime, stop=max_runtime, value=max_runtime, step=1, label="Runtime upper bound")
    
    mo.md(f"""
    {time_lower_slider}
    {time_upper_slider}
    """)
    return (max_runtime, min_runtime, time_lower_slider, time_upper_slider)


@app.cell
def _(ours_df, pd, rand_df, time_lower_slider, time_upper_slider):
    time_lower = time_lower_slider.value
    time_upper = time_upper_slider.value
    rand=rand_df[(rand_df['runtime']>=time_lower) & (rand_df['runtime']<=time_upper)]
    ours=ours_df[(ours_df['runtime']>=time_lower) & (ours_df['runtime']<=time_upper)]
    # rand=rand_df
    # ours=ours_df
    rand['method'] = 'random'
    ours['method'] = 'ours'
    draw_df = pd.concat([rand,ours],ignore_index=True)
    draw_df = draw_df[['coverage','runtime','method']]
    draw_df['coverage']*=100
    # draw_df
    return (draw_df,)


@app.cell
def _(draw_df, mo):
    # 覆盖率范围滑块
    coverage_min = draw_df['coverage'].min() if not draw_df.empty else 0
    coverage_max = draw_df['coverage'].max() if not draw_df.empty else 100
    coverage_lower_slider = mo.ui.slider(start=0, stop=100, value=coverage_min, step=0.1, label="Coverage lower bound (%)")
    coverage_upper_slider = mo.ui.slider(start=0, stop=100, value=coverage_max, step=0.1, label="Coverage upper bound (%)")
    
    mo.md(f"""
    {coverage_lower_slider}
    {coverage_upper_slider}
    """)
    return (coverage_lower_slider, coverage_upper_slider)


@app.cell
def _(alt, coverage_lower_slider, coverage_upper_slider, draw_df, mo, pd):
    # 找每个 method 的最大 coverage 点
    max_points = draw_df.loc[draw_df.groupby('method')['coverage'].idxmax()]

    # 画图部分

    # 折线图
    line = alt.Chart(draw_df).mark_line().encode(
        x='runtime',
        y=alt.Y('coverage', scale=alt.Scale(domain=[coverage_lower_slider.value, coverage_upper_slider.value])),
        color='method'
    )

    # 最大点
    points = alt.Chart(max_points).mark_point(
        filled=True,
        size=100,
        shape='triangle'
    ).encode(
        x='runtime',
        y=alt.Y('coverage', scale=alt.Scale(domain=[coverage_lower_slider.value, coverage_upper_slider.value])),
        color='method'
    )

    # 最大值文字
    text = alt.Chart(max_points).mark_text(
        align='left',
        dx=5,
        dy=-5
    ).encode(
        x='runtime',
        y=alt.Y('coverage', scale=alt.Scale(domain=[coverage_lower_slider.value, coverage_upper_slider.value])),
        text=alt.Text('coverage:Q', format='.2f'),
        color='method'
    )

    # 合并所有图层
    chart = (line + points + text).properties(
        width=700,
        height=400,
        title="Coverage vs. Runtime"
    )
    mo.ui.altair_chart(chart)
    return (chart,)


@app.cell
def _(chart):
    chart.save('chart.png')
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
