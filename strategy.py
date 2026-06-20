"""
strategy.py
-----------
Stratégie de "croisement de moyennes mobiles" (Moving Average Crossover).

Principe (simple à comprendre, c'est pour ça qu'on commence par elle) :
- On calcule une moyenne mobile courte (ex: 20 périodes) et une moyenne
  mobile longue (ex: 50 périodes).
- Quand la moyenne courte CROISE AU-DESSUS de la moyenne longue → signal
  d'ACHAT (le marché accélère vers le haut).
- Quand la moyenne courte CROISE AU-DESSOUS de la moyenne longue → signal
  de VENTE (le marché accélère vers le bas).

C'est une stratégie "tendancielle" (trend-following) : elle essaie de
suivre les tendances, pas de prédire les retournements.
"""

import pandas as pd


def add_moving_averages(df, short_window=20, long_window=50):
    """Ajoute deux colonnes de moyennes mobiles au DataFrame."""
    df = df.copy()
    df["ma_short"] = df["close"].rolling(window=short_window).mean()
    df["ma_long"] = df["close"].rolling(window=long_window).mean()
    return df


def generate_signals(df, short_window=20, long_window=50):
    """
    Ajoute une colonne 'signal' :
        1  → on doit être en position ACHETEUR (long)
        0  → on ne doit pas être en position (cash)

    Et une colonne 'position_change' qui vaut :
        1  → on vient d'acheter
       -1  → on vient de vendre
        0  → rien ne change
    """
    df = add_moving_averages(df, short_window, long_window)

    # Signal = 1 quand la moyenne courte est au-dessus de la moyenne longue
    df["signal"] = 0
    df.loc[df["ma_short"] > df["ma_long"], "signal"] = 1

    # On détecte les moments où le signal change (croisement réel)
    df["position_change"] = df["signal"].diff()

    return df


if __name__ == "__main__":
    # Petit test avec des données factices pour vérifier que ça fonctionne
    import numpy as np

    dates = pd.date_range("2024-01-01", periods=200, freq="h")
    prices = 100 + np.cumsum(np.random.randn(200))  # marche aléatoire simple

    df = pd.DataFrame({"timestamp": dates, "close": prices})
    df = generate_signals(df, short_window=10, long_window=30)

    print(df[["timestamp", "close", "ma_short", "ma_long", "signal", "position_change"]].tail(20))
