"""
multi_period_analysis.py
-------------------------
Découpe l'historique de prix en plusieurs tranches (ex: 30 jours chacune)
et lance le backtest sur chaque tranche séparément.

Objectif : voir si la stratégie se comporte bien UNIQUEMENT sur certaines
conditions de marché (ex: tendance baissière nette) ou si elle reste
cohérente sur des contextes variés (range, haussier, baissier...).

⚠️ Une stratégie qui ne marche bien que sur un seul type de marché n'est
pas "robuste" — elle a probablement eu de la chance sur cette période.
"""

import pandas as pd
import matplotlib.pyplot as plt

from backtest import run_backtest


def classify_market_regime(df):
    """
    Classification simple du régime de marché sur une tranche :
    compare le prix de début et de fin pour dire si c'était plutôt
    haussier, baissier, ou stable (range).
    """
    start_price = df["close"].iloc[0]
    end_price = df["close"].iloc[-1]
    change_pct = (end_price / start_price - 1) * 100

    if change_pct > 5:
        regime = "Haussier"
    elif change_pct < -5:
        regime = "Baissier"
    else:
        regime = "Range / stable"

    return regime, change_pct


def split_into_periods(df, period_days=30, min_candles=60):
    """Découpe le DataFrame en tranches de N jours."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    start_date = df["timestamp"].iloc[0]
    end_date = df["timestamp"].iloc[-1]

    periods = []
    current_start = start_date
    while current_start < end_date:
        current_end = current_start + pd.Timedelta(days=period_days)
        chunk = df[(df["timestamp"] >= current_start) & (df["timestamp"] < current_end)]
        if len(chunk) > min_candles:  # assez de données pour calculer les moyennes mobiles
            periods.append(chunk.reset_index(drop=True))
        current_start = current_end

    return periods


def analyze_all_periods(df, period_days=30, initial_capital=1000, short_window=20, long_window=50):
    """Lance le backtest sur chaque tranche et compile les résultats dans un tableau."""
    periods = split_into_periods(df, period_days, min_candles=long_window + 10)

    results = []
    for i, chunk in enumerate(periods):
        regime, market_change_pct = classify_market_regime(chunk)

        bt_df, trades_df = run_backtest(
            chunk,
            initial_capital=initial_capital,
            short_window=short_window,
            long_window=long_window
        )

        if len(bt_df) == 0:
            continue

        final_value = bt_df["portfolio_value"].iloc[-1]
        strategy_return_pct = (final_value / initial_capital - 1) * 100

        results.append({
            "periode": i + 1,
            "date_debut": chunk["timestamp"].iloc[0].date(),
            "date_fin": chunk["timestamp"].iloc[-1].date(),
            "regime_marche": regime,
            "rendement_marche_pct": round(market_change_pct, 2),
            "rendement_strategie_pct": round(strategy_return_pct, 2),
            "nb_trades": len(trades_df),
        })

    return pd.DataFrame(results)


def print_summary(results_df):
    print("=" * 95)
    print("ANALYSE MULTI-PÉRIODES")
    print("=" * 95)
    print(results_df.to_string(index=False))
    print("=" * 95)

    nb_periodes_gagnantes = (results_df["rendement_strategie_pct"] > 0).sum()
    nb_periodes_meilleures_que_marche = (
        results_df["rendement_strategie_pct"] > results_df["rendement_marche_pct"]
    ).sum()

    print(f"\nPériodes profitables             : {nb_periodes_gagnantes}/{len(results_df)}")
    print(f"Périodes où la stratégie bat le marché : {nb_periodes_meilleures_que_marche}/{len(results_df)}")
    print(f"Rendement moyen de la stratégie   : {results_df['rendement_strategie_pct'].mean():.2f}%")
    print(f"Rendement moyen du marché (buy&hold) : {results_df['rendement_marche_pct'].mean():.2f}%")

    print("\nPerformance par régime de marché :")
    print(results_df.groupby("regime_marche")["rendement_strategie_pct"].agg(["mean", "count"]))


def plot_comparison(results_df):
    fig, ax = plt.subplots(figsize=(12, 6))

    x = range(len(results_df))
    width = 0.35

    ax.bar([i - width/2 for i in x], results_df["rendement_marche_pct"], width, label="Marché (buy & hold)", color="gray", alpha=0.7)
    ax.bar([i + width/2 for i in x], results_df["rendement_strategie_pct"], width, label="Stratégie", color="purple", alpha=0.8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"P{i+1}\n{row['regime_marche']}" for i, row in results_df.iterrows()], fontsize=8)
    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.set_ylabel("Rendement (%)")
    ax.set_title("Stratégie vs Buy & Hold, par période et régime de marché")
    ax.legend()

    plt.tight_layout()
    plt.savefig("multi_period_results.png", dpi=120)
    print("\nGraphique sauvegardé dans multi_period_results.png")


if __name__ == "__main__":
    # =========================================================================
    # PARAMÈTRES À AJUSTER
    # =========================================================================
    # Découpage des périodes : 30 = mensuel, 7 = hebdomadaire, 1 = journalier
    PERIOD_DAYS = 30

    # ⚠️ IMPORTANT : la granularité des données (timeframe dans fetch_data.py)
    # doit être adaptée à PERIOD_DAYS, sinon tu n'as pas assez de bougies
    # par période pour calculer des moyennes mobiles fiables :
    #
    #   PERIOD_DAYS = 30 (mensuel)   → timeframe "1h"  fonctionne bien
    #   PERIOD_DAYS = 7  (hebdo)     → timeframe "15m" ou "1h" recommandé
    #   PERIOD_DAYS = 1  (journalier)→ timeframe "1m" ou "5m" nécessaire
    #
    # Avec PERIOD_DAYS=1 et des bougies 1h, tu n'as que 24 bougies dans la
    # journée : pas assez pour une moyenne longue de 50 périodes !
    # Pense à adapter aussi short_window / long_window à la granularité :
    #
    #   Sur 1h  : short=20, long=50  (comme actuellement)
    #   Sur 15m : short=20, long=50  (couvre ~5h / ~12h30)
    #   Sur 5m  : short=12, long=30  (couvre 1h / 2h30, plus réactif)
    #   Sur 1m  : short=10, long=20  (très réactif, proche du scalping)
    SHORT_WINDOW = 20
    LONG_WINDOW = 50

    DATA_FILE = "btc_usdt_1h.csv"  # adapte selon le fichier généré par fetch_data.py  # change selon le fichier généré par fetch_data.py

    # =========================================================================

    df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])

    results_df = analyze_all_periods(
        df,
        period_days=PERIOD_DAYS,
        initial_capital=1000,
        short_window=SHORT_WINDOW,
        long_window=LONG_WINDOW
    )

    print_summary(results_df)
    plot_comparison(results_df)
