"""
Moniteur de performances pour l'algorithme de trading
Permet le suivi et l'optimisation automatique des paramètres
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import matplotlib.pyplot as plt
from scipy.stats import norm

logger = logging.getLogger(__name__)

@dataclass
class TradeMetrics:
    """Métriques pour un trade individuel"""
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    position_size: float
    signal_confidence: float
    pnl: Optional[float] = None
    trade_duration: Optional[timedelta] = None
    max_drawdown: Optional[float] = None
    volatility_at_entry: float = 0.0
    market_impact: float = 0.0

class PerformanceMonitor:
    """
    Moniteur de performances avec optimisation automatique des paramètres
    """
    
    def __init__(self, 
                 initial_capital: float,
                 confidence_threshold: float = 0.6,
                 evaluation_window: int = 50,
                 max_drawdown_threshold: float = 0.02,
                 target_win_rate: float = 0.55):
        
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.confidence_threshold = confidence_threshold
        self.evaluation_window = evaluation_window
        self.max_drawdown_threshold = max_drawdown_threshold
        self.target_win_rate = target_win_rate
        
        # Historique des trades
        self.trades: List[TradeMetrics] = []
        self.active_trades: Dict[str, TradeMetrics] = {}
        
        # Métriques de performance
        self.daily_returns = []
        self.win_rate = 0.0
        self.profit_factor = 0.0
        self.sharpe_ratio = 0.0
        self.max_drawdown = 0.0
        
        # Paramètres optimisés
        self.optimal_params = {
            'confidence_threshold': confidence_threshold,
            'position_size_factor': 1.0,
            'signal_cooldown': 60
        }
        
        # Historique des paramètres
        self.params_history = []
        
        logger.info("Moniteur de performances initialisé")
        
    def record_trade_entry(self, 
                          symbol: str,
                          entry_time: datetime,
                          entry_price: float,
                          position_size: float,
                          signal_confidence: float,
                          volatility: float) -> None:
        """Enregistre l'entrée d'un trade"""
        
        trade = TradeMetrics(
            symbol=symbol,
            entry_time=entry_time,
            exit_time=None,
            entry_price=entry_price,
            exit_price=None,
            position_size=position_size,
            signal_confidence=signal_confidence,
            volatility_at_entry=volatility
        )
        
        self.active_trades[symbol] = trade
        logger.info(f"Trade enregistré pour {symbol} à {entry_price}")
        
    def record_trade_exit(self,
                         symbol: str,
                         exit_time: datetime,
                         exit_price: float,
                         market_impact: float) -> None:
        """Enregistre la sortie d'un trade et calcule les métriques"""
        
        if symbol not in self.active_trades:
            logger.warning(f"Aucun trade actif trouvé pour {symbol}")
            return
            
        trade = self.active_trades[symbol]
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.market_impact = market_impact
        
        # Calcul des métriques
        trade.trade_duration = exit_time - trade.entry_time
        trade.pnl = (exit_price - trade.entry_price) * trade.position_size
        
        # Mise à jour du capital
        self.current_capital += trade.pnl
        
        # Ajout aux trades terminés
        self.trades.append(trade)
        del self.active_trades[symbol]
        
        # Mise à jour des métriques globales
        self._update_performance_metrics()
        
        logger.info(f"Trade terminé pour {symbol}, PnL: {trade.pnl:.2f}")
        
    def _update_performance_metrics(self) -> None:
        """Met à jour toutes les métriques de performance"""
        
        if not self.trades:
            return
            
        # Calcul sur la fenêtre d'évaluation
        recent_trades = self.trades[-self.evaluation_window:]
        
        # Win rate
        profitable_trades = sum(1 for t in recent_trades if t.pnl and t.pnl > 0)
        self.win_rate = profitable_trades / len(recent_trades)
        
        # Profit factor
        gross_profit = sum(t.pnl for t in recent_trades if t.pnl and t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in recent_trades if t.pnl and t.pnl < 0))
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Rendements quotidiens
        daily_pnl = pd.Series([t.pnl for t in recent_trades if t.pnl]).resample('D').sum()
        self.daily_returns = daily_pnl / self.initial_capital
        
        # Sharpe ratio
        if len(self.daily_returns) > 1:
            self.sharpe_ratio = np.sqrt(252) * (
                self.daily_returns.mean() / self.daily_returns.std()
            )
        
        # Maximum drawdown
        cumulative_returns = (1 + self.daily_returns).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdowns = cumulative_returns / rolling_max - 1
        self.max_drawdown = abs(drawdowns.min())
        
        logger.info(f"""
        Métriques de performance mises à jour:
        - Win Rate: {self.win_rate:.2%}
        - Profit Factor: {self.profit_factor:.2f}
        - Sharpe Ratio: {self.sharpe_ratio:.2f}
        - Max Drawdown: {self.max_drawdown:.2%}
        """)
        
    def optimize_parameters(self) -> Dict[str, float]:
        """
        Optimise les paramètres de l'algorithme basé sur les performances récentes
        """
        if len(self.trades) < self.evaluation_window:
            logger.info("Pas assez de trades pour l'optimisation")
            return self.optimal_params
            
        # Analyse des performances récentes
        recent_trades = self.trades[-self.evaluation_window:]
        
        # Optimisation du seuil de confiance
        confidence_performance = pd.DataFrame([
            {
                'confidence': t.signal_confidence,
                'pnl': t.pnl,
                'success': 1 if t.pnl and t.pnl > 0 else 0
            }
            for t in recent_trades if t.pnl is not None
        ])
        
        if not confidence_performance.empty:
            # Trouver le seuil optimal
            thresholds = np.arange(0.5, 0.9, 0.05)
            best_threshold = self.confidence_threshold
            best_win_rate = self.win_rate
            
            for threshold in thresholds:
                high_conf_trades = confidence_performance[
                    confidence_performance['confidence'] >= threshold
                ]
                if len(high_conf_trades) > 10:
                    win_rate = high_conf_trades['success'].mean()
                    if win_rate > best_win_rate:
                        best_threshold = threshold
                        best_win_rate = win_rate
            
            self.optimal_params['confidence_threshold'] = best_threshold
        
        # Ajustement de la taille des positions
        if self.max_drawdown > self.max_drawdown_threshold:
            # Réduire la taille des positions si le drawdown est trop important
            self.optimal_params['position_size_factor'] *= 0.8
        elif self.win_rate > self.target_win_rate and self.max_drawdown < self.max_drawdown_threshold * 0.5:
            # Augmenter la taille si les performances sont bonnes
            self.optimal_params['position_size_factor'] *= 1.2
        
        # Limites de sécurité
        self.optimal_params['position_size_factor'] = np.clip(
            self.optimal_params['position_size_factor'],
            0.2,  # Minimum 20% de la taille normale
            2.0   # Maximum 200% de la taille normale
        )
        
        # Ajustement du cooldown
        avg_trade_duration = np.mean([
            t.trade_duration.total_seconds()
            for t in recent_trades
            if t.trade_duration
        ])
        
        # Ajuster le cooldown à environ 20% de la durée moyenne des trades
        if avg_trade_duration > 0:
            self.optimal_params['signal_cooldown'] = max(30, min(300, avg_trade_duration * 0.2))
        
        # Enregistrer l'historique des paramètres
        self.params_history.append({
            'timestamp': datetime.now(),
            'params': self.optimal_params.copy(),
            'metrics': {
                'win_rate': self.win_rate,
                'profit_factor': self.profit_factor,
                'sharpe_ratio': self.sharpe_ratio,
                'max_drawdown': self.max_drawdown
            }
        })
        
        logger.info(f"""
        Paramètres optimisés:
        - Seuil de confiance: {self.optimal_params['confidence_threshold']:.2f}
        - Facteur de taille: {self.optimal_params['position_size_factor']:.2f}
        - Cooldown: {self.optimal_params['signal_cooldown']:.0f}s
        """)
        
        return self.optimal_params
    
    def plot_performance_metrics(self, save_path: str = 'performance_metrics.png') -> None:
        """Génère un graphique des métriques de performance"""
        
        if not self.trades:
            logger.warning("Pas de données pour générer le graphique")
            return
            
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Rendements cumulés
        cumulative_returns = (1 + pd.Series(self.daily_returns)).cumprod()
        ax1.plot(cumulative_returns.index, cumulative_returns.values)
        ax1.set_title('Rendements Cumulés')
        ax1.grid(True)
        
        # Distribution des rendements
        ax2.hist(self.daily_returns, bins=50, density=True, alpha=0.7)
        ax2.set_title('Distribution des Rendements')
        
        # Évolution des paramètres
        params_df = pd.DataFrame([p['params'] for p in self.params_history])
        timestamps = [p['timestamp'] for p in self.params_history]
        ax3.plot(timestamps, params_df['confidence_threshold'], label='Confiance')
        ax3.plot(timestamps, params_df['position_size_factor'], label='Taille')
        ax3.set_title('Évolution des Paramètres')
        ax3.legend()
        ax3.grid(True)
        
        # Drawdown
        cumulative_returns = (1 + pd.Series(self.daily_returns)).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdowns = (cumulative_returns - rolling_max) / rolling_max
        ax4.fill_between(drawdowns.index, drawdowns.values, 0, color='red', alpha=0.3)
        ax4.set_title('Drawdown')
        ax4.grid(True)
        
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        
        logger.info(f"Graphique des performances sauvegardé dans {save_path}")
    
    def save_metrics(self, file_path: str = 'performance_metrics.json') -> None:
        """Sauvegarde les métriques de performance"""
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'total_return': (self.current_capital / self.initial_capital - 1) * 100,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'optimal_params': self.optimal_params,
            'number_of_trades': len(self.trades),
            'active_trades': len(self.active_trades)
        }
        
        with open(file_path, 'w') as f:
            json.dump(metrics, f, indent=4)
            
        logger.info(f"Métriques sauvegardées dans {file_path}") 