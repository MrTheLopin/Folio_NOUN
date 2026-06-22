"""
paper_trading.py
-----------------
Connecte le bot au TESTNET Binance (argent fictif) pour voir la stratégie
passer de vrais ordres, dans des conditions de marché réelles, SANS RISQUE.

⚠️ CECI EST DU TESTNET. Aucune perte financière réelle n'est possible avec
ce script tel qu'il est configuré. Ne mets JAMAIS tes clés API d'un compte
Binance réel ici.

=============================================================================
COMMENT OBTENIR DES CLÉS TESTNET (gratuit, aucune carte bancaire requise) :
=============================================================================
1. Va sur https://testnet.binance.vision/
2. Connecte-toi avec un compte GitHub (pas besoin de compte Binance réel)
3. Génère une clé API testnet → tu obtiens une API Key et une Secret Key
4. Configure-les comme variables d'environnement (jamais en dur dans le code) :

   Sur Linux/Mac :
       export BINANCE_TESTNET_API_KEY="ta_clé"
       export BINANCE_TESTNET_API_SECRET="ton_secret"

   Sur Windows (PowerShell) :
       $env:BINANCE_TESTNET_API_KEY="ta_clé"
       $env:BINANCE_TESTNET_API_SECRET="ton_secret"

5. Le testnet te donne automatiquement un solde fictif (souvent 1 BTC +
   10 000 USDT) pour jouer avec.
=============================================================================
"""

import os
import time
import json
from datetime import datetime

import ccxt
import pandas as pd

from strategy import generate_signals

# =============================================================================
# CONFIGURATION
# =============================================================================
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"            # doit correspondre au rythme de vérification ci-dessous
CHECK_INTERVAL_SECONDS = 60 * 60  # vérifie une fois par bougie (1h ici)

SHORT_WINDOW = 20
LONG_WINDOW = 50
TREND_FILTER_WINDOW = 200
STOP_LOSS_PCT = 3.0
TAKE_PROFIT_PCT = 6.0

# Quota de trades hebdomadaire visé (voir backtest.py pour le détail de cette
# logique). Mets à None pour désactiver et ne suivre que le signal normal.
TARGET_TRADES_PER_WEEK = 12
FAST_SHORT_WINDOW = 5
FAST_LONG_WINDOW = 15

TRADE_FRACTION = 1.0   # fraction du solde USDT disponible utilisée à chaque achat (1.0 = tout)
LOG_FILE = "paper_trades_log.json"


def get_exchange():
    """Crée une connexion à l'exchange Binance en mode TESTNET (sandbox)."""
    api_key = os.environ.get("BINANCE_TESTNET_API_KEY")
    api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        raise RuntimeError(
            "Clés API testnet manquantes. Configure les variables d'environnement "
            "BINANCE_TESTNET_API_KEY et BINANCE_TESTNET_API_SECRET (voir le haut de "
            "ce fichier pour les instructions)."
        )

    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
    })
    exchange.set_sandbox_mode(True)  # ⚠️ active le mode testnet — NE JAMAIS retirer cette ligne
    return exchange


def fetch_recent_data(exchange, limit=300):
    """Récupère les dernières bougies pour calculer les signaux."""
    raw = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def load_state():
    """Charge l'état du bot (position en cours, prix d'entrée, historique des achats)."""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"position": 0, "entry_price": None, "buy_timestamps": [], "trades": []}


def save_state(state):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, default=str)


def decide_action(df, state):
    """
    Reproduit la même logique de décision que backtest.py (signal normal +
    signal de secours si en retard sur le quota), mais pour UNE seule bougie
    (la plus récente), avec l'état réel du bot (position en cours).
    """
    df = generate_signals(df, SHORT_WINDOW, LONG_WINDOW, TREND_FILTER_WINDOW)

    if TARGET_TRADES_PER_WEEK is not None:
        df["fast_ma_short"] = df["close"].rolling(window=FAST_SHORT_WINDOW).mean()
        df["fast_ma_long"] = df["close"].rolling(window=FAST_LONG_WINDOW).mean()
        df["fast_signal"] = (df["fast_ma_short"] > df["fast_ma_long"]).astype(int)
        if TREND_FILTER_WINDOW is not None:
            df.loc[df["close"] < df["ma_trend"], "fast_signal"] = 0

    df = df.dropna().reset_index(drop=True)
    if len(df) == 0:
        return "HOLD", df, False

    last = df.iloc[-1]
    price = last["close"]
    effective_signal = last["signal"]
    force_mode = False

    if TARGET_TRADES_PER_WEEK is not None:
        seven_days_ago = last["timestamp"] - pd.Timedelta(days=7)
        buy_times = pd.to_datetime(state["buy_timestamps"])
        trades_last_7d = sum(1 for t in buy_times if t >= seven_days_ago)
        if trades_last_7d < TARGET_TRADES_PER_WEEK:
            force_mode = True
            effective_signal = 1 if (last["signal"] == 1 or last["fast_signal"] == 1) else 0

    # Stop-loss / take-profit prioritaires si en position
    if state["position"] == 1 and state["entry_price"] is not None:
        change_pct = (price / state["entry_price"] - 1) * 100
        if STOP_LOSS_PCT is not None and change_pct <= -STOP_LOSS_PCT:
            return "SELL_STOP_LOSS", df, force_mode
        if TAKE_PROFIT_PCT is not None and change_pct >= TAKE_PROFIT_PCT:
            return "SELL_TAKE_PROFIT", df, force_mode

    if effective_signal == 1 and state["position"] == 0:
        return "BUY", df, force_mode
    if effective_signal == 0 and state["position"] == 1:
        return "SELL_SIGNAL", df, force_mode

    return "HOLD", df, force_mode


def execute_action(exchange, action, price, state, force_mode):
    """Place l'ordre correspondant sur le testnet et met à jour l'état local."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "BUY":
        balance = exchange.fetch_balance()
        usdt_available = balance["free"].get("USDT", 0)
        amount_usdt = usdt_available * TRADE_FRACTION

        if amount_usdt < 10:  # Binance refuse les ordres trop petits
            print(f"[{timestamp}] Solde USDT insuffisant pour acheter ({usdt_available:.2f} USDT).")
            return

        amount_btc = amount_usdt / price
        order = exchange.create_market_buy_order(SYMBOL, amount_btc)

        state["position"] = 1
        state["entry_price"] = price
        state["buy_timestamps"].append(timestamp)
        state["trades"].append({
            "horodatage": timestamp, "type": "BUY", "prix": price,
            "montant_usdt": amount_usdt, "force": force_mode, "order_id": order.get("id"),
        })
        print(f"[{timestamp}] 🟢 ACHAT {amount_btc:.6f} BTC à {price:.2f} USDT"
              f"{' (forcé par quota)' if force_mode else ''}")

    elif action.startswith("SELL"):
        balance = exchange.fetch_balance()
        btc_available = balance["free"].get("BTC", 0)

        if btc_available <= 0.0001:
            print(f"[{timestamp}] Aucun BTC à vendre.")
            state["position"] = 0
            return

        order = exchange.create_market_sell_order(SYMBOL, btc_available)
        reason = action.replace("SELL_", "")

        state["position"] = 0
        state["entry_price"] = None
        state["trades"].append({
            "horodatage": timestamp, "type": "SELL", "prix": price,
            "montant_btc": btc_available, "raison": reason, "order_id": order.get("id"),
        })
        print(f"[{timestamp}] 🔴 VENTE {btc_available:.6f} BTC à {price:.2f} USDT — raison : {reason}")

    save_state(state)


def run_once():
    """Une itération : vérifie le marché et agit si besoin. Utile pour tester rapidement."""
    exchange = get_exchange()
    state = load_state()

    df = fetch_recent_data(exchange)
    action, df, force_mode = decide_action(df, state)
    price = df.iloc[-1]["close"]

    print(f"\n--- Vérification à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    print(f"Prix actuel : {price:.2f} USDT | Position actuelle : {'BTC' if state['position'] else 'cash'}")
    print(f"Décision : {action}")

    if action != "HOLD":
        execute_action(exchange, action, price, state, force_mode)
    else:
        save_state(state)


def run_forever():
    """Boucle infinie : vérifie le marché à intervalle régulier. À lancer dans un terminal dédié."""
    print(f"Démarrage du paper trading sur testnet — {SYMBOL}, vérification toutes les "
          f"{CHECK_INTERVAL_SECONDS // 60} minutes. Ctrl+C pour arrêter.\n")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Erreur lors de la vérification : {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        run_once()
    else:
        run_forever()
