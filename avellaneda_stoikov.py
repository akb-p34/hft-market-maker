import shift
import numpy as np
import pandas as pd
import sys
import time

def k_calc(order_book_levels):
    prices = []
    volumes = []

    best_price = order_book_levels[0].price

    for level in order_book_levels[1:]:
        price = level.price
        size = level.size

        if size <= 0:
            continue

        delta_p = abs(price - best_price)
        prices.append(delta_p)
        volumes.append(size)
    log_volumes = [np.log(v) for v in volumes]
    if prices != []:
        k = -np.polyfit(prices, log_volumes, deg=1)[0]
    else:
        k = 1.5
    return k


def stoikov_strategy(trader, symbol, gamma, duration, t):
    # Get volatility from log returns
    log_rets = trader.get_log_returns(symbol)
    time.sleep(1)
    histvol = np.std(log_rets) / 60  # Convert to per-second volatility

    # Get order book for depth (k)
    bids = trader.get_order_book(symbol, shift.OrderBookType.GLOBAL_BID, max_level=20)
    time.sleep(1)
    asks = trader.get_order_book(symbol, shift.OrderBookType.GLOBAL_ASK, max_level=20)
    time.sleep(1)
    k_bid = k_calc(bids)
    k_ask = k_calc(asks)

    # Compute reservation price
    bp = trader.get_best_price(symbol)
    time.sleep(1)
    best_bid = bp.get_global_bid_price()
    best_ask = bp.get_global_ask_price()
    mid = (best_bid + best_ask) / 2

    portfolio_item = trader.get_portfolio_item(symbol)
    time.sleep(1)
    inventory = (portfolio_item.get_long_shares() - portfolio_item.get_short_shares()) / 100
    reservation_price = mid - inventory * gamma * (histvol ** 2) * (duration - t)

    # Compute optimal spreads
    spread_bid = abs(2 / gamma * np.log(1 + gamma / k_bid))
    spread_ask = abs(2 / gamma * np.log(1 + gamma / k_ask))

    # Place orders
    buy_price = reservation_price - spread_bid
    sell_price = reservation_price + spread_ask

    lb_buy = shift.Order(shift.Order.Type.LIMIT_BUY, symbol, 10, buy_price)
    lb_sell = shift.Order(shift.Order.Type.LIMIT_SELL, symbol, 10, sell_price)
    trader.submit_order(lb_buy)
    trader.submit_order(lb_sell)

    print(f"[{symbol}] Mid: {mid:.2f}, Inventory: {inventory}, Vol: {histvol:.4f}")
    print(
        f"[{symbol}] Reservation: {reservation_price:.2f}, Spread Bid: {spread_bid:.2f}, Spread Ask: {spread_ask:.2f}")
    print(f"[{symbol}] Orders submitted at {buy_price:.2f} (BUY), {sell_price:.2f} (SELL)\n")
    time.sleep(1)


def run_stoikov_strategy(trader, symbol, gamma, duration, start_time):
    while True:
        t = time.time() - start_time
        if t > duration:
            break
        if t < 30 * 60:
            continue
        try:
            stoikov_strategy(trader, symbol, gamma, duration, t)
        except Exception as e:
            print(f"[{symbol}] Error during Stoikov strategy: {e}")
            time.sleep(1)
