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


def run_backtest(df, initial_capital=1000, short_window=20, long_window=50, fee_pct=0.001,
                  stop_loss_pct=None, take_profit_pct=None, trend_filter_window=None,
                  target_trades_per_week=None, fast_short_window=5, fast_long_window=15):
    """
    Simule un portefeuille qui suit les signaux d'achat/vente.

    initial_capital      : capital de départ (fictif)
    fee_pct               : frais de transaction par trade (0.001 = 0.1%, typique sur Binance)
    stop_loss_pct         : si défini (ex: 2.0), vend automatiquement si le prix chute de X%
                             depuis le prix d'achat — même si le signal de moyenne mobile
                             dit encore de rester acheteur. Limite les grosses pertes.
    take_profit_pct       : si défini (ex: 4.0), vend automatiquement si le prix monte de
                             X% depuis le prix d'achat — sécurise le gain avant un possible
                             retournement, même si le signal dit encore de rester acheteur.
    trend_filter_window   : si défini (ex: 200), n'autorise l'achat que si le prix est
                             au-dessus de cette moyenne mobile longue (filtre de tendance).
                             Voir strategy.py pour le détail.
    target_trades_per_week : si défini (ex: 12), la stratégie surveille son rythme de trading
                             sur les 7 derniers jours. Si elle est en retard sur ce quota, elle
                             active un second jeu de moyennes mobiles, plus rapide
                             (fast_short_window/fast_long_window), pour générer plus
                             d'opportunités d'entrée.
                             ⚠️ Forcer un nombre de trades indépendamment du signal de marché
                             augmente les frais payés et peut faire entrer le bot sur des
                             trades sans avantage statistique réel. Cette option sert à
                             OBSERVER cet effet (notamment sur testnet), pas à l'optimiser.
    """
    df = generate_signals(df, short_window, long_window, trend_filter_window)

    # Signal "de secours" plus réactif, utilisé uniquement quand on est en
    # retard sur le quota de trades hebdomadaire visé.
    if target_trades_per_week is not None:
        df["fast_ma_short"] = df["close"].rolling(window=fast_short_window).mean()
        df["fast_ma_long"] = df["close"].rolling(window=fast_long_window).mean()
        df["fast_signal"] = (df["fast_ma_short"] > df["fast_ma_long"]).astype(int)
        # Le filtre de tendance, si actif, s'applique aussi au signal de secours
        # (on ne veut pas qu'il contourne complètement le garde-fou de tendance)
        if trend_filter_window is not None:
            df.loc[df["close"] < df["ma_trend"], "fast_signal"] = 0

    df = df.dropna().reset_index(drop=True)  # enlève les lignes sans moyenne mobile calculée

    capital = initial_capital
    position = 0  # 0 = pas de BTC détenu, 1 = on détient du BTC
    btc_held = 0
    entry_price = None
    portfolio_values = []
    trades = []
    buy_timestamps = []  # historique des achats, pour calculer le rythme hebdomadaire

    for i, row in df.iterrows():
        price = row["close"]

        # --- Détermine si on est en retard sur le quota de trades hebdomadaire ---
        effective_signal = row["signal"]
        force_mode = False
        if target_trades_per_week is not None:
            seven_days_ago = row["timestamp"] - pd.Timedelta(days=7)
            trades_last_7d = sum(1 for t in buy_timestamps if t >= seven_days_ago)
            if trades_last_7d < target_trades_per_week:
                force_mode = True
                effective_signal = 1 if (row["signal"] == 1 or row["fast_signal"] == 1) else 0

        # --- Vérification stop-loss / take-profit AVANT le signal de moyenne mobile ---
        # (une fois en position, on regarde à chaque bougie si le prix a atteint
        # un seuil de sortie automatique)
        exit_reason = None
        if position == 1 and entry_price is not None:
            change_pct = (price / entry_price - 1) * 100
            if stop_loss_pct is not None and change_pct <= -stop_loss_pct:
                exit_reason = "STOP_LOSS"
            elif take_profit_pct is not None and change_pct >= take_profit_pct:
                exit_reason = "TAKE_PROFIT"

        # Sortie automatique (stop-loss ou take-profit déclenché)
        if exit_reason is not None:
            capital_recupere = btc_held * price * (1 - fee_pct)
            capital = capital_recupere
            btc_held = 0
            position = 0
            entry_price = None
            trades.append({
                "date": row["timestamp"],
                "type": "SELL",
                "price": price,
                "capital_recupere": capital_recupere,
                "exit_reason": exit_reason,
            })

        # Signal d'achat : on n'a pas de position et le signal (normal ou de
        # secours) dit d'acheter
        elif effective_signal == 1 and position == 0:
            capital_investi = capital  # montant englouti dans ce trade (avant frais)
            btc_held = (capital * (1 - fee_pct)) / price
            capital = 0
            position = 1
            entry_price = price
            buy_timestamps.append(row["timestamp"])
            trades.append({
                "date": row["timestamp"],
                "type": "BUY",
                "price": price,
                "capital_investi": capital_investi,
                "exit_reason": "FORCÉ (quota)" if force_mode else None,
            })

        # Signal de vente normal (croisement inverse) : on a une position et le
        # signal dit de sortir
        elif effective_signal == 0 and position == 1:
            capital_recupere = btc_held * price * (1 - fee_pct)  # montant récupéré (après frais)
            capital = capital_recupere
            btc_held = 0
            position = 0
            entry_price = None
            trades.append({
                "date": row["timestamp"],
                "type": "SELL",
                "price": price,
                "capital_recupere": capital_recupere,
                "exit_reason": "SIGNAL",
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
                "raison_sortie": row.get("exit_reason", "SIGNAL"),
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

    header = f"{'#':>3} | {'Achat':^19} | {'Vente':^19} | {'Prix achat':>10} | {'Prix vente':>10} | {'Investi':>10} | {'Récupéré':>10} | {'Profit':>12} | {'Raison':>11}"
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
            f"{profit_str:>12} | "
            f"{t['raison_sortie']:>11}"
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
        "capital_investi", "capital_recupere", "profit_usdt", "raison_sortie"
    ]
    column_labels = [
        "#", "Date achat", "Date vente", "Prix achat", "Prix vente",
        "Investi (USDT)", "Récupéré (USDT)", "Profit", "Raison"
    ]

    # Ligne finale récapitulative (capital de départ -> capital final)
    final_row = ["", "", "CAPITAL FINAL", "", "", f"{initial_capital:.2f}", f"{final_capital:.2f}",
                 f"{final_capital - initial_capital:+.2f} ({(final_capital/initial_capital - 1) * 100:+.2f}%)", ""]

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
            <td>{t['raison_sortie']}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Détail des trades — Bot de trading BTC/USDT</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="sidebar.css">
<style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body {{ font-family: var(--body); background: var(--bg); color: var(--text); padding: 60px 40px 90px; -webkit-font-smoothing:antialiased; }}
    h1 {{ font-family: var(--display); font-size: 1.5em; margin-bottom: 18px; }}
    table {{ border-collapse: collapse; width: 100%; background: var(--surface); border:1px solid var(--line); border-radius:8px; overflow:hidden; font-family: var(--mono); }}
    th, td {{ padding: 10px 14px; text-align: center; border-bottom: 1px solid var(--line); font-size: 0.82em; }}
    th {{ background: var(--surface-2); color: var(--muted); text-transform:uppercase; letter-spacing:.04em; font-size:.7em; }}
    tr.gagnant {{ background-color: rgba(62,168,160,0.12); }}
    tr.perdant {{ background-color: rgba(194,84,80,0.12); }}
    tr.final {{ background-color: var(--surface-2); font-weight: bold; }}
    .summary {{ margin-bottom: 20px; font-family: var(--mono); font-size: .88em; color: var(--muted); }}
    .summary span.gagnant {{ color: var(--teal); font-weight: bold; }}
    .summary span.perdant {{ color: var(--red); font-weight: bold; }}
</style>
</head>
<body>
    <h1>Détail des trades — Stratégie de croisement de moyennes mobiles</h1>
    <div class="summary">
        <p>Capital de départ : <b style="color:var(--text);">{initial_capital:.2f} USDT</b></p>
        <p>Trades gagnants : <span class="gagnant">{nb_gagnants}</span> |
           Trades perdants : <span class="perdant">{nb_perdants}</span></p>
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th><th>Date achat</th><th>Date vente</th>
                <th>Prix achat</th><th>Prix vente</th>
                <th>Investi (USDT)</th><th>Récupéré (USDT)</th><th>Profit</th><th>Raison</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
            <tr class="final">
                <td colspan="5">CAPITAL FINAL</td>
                <td>{initial_capital:.2f}</td>
                <td>{final_capital:.2f}</td>
                <td>{total_profit:+.2f} USDT ({total_profit_pct:+.2f}%)</td>
                <td></td>
            </tr>
        </tbody>
    </table>
<script src="sidebar.js"></script>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Page HTML sauvegardée dans {filename}")


def calculate_max_drawdown(df):
    """
    Calcule le drawdown maximum : la plus grosse chute en % entre un sommet
    de la valeur du portefeuille et le creux qui a suivi.

    C'est une métrique clé en trading : un rendement final positif peut
    cacher une période où tu aurais perdu 30% de ton capital en cours de
    route — information cruciale pour juger si une stratégie est "vivable"
    psychologiquement et financièrement.
    """
    running_max = df["portfolio_value"].cummax()
    drawdown_pct = (df["portfolio_value"] / running_max - 1) * 100
    max_drawdown_pct = drawdown_pct.min()
    return max_drawdown_pct


def print_performance_summary(df, trades_df, initial_capital):
    final_value = df["portfolio_value"].iloc[-1]
    total_return_pct = (final_value / initial_capital - 1) * 100

    # Performance si on avait juste acheté et gardé (buy & hold), pour comparaison
    buy_hold_return_pct = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
    max_drawdown_pct = calculate_max_drawdown(df)

    print("=" * 50)
    print("RÉSUMÉ DE PERFORMANCE")
    print("=" * 50)
    print(f"Capital de départ      : {initial_capital:.2f} USDT")
    print(f"Capital final           : {final_value:.2f} USDT")
    print(f"Rendement stratégie     : {total_return_pct:+.2f}%")
    print(f"Rendement buy & hold     : {buy_hold_return_pct:+.2f}%")
    print(f"Drawdown maximum         : {max_drawdown_pct:.2f}%")
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


def log_to_journal(params, df, trades_df, initial_capital, filename="journal-data.json"):
    """
    Enregistre ce run dans un journal de bord (fichier JSON), pour garder une
    trace de l'évolution de tes tests dans le temps. Chaque exécution de
    backtest.py ajoute une nouvelle entrée — rien à faire manuellement.

    Le fichier est lu par journal.html pour afficher l'historique sur le site.
    """
    import json
    import os
    from datetime import datetime

    final_value = df["portfolio_value"].iloc[-1]
    return_pct = (final_value / initial_capital - 1) * 100
    buy_hold_pct = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
    max_dd = calculate_max_drawdown(df)

    entry = {
        "horodatage": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "periode_donnees": {
            "debut": df["timestamp"].iloc[0].strftime("%Y-%m-%d"),
            "fin": df["timestamp"].iloc[-1].strftime("%Y-%m-%d"),
        },
        "parametres": params,
        "resultats": {
            "capital_depart": initial_capital,
            "capital_final": round(final_value, 2),
            "rendement_pct": round(return_pct, 2),
            "buy_hold_pct": round(buy_hold_pct, 2),
            "drawdown_max_pct": round(max_dd, 2),
            "nb_trades": len(trades_df),
        },
    }

    history = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            history = []

    history.append(entry)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"Run ajouté au journal de bord ({filename}) — {len(history)} run(s) enregistré(s) au total.")


if __name__ == "__main__":
    INITIAL_CAPITAL = 1000

    # Stop-loss / take-profit : mets à None pour désactiver (comportement d'origine)
    STOP_LOSS_PCT = 3.0     # vend automatiquement si le prix chute de 3% depuis l'achat
    TAKE_PROFIT_PCT = 6.0   # vend automatiquement si le prix monte de 6% depuis l'achat

    # Filtre de tendance : mets à None pour désactiver. Avec "200", on n'achète
    # que si le prix est au-dessus de sa moyenne mobile 200 périodes (filtre
    # classique pour éviter d'acheter en pleine tendance baissière de fond).
    TREND_FILTER_WINDOW = 200

    # Quota de trades hebdomadaire visé : mets à None pour désactiver (la
    # stratégie ne trade alors que sur son signal normal, sans contrainte de
    # fréquence). Avec une valeur (ex: 12), active un signal de secours plus
    # réactif dès que le rythme des 7 derniers jours est en retard sur ce quota.
    TARGET_TRADES_PER_WEEK = 12

    # Charge les données récupérées par fetch_data.py
    df = pd.read_csv("btc_usdt_1h.csv", parse_dates=["timestamp"])

    df, trades_df = run_backtest(
        df,
        initial_capital=INITIAL_CAPITAL,
        short_window=20,
        long_window=50,
        fee_pct=0.001,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
        trend_filter_window=TREND_FILTER_WINDOW,
        target_trades_per_week=TARGET_TRADES_PER_WEEK
    )

    print_performance_summary(df, trades_df, INITIAL_CAPITAL)
    plot_results(df, trades_df, INITIAL_CAPITAL)

    final_capital = df["portfolio_value"].iloc[-1]
    trade_log_df = build_trade_log(trades_df, INITIAL_CAPITAL)
    print_trade_log(trade_log_df, INITIAL_CAPITAL, final_capital)
    export_trade_log_image(trade_log_df, INITIAL_CAPITAL, final_capital)
    export_trade_log_html(trade_log_df, INITIAL_CAPITAL, final_capital)

    log_to_journal(
        params={
            "short_window": 20,
            "long_window": 50,
            "stop_loss_pct": STOP_LOSS_PCT,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "trend_filter_window": TREND_FILTER_WINDOW,
            "target_trades_per_week": TARGET_TRADES_PER_WEEK,
        },
        df=df,
        trades_df=trades_df,
        initial_capital=INITIAL_CAPITAL,
    )
