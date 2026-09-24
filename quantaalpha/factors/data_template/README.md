# How to read files.
For example, if you want to read `filename.h5`
```Python
import pandas as pd
df = pd.read_hdf("filename.h5", key="data")
```
NOTE: **key is always "data" for all hdf5 files **.

# Here is a short description about the data

| Filename       | Description                                                      |
| -------------- | -----------------------------------------------------------------|
| "daily_pv.h5"  | Adjusted daily price and volume data.                            |


# For different data, We have some basic knowledge for them

## Daily data variables
$open: open price of the stock on that day.
$close: close price of the stock on that day.
$high: high price of the stock on that day.
$low: low price of the stock on that day.
$volume: volume of the stock on that day.
$amount: trading amount of the stock on that day.
$vwap: volume-weighted average price, derived as $amount / ($volume + 1e-8).
$return: daily return of the stock on that day.
$swing: intraday amplitude of the stock on that day.
$volume_ratio: volume ratio, comparing current volume with recent average volume.
$turnover_rate: turnover rate based on float shares.
$turnover_rate_f: turnover rate based on free-float shares.
$total_mv: total market capitalization.
$float_mv: float market capitalization.
$pe: price-to-earnings ratio. Missing or NaN values are filled with 0.
$pe_ttm: trailing-twelve-month price-to-earnings ratio. Missing or NaN values are filled with 0.
$pb: price-to-book ratio.
$ps_ttm: trailing-twelve-month price-to-sales ratio.
$buy_sm_vol: small-order buy volume.
$buy_sm_amount: small-order buy amount.
$sell_sm_vol: small-order sell volume.
$sell_sm_amount: small-order sell amount.
$buy_lg_vol: large-order buy volume.
$buy_lg_amount: large-order buy amount.
$sell_lg_vol: large-order sell volume.
$sell_lg_amount: large-order sell amount.
$net_mf_vol: net money-flow volume.
$net_mf_amount: net money-flow amount.
$buying: outside volume; trades executed at seller quotes, indicating buyer-initiated order-taking.
$selling: inside volume; trades executed at buyer quotes, indicating seller-initiated order-hitting.
