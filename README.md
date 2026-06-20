# Bot de trading crypto — étape 1 : Backtest

Ce projet contient les premières bases d'un bot de trading crypto. On commence
par le **backtest** : simuler une stratégie sur des données passées, avant
de risquer le moindre euro/dollar/dollar fictif.

## Stratégie utilisée : croisement de moyennes mobiles

C'est une stratégie simple et classique pour apprendre :
- Si la moyenne mobile courte (20 périodes) passe au-dessus de la longue
  (50 périodes) → signal d'achat.
- Si elle repasse au-dessous → signal de vente.

⚠️ **Important** : cette stratégie n'a aucune garantie de profitabilité.
On l'utilise ici pour apprendre la mécanique du backtest, pas comme
recommandation d'investissement.

## Installation (à faire sur TON ordinateur)

Ce projet a besoin d'accéder à l'API publique de Binance pour récupérer des
données — ça ne fonctionne pas depuis l'environnement sandbox de Claude.
Télécharge les fichiers `.py` et lance-les chez toi :

```bash
pip install -r requirements.txt
```

## Utilisation

### Étape 1 — Récupérer les données historiques

```bash
python fetch_data.py
```

Ça va créer un fichier `btc_usdt_1h.csv` avec ~3000 bougies de 1h
(environ 4 mois d'historique BTC/USDT).

Tu peux changer la paire ou le timeframe en éditant les paramètres en
bas du fichier `fetch_data.py` (ex: `symbol="ETH/USDT"`, `timeframe="4h"`).

### Étape 2 — Lancer le backtest

```bash
python backtest.py
```

Ça affiche un résumé (rendement, nombre de trades, comparaison avec un
simple "buy & hold") et génère un graphique `backtest_results.png`
montrant :
- Le prix avec les moyennes mobiles et les points d'achat/vente
- L'évolution de la valeur du portefeuille dans le temps

## Fichiers du projet

| Fichier         | Rôle                                                          |
|-----------------|----------------------------------------------------------------|
| `fetch_data.py` | Télécharge les données historiques depuis Binance              |
| `strategy.py`   | Calcule les moyennes mobiles et génère les signaux achat/vente |
| `backtest.py`   | Simule la stratégie et affiche les résultats                  |

## Prochaines étapes possibles

Une fois que tu es à l'aise avec ce backtest, on pourra :
1. **Tester d'autres paramètres** (ex: moyennes 10/30 au lieu de 20/50) pour
   voir leur impact
2. **Ajouter une gestion du risque** (stop-loss, taille de position)
3. **Tester plusieurs paires** en parallèle
4. **Passer au paper trading** : connecter le bot au testnet Binance pour le
   voir "trader" en conditions réelles, mais sans argent réel
5. Seulement après tout ça : envisager un déploiement avec un petit capital réel

N'hésite pas à me montrer les résultats de ton backtest une fois lancé, on
pourra les analyser ensemble et itérer sur la stratégie.
