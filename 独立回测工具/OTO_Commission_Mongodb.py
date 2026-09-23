import os
import re
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pymongo

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# ============ MongoDB 连接配置 ============
MONGO_HOST = "192.168.1.18"
MONGO_PORT = 17629
MONGO_USER = "hqy"
MONGO_PWD = "hqy888"
MONGO_DB = "StockBackSys"
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PWD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin&serverSelectionTimeoutMS=5000"

START_DATE = "2026-02-02" #回测开始时间
END_DATE = "2026-05-28" #回测结束时间

FACTOR_DIR_PATH = "/home/hqy/factor/orderBook/ema_orderBook_10_30"
FACTOR_NAME = "92456_diff"  #因子字段名
AimFACTOR_NAME = "CF_E"
GROUP_NUM = 10
REBALANCE_PERIOD_DAYS = int(os.environ.get("REBALANCE_PERIOD_DAYS", "1"))  # 调仓周期,默认保持原始每日调仓
RESULT_DIR = "/home/hqy/OTO-Commisson/BackTest/FactorGroupBacktest"
CHART_DIR = "/home/hqy/OTO-Commisson/FactorResearchResults/GroupTrendCharts/FactorResults"


def parse_args():
    parser = argparse.ArgumentParser(description="OTO 分组回测工具,支持设置调仓周期。")
    parser.add_argument(
        "--rebalance-period-days",
        type=int,
        default=REBALANCE_PERIOD_DAYS,
        help="调仓周期,单位为交易日。1 表示每日调仓,3 表示每 3 个交易日重新分组一次。",
    )
    return parser.parse_args()


def result_file_stem():
    if REBALANCE_PERIOD_DAYS == 1:
        return FACTOR_NAME
    return f"{FACTOR_NAME}_rebalance{REBALANCE_PERIOD_DAYS}D"


def get_mongo_db():
    """返回 StockBackSys 数据库连接,启动时校验连通性"""
    client = pymongo.MongoClient(MONGO_URI)
    client.admin.command('ping')
    return client[MONGO_DB]


def to_ymd(date_str):
    """'YYYY-MM-DD' -> 'YYYYMMDD'"""
    return date_str.replace("-", "")


def get_trade_dates():
    """000852.SH 的交易日历(YYYYMMDD 字符串,升序)"""
    db = get_mongo_db()
    return sorted(db["Index_DayLine"].distinct("trade_date", {"ts_code": "000852.SH"}))


def limit_ratio(code):
    """涨跌停比例:创业板/科创板 20%,其余 10%"""
    if code[:3] in ("300", "301", "688", "689"):
        return 0.20
    return 0.10


def get_price_panel(start, end):
    """批量拉取区间内日线,计算次日OTO涨跌幅与开盘涨跌停flag。

    返回 DataFrame 列: [code, trade_date, 次日OTO涨跌幅, open_cap, open_floor]
    trade_date 为 'YYYYMMDD' 字符串, code 为 6 位数字字符串。
    """
    start_ymd, end_ymd = to_ymd(start), to_ymd(end)
    trade_dates = get_trade_dates()
    next_dates = [d for d in trade_dates if d > end_ymd]
    if not next_dates:
        print(f"警告: {end} 已是 Mongo 数据最后一个交易日,末日次日OTO涨跌幅为空")
    fetch_end = next_dates[0] if next_dates else end_ymd
    years = set(range(int(start[:4]), int(end[:4]) + 1)) | {int(fetch_end[:4])}

    frames = []
    db = get_mongo_db()
    for year in years:
        coll = f"Stock_DayLine_{year}"
        if coll not in db.list_collection_names():
            raise ValueError(f"Mongo 集合不存在: {coll}")
        cursor = db[coll].find(
            {"trade_date": {"$gte": start_ymd, "$lte": fetch_end}},
            {"_id": 0, "ts_code": 1, "trade_date": 1, "open": 1, "close": 1, "pre_close": 1},
        )
        frames.append(pd.DataFrame(list(cursor)))
    panel = pd.concat(frames, ignore_index=True)
    if panel.empty:
        raise ValueError("price panel 为空,请检查日期范围或 Mongo 数据")

    panel["code"] = panel["ts_code"].str[:6]
    panel = panel.sort_values(["code", "trade_date"]).reset_index(drop=True)
    panel["pre_close"] = panel["pre_close"].replace(0, np.nan)
    panel["隔夜涨跌幅"] = panel["open"] / panel["pre_close"]
    panel["开盘后涨跌幅"] = panel["close"] / panel["open"]
    panel["次日_隔夜涨跌幅"] = panel.groupby("code")["隔夜涨跌幅"].shift(-1)
    panel["次日OTO涨跌幅"] = panel["开盘后涨跌幅"] * panel["次日_隔夜涨跌幅"]
    panel["ratio"] = panel["code"].apply(limit_ratio)
    up = (panel["pre_close"] * (1 + panel["ratio"])).round(2)
    dn = (panel["pre_close"] * (1 - panel["ratio"])).round(2)
    panel["open_cap"] = panel["open"] >= up - 0.001
    panel["open_floor"] = panel["open"] <= dn + 0.001
    return panel[["code", "trade_date", "次日OTO涨跌幅", "open_cap", "open_floor"]]


def get_st_panel(start, end):
    """批量拉取区间内股票名称,按名称含 ST 推算 is_st。

    返回 DataFrame 列: [code, trade_date, is_st]
    """
    start_ymd, end_ymd = to_ymd(start), to_ymd(end)
    years = set(range(int(start[:4]), int(end[:4]) + 1))

    frames = []
    db = get_mongo_db()
    for year in years:
        coll = f"stock_bak_daily_{year}"
        if coll not in db.list_collection_names():
            raise ValueError(f"Mongo 集合不存在: {coll}")
        cursor = db[coll].find(
            {"trade_date": {"$gte": start_ymd, "$lte": end_ymd}},
            {"_id": 0, "ts_code": 1, "trade_date": 1, "name": 1},
        )
        frames.append(pd.DataFrame(list(cursor)))
    panel = pd.concat(frames, ignore_index=True)
    if panel.empty:
        raise ValueError("st panel 为空")
    panel["code"] = panel["ts_code"].str[:6]
    panel["is_st"] = panel["name"].str.contains("ST", na=False)
    return panel[["code", "trade_date", "is_st"]]


def load_factor_data():
    """
    从文件夹中按yyyy-mm-dd格式的日期命名的CSV文件读取每一天的因子数据

    参数:
        folder_path: 包含因子数据CSV文件的文件夹路径

    返回:
        df: 合并后的因子数据DataFrame，包含['date', 'stock_code', 'factor_value']列
    """
    if REBALANCE_PERIOD_DAYS < 1:
        raise ValueError("REBALANCE_PERIOD_DAYS 必须 >= 1")

    ResultDict = {}
    datelist500 = [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in get_trade_dates()]
    price_panel = get_price_panel(START_DATE, END_DATE)
    st_panel = get_st_panel(START_DATE, END_DATE)

    # 确保文件夹存在
    if not os.path.exists(FACTOR_DIR_PATH):
        raise FileNotFoundError(f"因子数据文件夹不存在: {FACTOR_DIR_PATH}")

    # 获取文件夹中所有CSV文件
    files = [f for f in os.listdir(FACTOR_DIR_PATH) if f.endswith('.csv')]

    # 日期格式正则表达式 (yyyy-mm-dd)
    # date_pattern = re.compile(r'^\d{4}\d{2}\d{2}_df_mutiFactor\.csv$')
    # date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}\.csv$')
    date_pattern = re.compile(r'^\d{4}\d{2}\d{2}\.csv$')

    # 筛选符合日期格式的文件
    date_files = [f for f in files if date_pattern.match(f)]
    date_files.sort()

    if not date_files:
        raise ValueError(f"在{FACTOR_DIR_PATH}中没有找到符合yyyy-mm-dd格式的CSV文件")

    pre_dict_df = {i:[] for i in range(GROUP_NUM)}   # 上个交易日每组的持仓股票 键为组号，值为持仓股票代码列表
    processed_trade_day_count = 0
    # 读取每个日期文件并合并数据
    for file_name in date_files:
        # 从文件名中提取日期
        # tDate = file_name.replace('_df_mutiFactor.csv', '')
        # tDate = tDate[0:4] + '-' + tDate[4:6] + "-" + tDate[6:]

        tDate = file_name.replace('.csv', '')

        temp_c_data = int(tDate.replace("-", ""))
        tDate = tDate[0:4] + '-' + tDate[4:6] + "-" + tDate[6:]

        fee_ratio = 0.0
        if temp_c_data <= 20231231:
            fee_ratio = 0.0007 # 双边手续费
        else:
            fee_ratio = 0.00035 # 双边手续费

        if tDate < START_DATE or tDate > END_DATE:
            continue

        # 读取CSV文件
        file_path = os.path.join(FACTOR_DIR_PATH, file_name)
        FactorDF = pd.read_csv(file_path,index_col=0,dtype={'code': str,"ts_code":str})

        if 'symbol' in FactorDF.columns:
            FactorDF.rename(columns={'symbol': 'code'}, inplace=True)

        if 'ts_code' in FactorDF.columns:
            FactorDF.rename(columns={'ts_code': 'code'}, inplace=True)

        FactorDF['code'] = FactorDF.index
        FactorDF['code'] = FactorDF['code'].apply(lambda x: x[:6])
        FactorDF['code'] = FactorDF['code'].astype(int)
        FactorDF['code'] = FactorDF['code'].apply(lambda x: str(x).zfill(6))
        print(f"读取因子文件{file_name}成功")
        # 确保CSV文件包含必要的列
        if 'code' not in FactorDF.columns or FACTOR_NAME not in FactorDF.columns:
            print(f"警告: 文件{file_name}不包含必要的列(code, {FACTOR_NAME})，跳过此文件")
            continue

        #######################################################################################
        FactorDF = FactorDF[['code', FACTOR_NAME]]        # 只保留必要的列
        #归一化
        #FactorDF[FACTOR_NAME] = (FactorDF[FACTOR_NAME] - FactorDF[FACTOR_NAME].min()) / (FactorDF[FACTOR_NAME].max() - FactorDF[FACTOR_NAME].min())
        FactorDF = FactorDF[FactorDF['code'].str.endswith('BJ') == False]  # 过滤北交所

        FactorDF = FactorDF.sort_values(FACTOR_NAME, ascending=True)
        FactorDF = FactorDF.dropna()
        #######################################################################################

        # 添加日期列
        FactorDF['date'] = tDate
        # 过滤开盘涨跌停的股票(无法交易的股票)
        tDate_ymd = to_ymd(tDate)
        t_prices = price_panel[price_panel["trade_date"] == tDate_ymd]
        if t_prices.empty:
            print(f"警告: {tDate} 在价格面板中无数据,跳过当日")
            continue
        return_by_code = t_prices.set_index("code")["次日OTO涨跌幅"]
        max_min_lst = t_prices[(t_prices["open_cap"]) | (t_prices["open_floor"])]["code"].tolist()
        FactorDF = FactorDF[~FactorDF["code"].isin(max_min_lst)]

        #过滤ST
        t_st = st_panel[st_panel["trade_date"] == tDate_ymd]
        sfe_Lst = t_st[t_st["is_st"]]["code"].tolist()
        FactorDF = FactorDF[~FactorDF["code"].isin(sfe_Lst)]

        # 读取每日涨跌幅数据(从 Mongo 价格面板)
        PctData = t_prices[["code", "次日OTO涨跌幅"]]

        #过滤FactorDF中没有的股票
        PctData = PctData[PctData['code'].isin(FactorDF['code'])]

        # 以code字段为键，将PctData和FactorDF合并
        PctData = PctData.set_index('code')
        FactorDF = FactorDF.set_index('code')
        FactorDF = FactorDF.join(PctData)
        FactorDF = FactorDF.reset_index()

        is_rebalance_day = processed_trade_day_count % REBALANCE_PERIOD_DAYS == 0
        if is_rebalance_day:
            # 按因子值大小分10组
            # 添加微小随机噪声（如1e-8量级，远小于数据本身的波动）
            noisy_factor = FactorDF[FACTOR_NAME] + np.random.normal(0, 1e-8, size=len(FactorDF))
            FactorDF[f'{FACTOR_NAME}_group'] = pd.qcut(noisy_factor, GROUP_NUM, labels=False)

        # 计算每组的平均涨跌幅,存入ResultDict
        for i in range(GROUP_NUM):
            if is_rebalance_day:
                tGroup = FactorDF[FactorDF[f'{FACTOR_NAME}_group'] == i]
                cur_port_lst = tGroup['code'].tolist()
            else:
                cur_port_lst = pre_dict_df[i]

            ######## 计算该组换仓手续费(每组股票等权持有)
            fee = 0
            if is_rebalance_day:
                pre_port_lst = pre_dict_df[i]
                denominator = max(len(cur_port_lst), len(pre_port_lst))
                fee = len(set(cur_port_lst) - set(pre_port_lst)) * 2 * fee_ratio / denominator if denominator else 0
                pre_dict_df[i] = cur_port_lst
            ########################################

            tGroup = return_by_code.reindex(cur_port_lst).dropna()
            if i not in ResultDict:
                ResultDict[i] = {}
            ResultDict[i][tDate] = tGroup.mean() - 1 - fee if len(tGroup) else np.nan
            print(tDate, i, ResultDict[i][tDate], fee, "rebalance" if is_rebalance_day else "hold")

        processed_trade_day_count += 1

    # 检查回测区间内是否有交易日因价格数据缺失被跳过
    expected_days = [d for d in datelist500 if START_DATE <= d <= END_DATE]
    processed_days = set().union(*(v.keys() for v in ResultDict.values())) if ResultDict else set()
    missing_days = [d for d in expected_days if d not in processed_days]
    if missing_days:
        print(f"警告: 以下交易日未参与回测(共{len(missing_days)}天,可能因缺少价格数据或因子文件): {missing_days}")

    ResultDict = pd.DataFrame(ResultDict)
    ResultDict = ResultDict.sort_index()
    os.makedirs(RESULT_DIR, exist_ok=True)
    ResultDict.to_csv(os.path.join(RESULT_DIR, f"{result_file_stem()}.csv"), index=True)
    print(f"保存{result_file_stem()}数据成功,调仓周期={REBALANCE_PERIOD_DAYS}个交易日,收益日数={processed_trade_day_count}")

    # 将每天的分组计算存文件
    # for i, tGroup in ResultDict.items():
    #     tGroup = pd.DataFrame(tGroup).T
    #     # 按日期排序
    #     tGroup = tGroup.sort_index()
    #     tGroup.to_csv(os.path.join("/home/hqy/OTO-Commisson/BackTest/FactorGroupBacktest", f"{i}.csv"), index=True)
    #     print(f"保存{i}数据成功")


def DrawLineChart():
    #读取每日市值分组收益拆分数据
    local_file = os.path.join(RESULT_DIR, f"{result_file_stem()}.csv")
    stock_data = pd.read_csv(local_file, index_col=0)
    #计算每日的累加值
    stock_data = stock_data.cumsum()
    #画折线图
    ax = stock_data.plot()
    plt.title(f'{AimFACTOR_NAME}_Group_Recv', fontsize=14)
    plt.grid(True, linestyle='--', alpha=0.7)

    # 将图例移到图表外侧右上角,避免遮挡最新的折线走势
    ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0, fontsize=8)

    # 调整布局(为外侧图例留出空间)
    plt.tight_layout()

    # 保存图表
    os.makedirs(CHART_DIR, exist_ok=True)
    plt.savefig(os.path.join(CHART_DIR, f"{AimFACTOR_NAME}_Group_Recv_rebalance{REBALANCE_PERIOD_DAYS}D.png"), dpi=300, bbox_inches='tight')
    plt.close()


if __name__ == "__main__":
    args = parse_args()
    REBALANCE_PERIOD_DAYS = args.rebalance_period_days
    load_factor_data()
    DrawLineChart()
