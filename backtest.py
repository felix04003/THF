"""
Backtest de l'algorithme de trading quantitatif
- Données historiques IBKR (2 ans, barres journalières)
- Split train 70% / test 30% (walk-forward)
- Métriques : Sharpe, Max Drawdown, Win Rate, Profit Factor, Rendement total
- Rapport JSON + graphique PNG
"""

import sys
import os
import logging
import importlib.util
import json
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Import du module principal (fichier sans extension .py)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# Recherche du fichier principal (insensible à l'encodage du nom)
_main_file = next(
    (os.path.join(_PROJECT_ROOT, f) for f in os.listdir(_PROJECT_ROOT)
     if f.startswith("Algorithme") and not f.endswith(".py") and os.path.isfile(os.path.join(_PROJECT_ROOT, f))),
    None
)
if _main_file is None:
    raise FileNotFoundError("Fichier principal 'Algorithme de Trading...' introuvable dans " + _PROJECT_ROOT)

from importlib.machinery import SourceFileLoader
_loader = SourceFileLoader("trading_algo", _main_file)
_mod = _loader.load_module()

IBKRConnection = _mod.IBKRConnection
AdaptivePositionSizer = _mod.AdaptivePositionSizer
QuantTradingAlgorithm = _mod.QuantTradingAlgorithm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SYMBOLS = ['AAPL', 'GOOGL', 'MSFT']
INITIAL_CAPITAL = 1_000_000.0   # EUR (compte paper)
TRAIN_RATIO = 0.70
IBKR_PORT = 4002                # IB Gateway Paper
HISTORY_DURATION = '2 Y'
BAR_SIZE = '1 day'
SIGNAL_THRESHOLD = 0.52

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backtest.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Récupération des données historiques
# ---------------------------------------------------------------------------
def fetch_data(ibkr: IBKRConnection, symbol: str) -> pd.DataFrame:
    """Récupère les données historiques journalières via IBKR."""
    import threading

    req_id = hash(symbol) % 10000
    event = threading.Event()

    with ibkr.lock:
        ibkr.historical_data[req_id] = []
        ibkr.historical_data_events[req_id] = event

    contract = ibkr.get_contract(symbol)
    ibkr.reqHistoricalData(
        reqId=req_id,
        contract=contract,
        endDateTime='',
        durationStr=HISTORY_DURATION,
        barSizeSetting=BAR_SIZE,
        whatToShow='TRADES',
        useRTH=1,
        formatDate=1,
        keepUpToDate=False,
        chartOptions=[]
    )

    received = event.wait(timeout=60)
    if not received:
        logger.error(f"Timeout : données non reçues pour {symbol}")
        return pd.DataFrame()

    with ibkr.lock:
        data = list(ibkr.historical_data.get(req_id, []))

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    logger.info(f"{symbol} : {len(df)} barres récupérées ({HISTORY_DURATION}, {BAR_SIZE})")
    return df


# ---------------------------------------------------------------------------
# Simulation (boucle de backtest)
# ---------------------------------------------------------------------------
def simulate(symbol: str, test_data: pd.DataFrame, algo: QuantTradingAlgorithm) -> tuple:
    """
    Simule les trades sur les données de test.
    Retourne (trades, portfolio_values).
    """
    FEATURES = ['returns', 'volatility', 'ma_ratio', 'volume_ratio',
                'price_impact', 'normalized_range', 'close_to_open']

    position_sizer = _mod.AdaptivePositionSizer()
    signal_gen = algo.signal_generator

    capital = INITIAL_CAPITAL
    position = 0.0
    entry_price = None
    entry_idx = None
    trades = []
    portfolio_values = [capital]

    for i, (_, row) in enumerate(test_data.iterrows()):
        price = row['close']
        vol = max(row['volatility'], 0.001)

        feature_vec = np.array([[row[f] for f in FEATURES]])
        signal, confidence = signal_gen.predict(feature_vec, threshold=SIGNAL_THRESHOLD)

        target_units = position_sizer.calculate_position_size(
            signal, confidence, vol, capital, price, position
        )
        delta = round(target_units)

        if delta != 0:
            # Fermeture si changement de sens
            if position != 0 and entry_price is not None:
                if (position > 0 and delta < 0) or (position < 0 and delta > 0):
                    pnl = position * (price - entry_price)
                    trades.append({
                        'symbol': symbol,
                        'entry_price': entry_price,
                        'exit_price': price,
                        'units': position,
                        'pnl': pnl,
                        'duration_bars': i - entry_idx,
                        'confidence': confidence,
                    })
                    capital += pnl
                    position = 0.0
                    entry_price = None
                    entry_idx = None

            # Ouverture nouvelle position
            if signal != 0:
                position = float(delta)
                entry_price = price
                entry_idx = i

        portfolio_values.append(capital + position * price)

    # Clôture en fin de période
    if position != 0 and entry_price is not None:
        final_price = test_data.iloc[-1]['close']
        pnl = position * (final_price - entry_price)
        trades.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': final_price,
            'units': position,
            'pnl': pnl,
            'duration_bars': len(test_data) - 1 - (entry_idx or 0),
            'confidence': float(confidence) if confidence else 0.0,
        })

    return trades, portfolio_values


# ---------------------------------------------------------------------------
# Métriques de performance
# ---------------------------------------------------------------------------
def compute_metrics(symbol: str, trades: list, portfolio_values: list) -> dict:
    if not trades:
        logger.warning(f"{symbol} : aucun trade exécuté")
        return {'symbol': symbol, 'n_trades': 0}

    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls)
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

    pv = np.array(portfolio_values, dtype=float)
    daily_ret = np.diff(pv) / np.where(pv[:-1] != 0, pv[:-1], 1e-9)

    sharpe = 0.0
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(np.sqrt(252) * daily_ret.mean() / daily_ret.std())

    cum = np.cumprod(1 + np.clip(daily_ret, -0.99, 10))
    roll_max = np.maximum.accumulate(cum)
    drawdowns = (cum - roll_max) / np.where(roll_max != 0, roll_max, 1e-9)
    max_dd = float(abs(drawdowns.min())) if len(drawdowns) > 0 else 0.0

    total_return = float((pv[-1] / INITIAL_CAPITAL - 1) * 100)
    avg_duration = float(np.mean([t['duration_bars'] for t in trades]))

    m = {
        'symbol': symbol,
        'n_trades': len(trades),
        'win_rate_pct': round(win_rate * 100, 2),
        'profit_factor': round(profit_factor, 3),
        'sharpe_ratio': round(sharpe, 3),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'total_return_pct': round(total_return, 2),
        'gross_profit_eur': round(gross_profit, 2),
        'gross_loss_eur': round(gross_loss, 2),
        'avg_duration_bars': round(avg_duration, 1),
        'final_capital_eur': round(float(pv[-1]), 2),
    }

    logger.info(
        f"\n{'─'*46}\n"
        f"  {symbol} — Résultats Backtest\n"
        f"{'─'*46}\n"
        f"  Trades          : {m['n_trades']}\n"
        f"  Win Rate        : {m['win_rate_pct']}%\n"
        f"  Profit Factor   : {m['profit_factor']}\n"
        f"  Sharpe Ratio    : {m['sharpe_ratio']}\n"
        f"  Max Drawdown    : {m['max_drawdown_pct']}%\n"
        f"  Rendement Total : {m['total_return_pct']}%\n"
        f"  Capital Final   : {m['final_capital_eur']:,.2f} EUR\n"
        f"  Durée moy.      : {m['avg_duration_bars']} barres\n"
    )
    return m


# ---------------------------------------------------------------------------
# Graphique
# ---------------------------------------------------------------------------
def plot_results(all_metrics: list, output: str = 'backtest_results.png'):
    valid = [m for m in all_metrics if m.get('n_trades', 0) > 0]
    if not valid:
        return

    symbols = [m['symbol'] for m in valid]
    panels = {
        'Win Rate (%)': ('win_rate_pct', '#2196F3'),
        'Sharpe Ratio': ('sharpe_ratio', '#4CAF50'),
        'Max Drawdown (%)': ('max_drawdown_pct', '#F44336'),
        'Rendement Total (%)': ('total_return_pct', '#FF9800'),
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f'Backtest — Algorithme Quantitatif  |  {datetime.now().strftime("%Y-%m-%d")}',
        fontsize=13, fontweight='bold'
    )

    for ax, (title, (key, color)) in zip(axes.flat, panels.items()):
        values = [m.get(key, 0) for m in valid]
        bar_colors = [color if v >= 0 else '#F44336' for v in values]
        bars = ax.bar(symbols, values, color=bar_colors, alpha=0.85, width=0.5)
        ax.set_title(title, fontweight='bold')
        ax.axhline(0, color='black', linewidth=0.8, linestyle='--')
        ax.grid(True, axis='y', alpha=0.3)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f'{val:.2f}',
                ha='center', va='bottom', fontsize=9
            )

    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    logger.info(f"Graphique sauvegardé : {output}")


# ---------------------------------------------------------------------------
# Rapport JSON
# ---------------------------------------------------------------------------
def save_report(all_metrics: list, output: str = 'backtest_report.json') -> dict:
    valid = [m for m in all_metrics if m.get('n_trades', 0) > 0]

    summary = {}
    if valid:
        summary = {
            'avg_sharpe_ratio': round(np.mean([m['sharpe_ratio'] for m in valid]), 3),
            'avg_win_rate_pct': round(np.mean([m['win_rate_pct'] for m in valid]), 2),
            'avg_max_drawdown_pct': round(np.mean([m['max_drawdown_pct'] for m in valid]), 2),
            'avg_total_return_pct': round(np.mean([m['total_return_pct'] for m in valid]), 2),
            'total_trades': sum(m['n_trades'] for m in valid),
        }

    report = {
        'generated_at': datetime.now().isoformat(),
        'config': {
            'symbols': SYMBOLS,
            'initial_capital_eur': INITIAL_CAPITAL,
            'train_ratio': TRAIN_RATIO,
            'history_duration': HISTORY_DURATION,
            'bar_size': BAR_SIZE,
            'signal_threshold': SIGNAL_THRESHOLD,
            'ibkr_port': IBKR_PORT,
        },
        'results': all_metrics,
        'summary': summary,
    }

    with open(output, 'w') as f:
        json.dump(report, f, indent=4)
    logger.info(f"Rapport JSON sauvegardé : {output}")
    return report


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("  DÉMARRAGE DU BACKTEST")
    logger.info(f"  Symboles       : {SYMBOLS}")
    logger.info(f"  Capital        : {INITIAL_CAPITAL:,.0f} EUR")
    logger.info(f"  Split          : {int(TRAIN_RATIO*100)}% train / {int((1-TRAIN_RATIO)*100)}% test")
    logger.info(f"  Données        : {HISTORY_DURATION}, {BAR_SIZE}")
    logger.info("=" * 50)

    # Connexion IBKR partagée pour la récupération de données
    ibkr = IBKRConnection()
    if not ibkr.connectIBKR(port=IBKR_PORT):
        logger.error("Impossible de se connecter à IB Gateway (port 4002).")
        sys.exit(1)

    all_metrics = []

    for symbol in SYMBOLS:
        logger.info(f"\n>>> Traitement : {symbol}")
        try:
            # 1. Données historiques
            raw_data = fetch_data(ibkr, symbol)
            if raw_data.empty:
                logger.warning(f"{symbol} : aucune donnée, ignoré")
                continue

            # 2. Algo (preprocessing/training) sans connexion IBKR interne
            orig_connect = IBKRConnection.connectIBKR
            IBKRConnection.connectIBKR = lambda *a, **kw: False
            algo = QuantTradingAlgorithm(initial_capital=INITIAL_CAPITAL)
            IBKRConnection.connectIBKR = orig_connect

            # 3. Prétraitement + labels
            processed = algo.preprocess_data(raw_data)
            if len(processed) < 100:
                logger.warning(f"{symbol} : données insuffisantes ({len(processed)} barres)")
                continue

            labeled = algo.create_labels(processed, horizon=5, threshold=0.005)

            # 4. Split train / test
            split = int(len(labeled) * TRAIN_RATIO)
            train_data = labeled.iloc[:split]
            test_data = labeled.iloc[split:]
            logger.info(f"  Train : {len(train_data)} barres | Test : {len(test_data)} barres")

            # 5. Entraînement sur données train
            algo.train_models(train_data)

            # 6. Simulation sur données test
            trades, portfolio_values = simulate(symbol, test_data, algo)

            # 7. Métriques
            metrics = compute_metrics(symbol, trades, portfolio_values)
            metrics['train_bars'] = len(train_data)
            metrics['test_bars'] = len(test_data)
            all_metrics.append(metrics)

        except Exception as e:
            logger.error(f"Erreur backtest {symbol} : {e}", exc_info=True)

    # Déconnexion
    if ibkr.isConnected():
        ibkr.disconnect()
        logger.info("Déconnexion IBKR")

    if not all_metrics:
        logger.error("Aucun résultat. Vérifiez la connexion et les données.")
        sys.exit(1)

    # Rapport et graphique
    report = save_report(all_metrics)
    plot_results(all_metrics)

    s = report['summary']
    logger.info("\n" + "=" * 50)
    logger.info("  RÉSUMÉ GLOBAL")
    logger.info("=" * 50)
    logger.info(f"  Trades total     : {s.get('total_trades', 0)}")
    logger.info(f"  Sharpe moyen     : {s.get('avg_sharpe_ratio', 'N/A')}")
    logger.info(f"  Win Rate moyen   : {s.get('avg_win_rate_pct', 'N/A')}%")
    logger.info(f"  Drawdown moyen   : {s.get('avg_max_drawdown_pct', 'N/A')}%")
    logger.info(f"  Rendement moyen  : {s.get('avg_total_return_pct', 'N/A')}%")
    logger.info("=" * 50)
    logger.info("Résultats : backtest_report.json | backtest_results.png")
