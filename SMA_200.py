# ------------------------------------------------------------
# Library ----------------------------------------------------
# ------------------------------------------------------------
# %%
import requests
import pandas as pd
from datetime import datetime, timezone
import time
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from IPython.display import display, Markdown

# ------------------------------------------------------------
# Data block -------------------------------------------------
# ------------------------------------------------------------
# %%

URL = "https://api.binance.com/api/v3/klines"

def fetch_binance_klines(symbol, interval, start, end):
    
    all_chunks = []
    # Binance wants milliseconds since epoch
    start_ms = int(start.timestamp() * 1000)
    end_ms   = int(end.timestamp()   * 1000)
    
    while start_ms < end_ms:
        params = {
            "symbol":    symbol,
            "interval":  interval,
            "startTime": start_ms,
            "endTime":   end_ms,
            "limit":     1000,         
        }
        r = requests.get(URL, params=params, timeout=30)


        r.raise_for_status()             
        raw = r.json()
        if not raw:                     
            break
        
        chunk = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        
        chunk = chunk[["open_time", "open", "high", "low", "close", "volume"]].copy()

        chunk["open_time"] = pd.to_datetime(chunk["open_time"], unit="ms", utc=True)
        chunk = chunk.rename(columns={"open_time": "time"})
        
        for col in ["open", "high", "low", "close", "volume"]:
            chunk[col] = pd.to_numeric(chunk[col])

                    
        all_chunks.append(chunk)
        print(f"Fetched up to {chunk['time'].iloc[-1].date()}  ({len(all_chunks)*1000:,} bars so far)")

        # Advance cursor to just after the last bar we received
        last_open_ms = int(raw[-1][0])
        start_ms = last_open_ms + 1
        
        time.sleep(0.1)                  
    
    if not all_chunks:
        return pd.DataFrame()
    
    df = pd.concat(all_chunks, ignore_index=True)
    df = df[df["time"] < end].reset_index(drop=True)   
    return df

# ------------------------------------------------------------
# Data download ----------------------------------------------
# ------------------------------------------------------------
# %%

start = datetime(2019, 1, 1, tzinfo=timezone.utc)
end   = datetime(2025, 1, 1, tzinfo=timezone.utc)

btc = fetch_binance_klines("BTCUSDT", "15m", start, end)

# ------------------------------------------------------------
# crossover_points -------------------------------------------
# ------------------------------------------------------------
# %%

close = btc["close"].set_axis(btc["time"])
sma200 = close.rolling(window=200).mean().set_axis(btc["time"])

diff = close - sma200

crossovers_above = close.index[ 
    (close>sma200) & 
    (diff.shift(1) * diff < 0) ]

crossovers_below = close.index[
    (close<sma200) & (
    (diff.shift(1) * diff < 0) |
    ((diff == 0) & (diff.shift(1) != 0)))]

#? Below includes 0

# ------------------------------------------------------------
# Profit calculation -----------------------------------------
# ------------------------------------------------------------
# %%

price_buy = close.loc[crossovers_above]
price_sell = close.loc[crossovers_below]

# If the first crossover is a sell, we'd be exiting a position we never opened — drop it.
if price_sell.index[0] < price_buy.index[0]:
    price_sell = price_sell.iloc[1:]

n = min(len(price_buy), len(price_sell))
profit = pd.Series(
    price_sell.values[:n] - price_buy.values[:n],   
    index=price_buy.index[:n],                       
)

print(f"Total profit: {profit.sum():.4f}")
print(f"# trades:     {n}")

# ------------------------------------------------------------
# take profit  -----------------------------------------------
# ------------------------------------------------------------
# %%

TP_PCT = 0.15
trades = []

for buy_time in price_buy.index:           
    next_sells = crossovers_below[crossovers_below > buy_time]
    if len(next_sells) == 0:
        break
    sell_time = next_sells[0]                

    buy    = close.loc[buy_time]
    target = buy * (1 + TP_PCT)
    window = close.loc[buy_time : sell_time]
    hit    = window >= target

    if hit.any():
        exit_price, kind = target, "TP"
    else:
        exit_price, kind = close.loc[sell_time], "signal"

    trades.append({
        "buy_time":  buy_time,
        "buy_price": buy,
        "exit_time": sell_time,
        "exit_price": exit_price,
        "exit_kind": kind,
        "profit":    exit_price - buy,
    })

trades = pd.DataFrame(trades)

display(Markdown(f"### PROFIT: {trades.profit.sum().round(2)}"))
print("TRADES: ", trades.exit_kind.value_counts())
print("-------------------------")
print(trades.exit_price )
print("-------------------------")
print(trades.loc[trades["exit_kind"] == "TP", "buy_time"])


#!------------------------------------------------------------
#!---------------------SMALL DATA-----------------------------
#!------------------------------------------------------------
#! SET INDEX HERE:
# %%

btc_small = btc[
    (btc["time"] >= "2019-05-07") & 
    (btc["time"] <  "2019-06-23")
].copy()


# ------------------------------------------------------------
# Graph ------------------------------------------------------
# ------------------------------------------------------------
# %%

btc_small_plot = go.Figure(data=[go.Candlestick(
    x=btc_small["time"],
    open=btc_small["open"],
    high=btc_small["high"],
    low=btc_small["low"],
    close=btc_small["close"]
)])
btc_small_plot.show(renderer="browser")


# ------------------------------------------------------------
# SMA_200 graph ----------------------------------------------
# ------------------------------------------------------------
# %%

close_1  = close.iloc[btc_small.index[0]:btc_small.index[-1]+1]    
sma200_1 = sma200.iloc[btc_small.index[0]:btc_small.index[-1]+1]  
crossovers_above_1 = crossovers_above.intersection(close_1.index)
crossovers_below_1 = crossovers_below.intersection(close_1.index)


close_1.plot(label="BTC")
sma200_1.plot(label="SMA 200")
close_1.loc[crossovers_above_1].plot(marker="x", linestyle="None", color="green", label="buy")
close_1.loc[crossovers_below_1].plot(marker="o", linestyle="None", color="red", label="sell")
plt.legend()
plt.show()

# ------------------------------------------------------------
# Small profit calculation -----------------------------------
# ------------------------------------------------------------
# %%

price_buy_1 = close.loc[crossovers_above_1]
price_sell_1 = close.loc[crossovers_below_1]

if price_sell_1.index[0] < price_buy_1.index[0]:
    price_sell_1 = price_sell_1.iloc[1:]

n = min(len(price_buy_1), len(price_sell_1))
profit = pd.Series(
    price_sell_1.values[:n] - price_buy_1.values[:n],   
    index=price_buy_1.index[:n],                       
)

print(profit.to_frame("profit"))
print(f"Total profit: {profit.sum():.4f}")
print(f"# trades:     {n}")

# ------------------------------------------------------------
# Small take profit  -----------------------------------------
# ------------------------------------------------------------
# %%

TP_PCT_1 = 0.15
trades_1 = []

for buy_time in price_buy_1.index:           
    next_sells = crossovers_below[crossovers_below > buy_time]
    if len(next_sells) == 0:
        break
    sell_time = next_sells[0]                

    buy    = close.loc[buy_time]
    target = buy * (1 + TP_PCT_1)
    window = close.loc[buy_time : sell_time]
    hit    = window >= target

    if hit.any():
        exit_price, kind = target, "TP"
    else:
        exit_price, kind = close.loc[sell_time], "signal"

    trades_1.append({
        "buy_time":  buy_time,
        "buy_price": buy,
        "exit_time": sell_time,
        "exit_price": exit_price,
        "exit_kind": kind,
        "profit":    exit_price - buy,
    })

trades_1 = pd.DataFrame(trades_1)

display(Markdown(f"### PROFIT: {trades_1.profit.sum().round(2)}"))
print("TRADES: ", trades_1.exit_kind.value_counts())
print("-------------------------")
print(trades_1.exit_price )
print("-------------------------")
print(trades_1.loc[trades_1["exit_kind"] == "TP", "buy_time"])


# ------------------------------------------------------------
# Some things to consider  -----------------------------------
# ------------------------------------------------------------
# %%

#? Cheek a vice versa strategy where we sell when the price is above sma200 and buy when its below
#? It would be nice to put stop loss as well because there are huge outliers candels 




