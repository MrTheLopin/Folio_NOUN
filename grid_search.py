"""
grid_search.py
---------------
Teste automatiquement plein de combinaisons de (short_window, long_window)
sur les mêmes données historiques, et classe les résultats.

⚠️ MISE EN GARDE IMPORTANTE SUR L'OVERFITTING :
Si tu choisis la combinaison qui a le MEILLEUR résultat ici et que tu l'utilises
en trading réel, tu n'as pas trouvé "la meilleure stratégie" — tu as juste
trouvé la combinaison qui collait le mieux au hasard de CETTE période précise.
Rien ne garantit qu'elle sera bonne sur des données futures.

L'utilité réelle de ce script :
- Voir si CERTAINES ZONES de paramètres sont structurellement meilleures
  (ex: toutes les combinaisons "court terme" sont mauvaises → évite-les)
- Repérer si la performance est stable autour d'un optimum (bon signe) ou
  si elle varie énormément avec de petits changements (signe d'overfitting,
  mauvais signe)
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from backtest import run_backtest


def grid_search(df, initial_capital=1000, short_range=range(5, 31, 5), long_range=range(20, 101, 10), fee_pct=0.001):
    """
    Teste toutes les combinaisons (short, long) où short < long.

    short_range / long_range : les valeurs à tester pour chaque moyenne mobile
    """
    results = []

    for short_window in short_range:
        for long_window in long_range:
            if short_window >= long_window:
                continue  # une moyenne courte doit être... courte

            bt_df, trades_df = run_backtest(
                df.copy(),
                initial_capital=initial_capital,
                short_window=short_window,
                long_window=long_window,
                fee_pct=fee_pct
            )

            if len(bt_df) == 0:
                continue

            final_value = bt_df["portfolio_value"].iloc[-1]
            return_pct = (final_value / initial_capital - 1) * 100

            results.append({
                "short_window": short_window,
                "long_window": long_window,
                "rendement_pct": round(return_pct, 2),
                "nb_trades": len(trades_df),
                "capital_final": round(final_value, 2),
            })

    results_df = pd.DataFrame(results).sort_values("rendement_pct", ascending=False).reset_index(drop=True)
    return results_df


def print_results(results_df, top_n=15):
    buy_hold_note = "(rappel : compare toujours au rendement buy & hold de la même période)"
    print("=" * 70)
    print(f"TOP {top_n} DES MEILLEURES COMBINAISONS (sur cette période historique)")
    print("=" * 70)
    print(results_df.head(top_n).to_string(index=False))
    print(f"\n{buy_hold_note}")

    print("\n" + "=" * 70)
    print("LES 5 PIRES COMBINAISONS (à éviter structurellement)")
    print("=" * 70)
    print(results_df.tail(5).to_string(index=False))

    print("\n" + "=" * 70)
    print("STATISTIQUES GLOBALES SUR TOUTES LES COMBINAISONS TESTÉES")
    print("=" * 70)
    print(f"Nombre de combinaisons testées : {len(results_df)}")
    print(f"Rendement moyen                : {results_df['rendement_pct'].mean():.2f}%")
    print(f"Rendement médian                : {results_df['rendement_pct'].median():.2f}%")
    print(f"Écart-type des rendements       : {results_df['rendement_pct'].std():.2f}")
    print(f"% de combinaisons profitables   : {(results_df['rendement_pct'] > 0).mean() * 100:.1f}%")

    std = results_df['rendement_pct'].std()
    if std > abs(results_df['rendement_pct'].median()) * 2:
        print("\n⚠️  Forte variance entre les combinaisons : signe que la performance est très")
        print("    sensible aux paramètres choisis. Prudence avant de figer une combinaison.")


def plot_heatmap(results_df, filename="grid_search_heatmap.png"):
    """Affiche une heatmap rendement en fonction de (short_window, long_window)."""
    pivot = results_df.pivot(index="short_window", columns="long_window", values="rendement_pct")

    fig, ax = plt.subplots(figsize=(10, 7))
    max_abs = np.nanmax(np.abs(pivot.values))
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-max_abs, vmax=max_abs)

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Moyenne longue (périodes)")
    ax.set_ylabel("Moyenne courte (périodes)")
    ax.set_title("Rendement (%) selon la combinaison de moyennes mobiles")

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            value = pivot.values[i, j]
            if not np.isnan(value):
                ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=8)

    fig.colorbar(im, ax=ax, label="Rendement (%)")
    plt.tight_layout()
    plt.savefig(filename, dpi=120)
    print(f"\nHeatmap sauvegardée dans {filename}")


if __name__ == "__main__":
    INITIAL_CAPITAL = 1000

    df = pd.read_csv("btc_usdt_1h.csv", parse_dates=["timestamp"])

    results_df = grid_search(
        df,
        initial_capital=INITIAL_CAPITAL,
        short_range=range(5, 31, 5),
        long_range=range(20, 101, 10),
        fee_pct=0.001
    )

    print_results(results_df)
    plot_heatmap(results_df)

    results_df.to_csv("grid_search_results.csv", index=False)
    print("\nRésultats complets sauvegardés dans grid_search_results.csv")
