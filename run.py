import configparser
import shift
import numpy as np
import pandas as pd
import sys
import time
import threading
import os
import csv
from datetime import datetime


def quote_spreads(trader: shift.Trader, symbol):
    bp = trader.get_best_price(symbol)
    time.sleep(1)
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()

    # place order at best bid
    lb_buy = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, 1, best_bid)
    trader.submit_order(lb_buy)
    time.sleep(1)

    # place order at best ask
    lb_sell = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, 1, best_ask)
    trader.submit_order(lb_sell)
    time.sleep(1)

    print(f"symbol {symbol} best bid: {best_bid}, best ask: {best_ask} submitted")


def quote_spreads_ma(trader: shift.Trader, symbol, ma10, ma30):
    bp = trader.get_best_price(symbol)
    time.sleep(1)
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()
    mid_price = 0.5 * (best_ask + best_bid)
    print(f"[INFO] [{symbol}], Mid-price: {mid_price:.2f}, MA10: {ma10:.2f}, MA30: {ma30:.2f}")
    bid_price = 0
    ask_price = 0
    tick = 0.02
    if mid_price > ma10 and ma10 > ma30:
        # Trend is up → quote more aggressively to buy
        bid_price = mid_price + tick  # more aggressive bid
        ask_price = mid_price + 2 * tick  # further ask
    elif mid_price < ma10 and ma10 < ma30:
        # Trend is down → quote more aggressively to sell
        ask_price = mid_price - tick  # more aggressive ask
        bid_price = mid_price - 2 * tick  # further bid
    else:
        return

    # Round to two decimal places (SHIFT doesn't allow infinite precision)
    bid_price = round(bid_price, 2)
    ask_price = round(ask_price, 2)

    # place order at best bid
    lb_buy = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, 1, bid_price)
    trader.submit_order(lb_buy)
    time.sleep(1)

    # place order at best ask
    lb_sell = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, 1, ask_price)
    trader.submit_order(lb_sell)
    time.sleep(1)
    print(f"[{symbol}] bid: {bid_price}, ask: {ask_price} submitted")


def directional_quote(trader, symbol, ma10, ma30, macd, signal, upper_band, lower_band, vol, trend):

    # get mid price
    bp = trader.get_best_price(symbol)
    time.sleep(1)
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()
    mid_price = 0.5 * (best_bid + best_ask)

    # determine tick size according to vol
    tick = 0.03

    new_trend = trend

    # filtering if the momentum is low or noise
    macd_gap = abs(macd - signal)
    macd_threshold = 0.1 * vol * mid_price  # adjustable multiplier

    # Skip weak signals based on MACD gap
    if macd_gap < macd_threshold:
        print(f"[{symbol}] [FILTERED] MACD gap too small ({macd_gap:.5f} < {macd_threshold:.5f})")
        return new_trend


    # === UP Trend Logic ===
    if trend == "UP":
        if ma30 < ma10 < mid_price and macd > signal:
            if mid_price > upper_band and (mid_price-upper_band) > 0.5:
                print(f"[{symbol}] Mid price above upper band - overextended. Skipping trade or sell here")
                cancel_orders(trader, symbol)
                liquidate_symbol(trader, symbol)
            else:
                bid_price = round(mid_price + tick, 2)
                order = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, 1, bid_price)
                trader.submit_order(order)
                print(f"[{symbol}] [UP] Submitting BID @ {bid_price}")
        elif (ma10 < ma30 or macd < signal) and macd_gap >= macd_threshold:
            print(f"[{symbol}] [UP END] Reversing Trend → NEUTRAL")
            cancel_orders(trader, symbol)
            liquidate_symbol(trader, symbol)
            new_trend = "NEUTRAL"

    # === DOWN Trend Logic ===
    elif trend == "DOWN":
        if ma30 > ma10 > mid_price and macd < signal:
            if mid_price < lower_band and (lower_band - mid_price) > 0.5:
                print(f"[{symbol}] Mid price below lower band - overextended. Skipping trade or buy here")
                cancel_orders(trader, symbol)
                liquidate_symbol(trader, symbol)
            else:
                ask_price = round(mid_price - tick, 2)
                order = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, 1, ask_price)
                trader.submit_order(order)
                print(f"[{symbol}] [DOWN] Submitting ASK @ {ask_price}")
        elif (ma10 > ma30 or macd > signal) and macd_gap >= macd_threshold:
            print(f"[{symbol}] [DOWN END] Reversing Trend → NEUTRAL")
            cancel_orders(trader, symbol)
            liquidate_symbol(trader, symbol)
            new_trend = "NEUTRAL"

    # === NEUTRAL Logic → Look for New Trend ===
    elif trend == "NEUTRAL":
        if ma10 > ma30 and macd > signal and mid_price > ma10 and macd_gap >= macd_threshold:
            if mid_price <= upper_band:
                new_trend = "UP"
                bid_price = round(mid_price + tick, 2)
                order = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, 1, bid_price)
                trader.submit_order(order)
                print(f"[{symbol}] [TREND START] UP → Submitting BID @ {bid_price}")
        elif ma10 < ma30 and macd < signal and mid_price < ma10:
            if mid_price >= lower_band:
                new_trend = "DOWN"
                ask_price = round(mid_price - tick, 2)
                order = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, 1, ask_price)
                trader.submit_order(order)
                print(f"[{symbol}] [TREND START] DOWN → Submitting ASK @ {ask_price}")

    return new_trend


def spread_capture(trader, symbol, vol, upper_band, lower_band, timeout=30):

    should_place_bid = True
    should_place_ask = True

    # Get mid price
    bp = trader.get_best_price(symbol)
    time.sleep(1)
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()
    mid_price = 0.5 * (best_bid + best_ask)

    # Get vwap for ask and bid
    bid_vwap = get_vwap(trader, symbol, shift.OrderBookType.GLOBAL_BID)
    ask_vwap = get_vwap(trader, symbol, shift.OrderBookType.GLOBAL_ASK)

    bid_pressure = bid_vwap - best_bid  # Positive means buying pressure
    ask_pressure = ask_vwap - best_ask  # Negative means selling pressure
    pressure_threshold = 0.2
    should_place_bid = abs(bid_pressure) <= pressure_threshold  # Place bid if pressure is within threshold
    should_place_ask = abs(ask_pressure) <= pressure_threshold  # Place ask if pressure is within threshold

    bid_adjustment = bid_pressure * 1.0  # Adjusting factor (scaling pressure effect)
    ask_adjustment = ask_pressure * 1.0  # Adjusting factor (scaling pressure effect)

    # Check if price is within Bollinger Band
    band_buffer = 0.0015 * mid_price  # e.g., 0.1% of mid price
    if mid_price > upper_band - band_buffer or mid_price < lower_band + band_buffer:
        print(f"[{symbol}] Skipping quote — price outside Bollinger Band")
        return

    # Tick size: bounded between 0.02 and 0.04
    base_tick = 0.01
    tick = round(min(0.03, max(base_tick, 2 * vol * mid_price)), 2)

    # Adjust bid and ask prices further based on tick
    bid_price = round(best_bid + tick + bid_adjustment, 2)
    ask_price = round(best_ask - tick + ask_adjustment, 2)

    # Get inventory
    item = trader.get_portfolio_item(symbol)
    long_shares = item.get_long_shares() / 100  # in lots of 100
    short_shares = item.get_short_shares() / 100

    # Net position
    net_pos = long_shares - short_shares

    # Base order size
    base_size = 1
    buy_size = int(base_size + short_shares)
    sell_size = int(base_size + long_shares)

    # Optional cap on max order size
    buy_size = min(buy_size, 5)
    sell_size = min(sell_size, 5)

    # Submit both orders
    buy_order = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, buy_size, bid_price)
    sell_order = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, sell_size, ask_price)
    if should_place_bid:
        trader.submit_order(buy_order)
        print(f"[{symbol}] Placing BID @ {bid_price} with size {buy_size}")
    if should_place_ask:
        trader.submit_order(sell_order)
        print(f"[{symbol}] Placing ASK @ {ask_price} with size {sell_size}")

    # Let orders sit briefly
    time.sleep(timeout)

    # Cancel all remaining open orders
    cancel_orders(trader, symbol)


def place_vwap_neutral_orders(trader, symbol, vol, pressure_threshold, alpha, timeout=30):
    # Get top-of-book
    bp = trader.get_best_price(symbol)
    time.sleep(0.5)
    # Get best bid and ask prices
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()
    mid_price = (best_bid + best_ask) / 2

    # VWAPs
    # we get the total volume here to use in OBI
    (bid_vwap, bid_volume) = get_vwap(trader, symbol, shift.OrderBookType.LOCAL_BID)
    (ask_vwap, ask_volume) = get_vwap(trader, symbol, shift.OrderBookType.LOCAL_ASK)
    
    # Pressure
    bid_pressure = bid_vwap - best_bid
    ask_pressure = ask_vwap - best_ask

    # Trade filters
    should_place_bid = abs(bid_pressure) <= pressure_threshold
    should_place_ask = abs(ask_pressure) <= pressure_threshold

    # Tick size logic
    base_tick = 0.01
    tick = round(min(0.03, max(base_tick, 2 * vol * mid_price)), 2)

    # Adjusted quotes
    bid_price = round(best_bid + tick + bid_pressure, 2)
    ask_price = round(best_ask - tick + ask_pressure, 2)

    # Inventory & size logic
    item = trader.get_portfolio_item(symbol)
    #net_pos = (item.get_long_shares() - item.get_short_shares()) / 100

    # Order Book Imbalance (OBI) for size calculation
    obi = (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) != 0 else 0

    # Base order size
    # from 3 to 5 capped

    # if our position is very short, we'll buy more
    buy_size = min(int(int(5 + item.get_short_shares() / 100) * (1 - alpha * obi)), 10)
    # if our position is very long, we'll sell more
    sell_size = min(int(int(5 + item.get_long_shares() / 100) * (1 + alpha * obi)), 10)

    # Submit new orders
    if should_place_bid:
        buy_order = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, buy_size, bid_price)
        trader.submit_order(buy_order)
        print(f"[{symbol}] BID {buy_size} @ {bid_price}")

    if should_place_ask:
        sell_order = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, sell_size, ask_price)
        trader.submit_order(sell_order)
        print(f"[{symbol}] ASK {sell_size} @ {ask_price}")
    
    # timeout
    time.sleep(timeout)

    # Cancel all remaining open orders
    cancel_orders(trader, symbol)

def log_market_data_to_csv(trader, symbol, vol, upper_band, lower_band, pnl, filename="market_log.csv"):
    bp = trader.get_best_price(symbol)
    time.sleep(0.5)
    best_bid = bp.get_bid_price()
    best_ask = bp.get_ask_price()
    mid_price = 0.5 * (best_bid + best_ask)
    # Get vwap for ask and bid
    bid_vwap = get_vwap(trader, symbol, shift.OrderBookType.LOCAL_BID)
    ask_vwap = get_vwap(trader, symbol, shift.OrderBookType.LOCAL_ASK)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Check if file exists and header is present
    file_exists = os.path.isfile(filename)
    write_header = not file_exists or os.path.getsize(filename) == 0

    with open(filename, mode="a", newline="") as file:
        writer = csv.writer(file)

        if write_header:
            writer.writerow(["Timestamp", "Symbol", "MidPrice", "Volatility", "BestBid", "BestAsk", "UpperBand", "LowerBand", "BidVWAP", "AskVWAP", "PNL"])

        writer.writerow([timestamp, symbol, mid_price, vol, best_bid, best_ask, upper_band, lower_band, bid_vwap, ask_vwap, pnl])

def get_submitted_request(trader):
    print(
        "Symbol\t\t\t\tType\t  Price\t\tSize\tExecuted\tID\t\t\t\t\t\t\t\t\t\t\t\t\t\t Status\t\tTimestamp"
    )
    time.sleep(1)
    for order in trader.get_submitted_orders():
        time.sleep(0.5)
        if order.status == shift.Order.Status.FILLED:
            price = order.executed_price
        else:
            price = order.price
        print(
            "%6s\t%16s\t%7.2f\t\t%4d\t\t%4d\t%36s\t%23s\t\t%26s"
            % (
                order.symbol,
                order.type,
                price,
                order.size,
                order.executed_size,
                order.id,
                order.status,
                order.timestamp,
            )
        )
    

def write_order_logs_to_file(trader, filename):
    file = open(filename, "a")
    orders = trader.get_submitted_orders()
    time.sleep(1)
    # check if file has headers
    if not file.tell():
        file.write("Symbol,Type,Price,Executed_Price,Size,Executed_Size,ID,Status,Timestamp\n")
    for order in orders:
        file.write(
            f"{order.symbol},{order.type},{order.price},{order.executed_price},{order.size},{order.executed_size},{order.id},{order.status},{order.timestamp}\n")
    file.close()


def get_portfolio_summary(trader):
    print("Buying Power\tTotal Shares\tTotal P&L\tTimestamp")
    time.sleep(0.5)
    print(
        "%12.2f\t%12d\t%9.2f\t%26s"
        % (
            trader.get_portfolio_summary().get_total_bp(),
            trader.get_portfolio_summary().get_total_shares(),
            trader.get_portfolio_summary().get_total_realized_pl(),
            trader.get_portfolio_summary().get_timestamp(),
        )
    )
    time.sleep(0.5)


def liquidify_portfolio(trader):
    for item in trader.get_portfolio_items().values():
        symbol = item.get_symbol()
        long = item.get_long_shares()
        short = item.get_short_shares()


        if long > 0:
            print(f"Liquidate [{symbol}] Long positions: {long}")
            order = shift.Order(shift.Order.Type.MARKET_SELL, symbol, int(long/100))
            trader.submit_order(order)
        elif short > 0:
            print(f"Liquidate [{symbol}] Short positions: {short}")
            order = shift.Order(shift.Order.Type.MARKET_BUY, symbol, int(short/100))
            trader.submit_order(order)

        print("Symbol\t\tShares\t\tPrice\t\tP&L\t\tTimestamp")
        print(
            "%6s\t\t%6d\t%9.2f\t%7.2f\t\t%26s"
            % (
                item.get_symbol(),
                item.get_shares(),
                item.get_price(),
                item.get_realized_pl(),
                item.get_timestamp(),
            )
        )

def liquidate_symbol(trader, symbol):
    item = trader.get_portfolio_item(symbol)
    if item.get_shares() != 0:
        long = item.get_long_shares()
        short = item.get_short_shares()
        if long > 0:
            print(f"Liquidate [{symbol}] Long positions: {long}")
            order = shift.Order(shift.Order.Type.MARKET_SELL, symbol, int(long/100))
            trader.submit_order(order)
        elif short > 0:
            print(f"Liquidate [{symbol}] Short positions: {short}")
            order = shift.Order(shift.Order.Type.MARKET_BUY, symbol, int(short/100))
            trader.submit_order(order)
    else:
        print(f"[Liquidate] No positions in [{symbol}]")


def cancel_orders(trader, ticker):
    for order in trader.get_waiting_list():
        if order.symbol == ticker:
            print(f"[Cancel Order] {order.size} {order.type} order(s) of [{ticker}] in waiting list")
            trader.submit_cancellation(order)
        time.sleep(0.5)



def get_10ma(prices):
    if len(prices) < 10:
        return sum(prices) / len(prices)
    return sum(prices[-10:]) / 10


def get_30ma(prices):
    if len(prices) < 30:
        return sum(prices) / len(prices)
    return sum(prices[-30:]) / 30

def get_ema(prices, span):
    """
    Calculates the Exponential Moving Average (EMA) for a list of prices.
    :param prices: List or pd.Series of prices (e.g., mid-prices)
    :param span: Lookback period for EMA (e.g., 12, 26, 9)
    :return: pd.Series of EMA values
    """
    return pd.Series(prices).ewm(span=span, adjust=False).mean()

def get_macd_signal(prices, fast=12, slow=26, signal=9):
    """
    Calculates MACD, signal line, and histogram from price series.
    :param prices: List or pd.Series of prices
    :param fast: Fast EMA period (default: 12)
    :param slow: Slow EMA period (default: 26)
    :param signal: Signal line EMA period (default: 9)
    :return: macd, signal line, histogram (pd.Series)
    """
    price_series = pd.Series(prices)
    ema_fast = get_ema(price_series, fast)
    ema_slow = get_ema(price_series, slow)
    macd = ema_fast - ema_slow
    signal_line = get_ema(macd, signal)
    histogram = macd - signal_line
    return macd.iat[-1], signal_line.iat[-1], histogram.iat[-1]

def get_vol(log_returns):
    return pd.Series(log_returns).std()

def get_boll_band(prices):
    if len(prices) < 20:
        return None, None  # Not enough data

    window = prices[-20:]  # Last 20 prices

    # Calculate 20-period mean
    ma20 = sum(window) / len(window)

    # Calculate 20-period sample standard deviation
    mean_diff_squared = [(p - ma20) ** 2 for p in window]
    std20 = (sum(mean_diff_squared) / (len(window) - 1)) ** 0.5

    upper_band = ma20 + 2 * std20
    lower_band = ma20 - 2 * std20

    return upper_band, lower_band

def get_vwap(trader, symbol, order_book_type, depth=5):
    prices = []
    sizes = []

    # Get order book data
    orders = trader.get_order_book(symbol, order_book_type, depth)
    time.sleep(0.5)
    for order in orders:
        prices.append(order.price)
        sizes.append(order.size)

    # Calculate VWAP
    total_value = sum(p * s for p, s in zip(prices, sizes))
    total_volume = sum(sizes)

    return (total_value / total_volume if total_volume != 0 else 0, total_volume)

def get_pnl(trader) -> float:
    # Get portfolio summary
    portfolio = trader.get_portfolio_summary()
    time.sleep(1)
    return portfolio.get_total_realized_pl()

def get_filled_orders_count(trader) -> int:
    import time
    orders = trader.get_submitted_orders()
    time.sleep(1)

    filled_count = sum(1 for order in orders if order.status == shift.Order.Status.FILLED)
    return filled_count

    

def main(argv):
    # import config
    config_parser = configparser.ConfigParser()
    config_parser.read("config.ini")
    config = config_parser["CONFIG"]
    
    # create trader object
    trader: shift.Trader = shift.Trader(config["username"])

    # connect and subscribe to all available order books
    try:
        trader.connect(config["initiator"], config["password"])
        trader.sub_all_order_book()
    except shift.IncorrectPasswordError as e:
        print(e)
    except shift.ConnectionTimeoutError as e:
        print(e)
    # set the duration and list of symbols
    start_time = time.time()
    duration = int(config["duration"])
    symbols = config["symbols"].split(",")

    # pressure threshold for vwap
    pressure_threshold = float(config["pressure_threshold"])

    # scaling factor for obi
    alpha = float(config["alpha"])

    # create sampling thread for prices so we can compute vol and other indicators
    trader.request_sample_prices(symbols, sampling_frequency=float(config["frequency"]), sampling_window=int(config["window"]))
    time.sleep(1)

    def run_quote_spreads(trader, symbol):
        last_print_time = start_time
        last_cancel_time = start_time
        last_wait_time = start_time
        while True:
            curr_time = time.time()
            t = curr_time - start_time

            # End session after duration
            if t > duration:
                break

            # Warm-up period (first 30 mins)
            if t < 30 * 60:
                if curr_time - last_wait_time >= 60:
                    print(f"[INFO] Time: {int(t)} | Waiting 30 mins")
                    last_wait_time = curr_time
                continue

            # Get sample prices for mid-prices MAs
            sample_prices = trader.get_sample_prices(symbol, mid_prices=True)
            time.sleep(0.5)

            ma10 = get_10ma(sample_prices)
            ma30 = get_30ma(sample_prices)


            # Only print every ~60 seconds
            if curr_time - last_print_time >= 60:
                if sample_prices:
                    print(f"[SAMPLE] Time: {int(t // 60)} min | Sample size: {len(sample_prices)} | Last price: {sample_prices[-1]:.2f}")
                    print(f"[MA] Time: {int(t // 60)} min | 10MA: {ma10:.2f} | 30MA: {ma30:.2f}")
                last_print_time = curr_time

            quote_spreads_ma(trader, symbol, ma10, ma30)
            time.sleep(30)
            if curr_time - last_cancel_time >=  60 * 15:
                cancel_orders(trader, symbol)
                liquidate_symbol(trader, symbol)
                last_cancel_time = curr_time

    def run_spread_capture(trader, symbol):
        last_print_time = start_time
        last_wait_time = start_time
        last_cancel_time = start_time
        trend = "NEUTRAL"
        while True:
            curr_time = time.time()
            t = curr_time - start_time

            # End session after duration
            if t > duration:
                break

            # Warm-up period (first 30 mins)
            if t < 30 * 60:
                if curr_time - last_wait_time >= 60:
                    print(f"[{symbol}] [INFO] Time: {int(t)} | Waiting 30 mins")
                    last_wait_time = curr_time
                continue

            # Get sample prices for mid-prices MAs
            sample_prices = trader.get_sample_prices(symbol, mid_prices=True)
            log_returns = trader.get_log_returns(symbol, mid_prices=True)
            time.sleep(0.5)

            vol = get_vol(log_returns)
            upper_band, lower_band = get_boll_band(sample_prices)
            pnl = get_pnl(trader)
            filled_count = get_filled_orders_count(trader)

            # Only print every ~60 seconds
            if curr_time - last_print_time >= 60:
                if sample_prices:
                    print(f"\n[{symbol}] [INFO] Time: {int(t // 60)} min")
                    print(f"[{symbol}] [MID] Last: {sample_prices[-1]:.2f} | Size: {len(sample_prices)}")
                    print(f"[{symbol}] [VOL] Volatility: {vol:.5f}")
                    print(f"[{symbol}] PNL: {pnl:.2f} | Filled Orders: {filled_count}")
                last_print_time = curr_time
                log_market_data_to_csv(trader, symbol, vol, upper_band, lower_band, pnl, filename="market_log6.csv")

            place_vwap_neutral_orders(trader, symbol, vol, pressure_threshold, alpha)
            time.sleep(5)

            if curr_time - last_cancel_time >=  60 * 20:
                cancel_orders(trader, symbol)
                liquidate_symbol(trader, symbol)
                last_cancel_time = curr_time

    threads = []
    for symbol in symbols:
        thread = threading.Thread(target=run_spread_capture, args=(trader, symbol))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    for symbol in symbols:
        cancel_orders(trader, symbol)
        liquidate_symbol(trader, symbol)

    liquidify_portfolio(trader)
    get_portfolio_summary(trader)
    write_order_logs_to_file(trader, "backtest15_order_logs.csv")

    # disconnect
    trader.disconnect()

    return


if __name__ == "__main__":
    main(sys.argv)
