"""
backtest.py
-----------
Simule l'exécution de la stratégie sur des données historiques, pour voir
comment elle se serait comportée DANS LE PASSÉ.

⚠️ Rappel important : une bonne performance en backtest ne garantit
PAS une bonne performance future. C'est un outil pour comprendre et
itérer sur une stratégie, pas une prédiction.
"""

import pandas as pd
import matplotlib.pyplot as plt

from strategy import generate_signals


def run_backtest(df, initial_capital=1000, short_window=20, long_window=50, fee_pct=0.001):
    """
    Simule un portefeuille qui suit les signaux d'achat/vente.

    initial_capital : capital de départ (fictif)
    fee_pct         : frais de transaction par trade (0.001 = 0.1%, typique sur Binance)
    """
    df = generate_signals(df, short_window, long_window)
    df = df.dropna().reset_index(drop=True)  # enlève les lignes sans moyenne mobile calculée

    capital = initial_capital
    position = 0  # 0 = pas de BTC détenu, 1 = on détient du BTC
    btc_held = 0
    portfolio_values = []
    trades = []

    for i, row in df.iterrows():
        price = row["close"]

        # Signal d'achat : on n'a pas de position et le signal dit d'acheter
        if row["signal"] == 1 and position == 0:
            capital_investi = capital  # montant englouti dans ce trade (avant frais)
            btc_held = (capital * (1 - fee_pct)) / price
            capital = 0
            position = 1
            trades.append({
                "date": row["timestamp"],
                "type": "BUY",
                "price": price,
                "capital_investi": capital_investi,
            })

        # Signal de vente : on a une position et le signal dit de sortir
        elif row["signal"] == 0 and position == 1:
            capital_recupere = btc_held * price * (1 - fee_pct)  # montant récupéré (après frais)
            capital = capital_recupere
            btc_held = 0
            position = 0
            trades.append({
                "date": row["timestamp"],
                "type": "SELL",
                "price": price,
                "capital_recupere": capital_recupere,
            })

        # Valeur totale du portefeuille à cet instant (cash + BTC détenu)
        total_value = capital + (btc_held * price)
        portfolio_values.append(total_value)

    df["portfolio_value"] = portfolio_values

    return df, pd.DataFrame(trades)


def build_trade_log(trades_df, initial_capital):
    """
    Associe chaque ACHAT à la VENTE qui suit pour former des "trades complets"
    (round trips), et calcule le profit/perte de chacun.

    Retourne un DataFrame avec une ligne par trade complet :
        date_achat, prix_achat, date_vente, prix_vente,
        capital_investi, capital_recupere, profit_usdt, profit_pct, gagnant
    """
    rows = []
    buy_row = None

    for _, row in trades_df.iterrows():
        if row["type"] == "BUY":
            buy_row = row
        elif row["type"] == "SELL" and buy_row is not None:
            capital_investi = buy_row["capital_investi"]
            capital_recupere = row["capital_recupere"]
            profit_usdt = capital_recupere - capital_investi
            profit_pct = (capital_recupere / capital_investi - 1) * 100

            rows.append({
                "date_achat": buy_row["date"],
                "prix_achat": buy_row["price"],
                "date_vente": row["date"],
                "prix_vente": row["price"],
                "capital_investi": capital_investi,
                "capital_recupere": capital_recupere,
                "profit_usdt": profit_usdt,
                "profit_pct": profit_pct,
                "gagnant": profit_usdt > 0,
            })
            buy_row = None

    log_df = pd.DataFrame(rows)
    if len(log_df) > 0:
        log_df.insert(0, "trade_num", range(1, len(log_df) + 1))

    return log_df


# Codes couleur ANSI pour l'affichage dans le terminal
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_trade_log(log_df, initial_capital, final_capital):
    """Affiche le tableau des trades dans le terminal, en vert (gain) / rouge (perte)."""
    print("\n" + "=" * 100)
    print("DÉTAIL DE CHAQUE TRADE")
    print("=" * 100)
    print(f"Capital de départ : {initial_capital:.2f} USDT\n")

    if len(log_df) == 0:
        print("Aucun trade complet (achat + vente) sur cette période.")
        return

    header = f"{'#':>3} | {'Achat':^19} | {'Vente':^19} | {'Prix achat':>10} | {'Prix vente':>10} | {'Investi':>10} | {'Récupéré':>10} | {'Profit':>12}"
    print(header)
    print("-" * len(header))

    for _, t in log_df.iterrows():
        color = GREEN if t["gagnant"] else RED
        profit_str = f"{t['profit_usdt']:+.2f} USDT ({t['profit_pct']:+.2f}%)"

        line = (
            f"{int(t['trade_num']):>3} | "
            f"{t['date_achat'].strftime('%Y-%m-%d %H:%M'):^19} | "
            f"{t['date_vente'].strftime('%Y-%m-%d %H:%M'):^19} | "
            f"{t['prix_achat']:>10.2f} | "
            f"{t['prix_vente']:>10.2f} | "
            f"{t['capital_investi']:>10.2f} | "
            f"{t['capital_recupere']:>10.2f} | "
            f"{profit_str:>12}"
        )
        print(f"{color}{line}{RESET}")

    print("-" * len(header))
    nb_gagnants = log_df["gagnant"].sum()
    nb_perdants = len(log_df) - nb_gagnants
    print(f"\nTrades gagnants : {GREEN}{nb_gagnants}{RESET}   |   Trades perdants : {RED}{nb_perdants}{RESET}")
    print(f"Profit total des trades : {log_df['profit_usdt'].sum():+.2f} USDT")
    print(f"\n{BOLD}Capital de départ : {initial_capital:.2f} USDT   →   Capital final : {final_capital:.2f} USDT{RESET}")


def export_trade_log_image(log_df, initial_capital, final_capital, filename="trade_log.png"):
    """Génère une image du tableau des trades, avec les lignes colorées en vert/rouge."""
    if len(log_df) == 0:
        print("Aucun trade à exporter en image.")
        return

    display_df = log_df.copy()
    display_df["date_achat"] = display_df["date_achat"].dt.strftime("%Y-%m-%d %H:%M")
    display_df["date_vente"] = display_df["date_vente"].dt.strftime("%Y-%m-%d %H:%M")
    display_df["prix_achat"] = display_df["prix_achat"].map(lambda x: f"{x:.2f}")
    display_df["prix_vente"] = display_df["prix_vente"].map(lambda x: f"{x:.2f}")
    display_df["capital_investi"] = display_df["capital_investi"].map(lambda x: f"{x:.2f}")
    display_df["capital_recupere"] = display_df["capital_recupere"].map(lambda x: f"{x:.2f}")
    display_df["profit_usdt"] = display_df.apply(
        lambda r: f"{r['profit_usdt']:+.2f} ({r['profit_pct']:+.2f}%)", axis=1
    )

    columns_to_show = [
        "trade_num", "date_achat", "date_vente", "prix_achat", "prix_vente",
        "capital_investi", "capital_recupere", "profit_usdt"
    ]
    column_labels = [
        "#", "Date achat", "Date vente", "Prix achat", "Prix vente",
        "Investi (USDT)", "Récupéré (USDT)", "Profit"
    ]

    # Ligne finale récapitulative (capital de départ -> capital final)
    final_row = ["", "", "CAPITAL FINAL", "", "", f"{initial_capital:.2f}", f"{final_capital:.2f}",
                 f"{final_capital - initial_capital:+.2f} ({(final_capital/initial_capital - 1) * 100:+.2f}%)"]

    nb_rows = len(display_df) + 1  # +1 pour la ligne finale
    fig_height = 0.9 + 0.35 * nb_rows
    fig, ax = plt.subplots(figsize=(13, fig_height))
    ax.axis("off")

    ax.set_title(
        f"Détail des trades — Capital de départ : {initial_capital:.2f} USDT",
        fontsize=13, fontweight="bold", pad=20
    )

    all_rows = list(display_df[columns_to_show].values) + [final_row]

    table = ax.table(
        cellText=all_rows,
        colLabels=column_labels,
        cellLoc="center",
        loc="center"
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)

    # Colore chaque ligne en vert (gain) ou rouge (perte) pâle, lisible
    for row_idx, gagnant in enumerate(log_df["gagnant"]):
        color = "#c6f0c2" if gagnant else "#f5c2c2"
        for col_idx in range(len(columns_to_show)):
            table[row_idx + 1, col_idx].set_facecolor(color)

    # Ligne finale en gras avec fond distinct
    final_row_idx = len(display_df) + 1
    for col_idx in range(len(columns_to_show)):
        table[final_row_idx, col_idx].set_facecolor("#b0b0b0")
        table[final_row_idx, col_idx].set_text_props(fontweight="bold")

    # En-tête en gras avec fond gris
    for col_idx in range(len(columns_to_show)):
        table[0, col_idx].set_facecolor("#d9d9d9")
        table[0, col_idx].set_text_props(fontweight="bold")

    plt.tight_layout()
    plt.savefig(filename, dpi=130, bbox_inches="tight")
    print(f"Tableau des trades sauvegardé dans {filename}")


def export_trade_log_html(log_df, initial_capital, final_capital, filename="trade_log.html"):
    """
    Génère une page HTML autonome avec le tableau des trades, colorée en
    vert/rouge. Pensée pour être déposée sur GitHub Pages ou tout hébergement
    web statique — texte sélectionnable, responsive, facile à enrichir en CSS.
    """
    total_profit = final_capital - initial_capital
    total_profit_pct = (final_capital / initial_capital - 1) * 100
    nb_gagnants = int(log_df["gagnant"].sum()) if len(log_df) > 0 else 0
    nb_perdants = len(log_df) - nb_gagnants

    rows_html = ""
    for _, t in log_df.iterrows():
        row_class = "gagnant" if t["gagnant"] else "perdant"
        rows_html += f"""
        <tr class="{row_class}">
            <td>{int(t['trade_num'])}</td>
            <td>{t['date_achat'].strftime('%Y-%m-%d %H:%M')}</td>
            <td>{t['date_vente'].strftime('%Y-%m-%d %H:%M')}</td>
            <td>{t['prix_achat']:.2f}</td>
            <td>{t['prix_vente']:.2f}</td>
            <td>{t['capital_investi']:.2f}</td>
            <td>{t['capital_recupere']:.2f}</td>
            <td>{t['profit_usdt']:+.2f} USDT ({t['profit_pct']:+.2f}%)</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Détail des trades</title>
<style>
    body {{ font-family: Arial, Helvetica, sans-serif; background: #f7f7f7; padding: 30px; }}
    h1 {{ font-size: 1.3em; }}
    table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
    th, td {{ padding: 8px 12px; text-align: center; border-bottom: 1px solid #e0e0e0; font-size: 0.9em; }}
    th {{ background: #333; color: white; }}
    tr.gagnant {{ background-color: #d8f5d4; }}
    tr.perdant {{ background-color: #fbd6d6; }}
    tr.final {{ background-color: #cfcfcf; font-weight: bold; }}
    .summary {{ margin-bottom: 15px; }}
    .summary span.gagnant {{ color: #1a8c1a; font-weight: bold; }}
    .summary span.perdant {{ color: #c0392b; font-weight: bold; }}
</style>
</head>
<body>
    <h1>Détail des trades — Stratégie de croisement de moyennes mobiles</h1>
    <div class="summary">
        <p>Capital de départ : <b>{initial_capital:.2f} USDT</b></p>
        <p>Trades gagnants : <span class="gagnant">{nb_gagnants}</span> |
           Trades perdants : <span class="perdant">{nb_perdants}</span></p>
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th><th>Date achat</th><th>Date vente</th>
                <th>Prix achat</th><th>Prix vente</th>
                <th>Investi (USDT)</th><th>Récupéré (USDT)</th><th>Profit</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
            <tr class="final">
                <td colspan="5">CAPITAL FINAL</td>
                <td>{initial_capital:.2f}</td>
                <td>{final_capital:.2f}</td>
                <td>{total_profit:+.2f} USDT ({total_profit_pct:+.2f}%)</td>
            </tr>
        </tbody>
    </table>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Page HTML sauvegardée dans {filename}")


def print_performance_summary(df, trades_df, initial_capital):
    final_value = df["portfolio_value"].iloc[-1]
    total_return_pct = (final_value / initial_capital - 1) * 100

    # Performance si on avait juste acheté et gardé (buy & hold), pour comparaison
    buy_hold_return_pct = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100

    print("=" * 50)
    print("RÉSUMÉ DE PERFORMANCE")
    print("=" * 50)
    print(f"Capital de départ      : {initial_capital:.2f} USDT")
    print(f"Capital final           : {final_value:.2f} USDT")
    print(f"Rendement stratégie     : {total_return_pct:+.2f}%")
    print(f"Rendement buy & hold     : {buy_hold_return_pct:+.2f}%")
    print(f"Nombre de trades         : {len(trades_df)}")
    print("=" * 50)


def plot_results(df, trades_df, initial_capital):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Graphique du prix + moyennes mobiles + points d'achat/vente
    ax1.plot(df["timestamp"], df["close"], label="Prix BTC/USDT", alpha=0.6)
    ax1.plot(df["timestamp"], df["ma_short"], label="Moyenne courte", alpha=0.8)
    ax1.plot(df["timestamp"], df["ma_long"], label="Moyenne longue", alpha=0.8)

    buys = trades_df[trades_df["type"] == "BUY"]
    sells = trades_df[trades_df["type"] == "SELL"]
    ax1.scatter(buys["date"], buys["price"], marker="^", color="green", s=100, label="Achat", zorder=5)
    ax1.scatter(sells["date"], sells["price"], marker="v", color="red", s=100, label="Vente", zorder=5)

    ax1.set_ylabel("Prix (USDT)")
    ax1.legend()
    ax1.set_title("Stratégie de croisement de moyennes mobiles - BTC/USDT")

    # Graphique de la valeur du portefeuille
    ax2.plot(df["timestamp"], df["portfolio_value"], label="Valeur du portefeuille", color="purple")
    ax2.axhline(y=initial_capital, color="gray", linestyle="--", label="Capital de départ")
    ax2.set_ylabel("Valeur (USDT)")
    ax2.set_xlabel("Date")
    ax2.legend()

    plt.tight_layout()
    plt.savefig("backtest_results.png", dpi=120)
    print("\nGraphique sauvegardé dans backtest_results.png")


if __name__ == "__main__":
    INITIAL_CAPITAL = 1000

    # Charge les données récupérées par fetch_data.py
    df = pd.read_csv("btc_usdt_1h.csv", parse_dates=["timestamp"])

    df, trades_df = run_backtest(
        df,
        initial_capital=INITIAL_CAPITAL,
        short_window=20,
        long_window=50,
        fee_pct=0.001
    )

    print_performance_summary(df, trades_df, INITIAL_CAPITAL)
    plot_results(df, trades_df, INITIAL_CAPITAL)

    final_capital = df["portfolio_value"].iloc[-1]
    trade_log_df = build_trade_log(trades_df, INITIAL_CAPITAL)
    print_trade_log(trade_log_df, INITIAL_CAPITAL, final_capital)
    export_trade_log_image(trade_log_df, INITIAL_CAPITAL, final_capital)
    export_trade_log_html(trade_log_df, INITIAL_CAPITAL, final_capital)
