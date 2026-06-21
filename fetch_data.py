"""
fetch_data.py
--------------
Récupère des données historiques (prix) depuis Binance et les sauvegarde
dans un fichier CSV, pour pouvoir ensuite les utiliser dans un backtest.

Aucune clé API n'est nécessaire pour récupérer des données publiques (OHLCV).
"""

import ccxt
import pandas as pd
from datetime import datetime


def fetch_ohlcv(symbol="BTC/USDT", timeframe="15m", limit=1000):
    """
    Récupère les données OHLCV (Open, High, Low, Close, Volume).

    symbol    : la paire de trading, ex "BTC/USDT"
    timeframe : la granularité des bougies, ex "1m", "5m", "15m", "1h", "4h", "1d"
    limit     : nombre de bougies à récupérer (max ~1000 par requête sur Binance)
    """
    exchange = ccxt.binance()

    print(f"Récupération de {limit} bougies {timeframe} pour {symbol}...")
    raw_data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(
        raw_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    # Convertit le timestamp (millisecondes) en date lisible
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    return df


def fetch_extended_history(symbol="BTC/USDT", timeframe="15m", total_candles=5000, max_retries=3):
    """
    Binance limite à ~1000 bougies par requête. Cette fonction fait plusieurs
    requêtes successives pour récupérer un historique plus long.

    max_retries : nombre de tentatives en cas d'erreur réseau temporaire
    avant d'abandonner (les APIs publiques peuvent parfois rejeter une
    requête ponctuellement, ce n'est pas forcément grave).
    """
    import time

    exchange = ccxt.binance()
    all_data = []
    since = None

    while len(all_data) < total_candles:
        for attempt in range(max_retries):
            try:
                batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
                break
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # attente progressive : 1s, 2s, 4s...
                    print(f"  Erreur réseau ({e}), nouvelle tentative dans {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"  Échec après {max_retries} tentatives, arrêt avec {len(all_data)} bougies récupérées.")
                    batch = []

        if not batch:
            break
        all_data += batch
        since = batch[-1][0] + 1  # on repart juste après la dernière bougie reçue
        print(f"  {len(all_data)} bougies récupérées...")
        if len(batch) < 1000:
            break  # plus de données disponibles

    if not all_data:
        raise RuntimeError(
            "Aucune donnée récupérée. Vérifie ta connexion internet et que "
            "l'exchange (Binance) est accessible depuis ton réseau."
        )

    df = pd.DataFrame(
        all_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)

    return df.tail(total_candles).reset_index(drop=True)


if __name__ == "__main__":
    # =========================================================================
    # Choisis la configuration adaptée à ton analyse (voir multi_period_analysis.py) :
    #
    #   Analyse mensuelle : timeframe="1h",  total_candles=3000  (~4 mois)
    #   Analyse hebdo     : timeframe="15m", total_candles=8000  (~3 mois)
    #   Analyse journalière : timeframe="5m", total_candles=10000 (~1 mois)
    #
    # Plus la granularité est fine, plus il faut de bougies pour couvrir la
    # même durée réelle, et plus la récupération prendra de temps (plusieurs
    # requêtes à l'API Binance).
    # =========================================================================

    TIMEFRAME = "15m"
    TOTAL_CANDLES = 8000

    df = fetch_extended_history(symbol="BTC/USDT", timeframe=TIMEFRAME, total_candles=TOTAL_CANDLES)

    output_path = f"btc_usdt_{TIMEFRAME}.csv"
    df.to_csv(output_path, index=False)
    print(f"\nDonnées sauvegardées dans {output_path}")
    print(df.head())
    print("...")
    print(df.tail())
