from performance_monitor import PerformanceMonitor

class QuantTradingAlgorithm:
    def __init__(self, 
                 risk_aversion=1.0, 
                 initial_capital=100000,
                 model_path=None,
                 broker_api=None):
        
        self.risk_aversion = risk_aversion
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.portfolio_values = [initial_capital]
        self.performance_metrics = {}
        self.last_signal_time = None
        self.signal_cooldown = 60
        
        # Composants principaux
        self.data_handler = MarketDataHandler()
        self.impact_model = MarketImpactModel()
        self.signal_generator = SignalGenerator(model_path)
        self.execution_optimizer = ExecutionOptimizer(risk_aversion, self.impact_model)
        self.position_sizer = AdaptivePositionSizer()
        
        # Moniteur de performances
        self.performance_monitor = PerformanceMonitor(
            initial_capital=initial_capital,
            confidence_threshold=0.6,
            evaluation_window=50,
            max_drawdown_threshold=0.02,
            target_win_rate=0.55
        )
        
        # Broker API
        self.broker_api = broker_api
        
        # Chargement du modèle s'il existe
        if model_path:
            self.signal_generator.load_model()
        
        # Initialisation du gestionnaire de données
        self.data_handler.start_processing()
        
        # Initialisation de la connexion IBKR
        self.ibkr_feed = IBKRDataFeed()
        self.current_positions = {}
        
        logger.info("Algorithme de trading initialisé avec moniteur de performances")

    def execute_trade(self, symbol, quantity, action):
        """Exécute un trade via IBKR avec suivi des performances"""
        try:
            logger.info(f"Préparation de l'ordre {action} pour {symbol}...")
            contract = self.ibkr_feed.get_contract(symbol)
            
            # Création de l'ordre
            order = Order()
            order.action = action
            order.totalQuantity = abs(quantity)
            order.orderType = "MKT"
            order.tif = "DAY"
            
            # Récupération du prix actuel
            current_price = self._get_current_price(symbol)
            current_time = datetime.now()
            
            # Enregistrement de l'entrée du trade
            self.performance_monitor.record_trade_entry(
                symbol=symbol,
                entry_time=current_time,
                entry_price=current_price,
                position_size=quantity,
                signal_confidence=self.last_signal_confidence,
                volatility=self.current_volatility
            )
            
            logger.info(f"Envoi de l'ordre: {action} {abs(quantity)} {symbol}")
            self.ibkr_feed.client.placeOrder(
                self.ibkr_feed.client.next_order_id,
                contract,
                order
            )
            
            # Mise à jour des positions
            self.current_positions[symbol] = quantity
            
            logger.info("Ordre envoyé avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution du trade : {str(e)}")
            logger.error("Traceback complet :", exc_info=True)

    def close_position(self, symbol):
        """Ferme une position existante"""
        if symbol in self.current_positions and self.current_positions[symbol] != 0:
            current_position = self.current_positions[symbol]
            action = "SELL" if current_position > 0 else "BUY"
            
            # Récupération du prix actuel
            current_price = self._get_current_price(symbol)
            current_time = datetime.now()
            
            # Calcul de l'impact de marché
            market_impact = self.impact_model.estimate_market_impact(
                current_position,
                current_price,
                self.current_volatility,
                self.current_volume
            )
            
            # Enregistrement de la sortie du trade
            self.performance_monitor.record_trade_exit(
                symbol=symbol,
                exit_time=current_time,
                exit_price=current_price,
                market_impact=market_impact
            )
            
            # Exécution de l'ordre de fermeture
            self.execute_trade(symbol, abs(current_position), action)
            
            # Mise à jour des paramètres optimaux
            optimal_params = self.performance_monitor.optimize_parameters()
            self._update_trading_parameters(optimal_params)
            
            # Sauvegarde des métriques et graphiques
            self.performance_monitor.plot_performance_metrics()
            self.performance_monitor.save_metrics()

    def _update_trading_parameters(self, optimal_params):
        """Met à jour les paramètres de trading basés sur l'optimisation"""
        self.signal_cooldown = optimal_params['signal_cooldown']
        self.signal_generator.confidence_threshold = optimal_params['confidence_threshold']
        self.position_sizer.base_position_size *= optimal_params['position_size_factor']
        
        logger.info(f"""
        Paramètres de trading mis à jour:
        - Cooldown: {self.signal_cooldown:.0f}s
        - Seuil de confiance: {self.signal_generator.confidence_threshold:.2f}
        - Facteur de taille: {optimal_params['position_size_factor']:.2f}
        """)

    def _get_current_price(self, symbol):
        """Récupère le prix actuel d'un symbole"""
        try:
            market_data = self.ibkr_feed.get_historical_data(
                symbol,
                duration='60 S',
                bar_size='1 min'
            )
            if not market_data.empty:
                return market_data.iloc[-1]['close']
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du prix pour {symbol}: {str(e)}")
        return None

    def run_live_trading(self, symbols, interval='1 min'):
        """
        Exécute l'algorithme en trading live avec IBKR et monitoring des performances
        """
        logger.info("Démarrage du trading live avec monitoring...")
        
        # Vérification initiale de la connexion
        if not self.ibkr_feed.is_connected():
            logger.error("Pas de connexion à TWS. Tentative de reconnexion...")
            if not self.ibkr_feed.connect():
                logger.error("Échec de la connexion à TWS. Veuillez vérifier que TWS est en cours d'exécution.")
                return
            
        logger.info("Connexion TWS établie")
        
        # Vérification des permissions de trading
        logger.info("Vérification des permissions de trading...")
        permissions = verify_trading_permissions(self.ibkr_feed.client)
        if not any(permissions.values()):
            logger.error("Permissions de trading insuffisantes")
            return
            
        logger.info("Permissions de trading vérifiées")
        
        # Initialisation des positions
        self.current_positions = {symbol: 0 for symbol in symbols}
        logger.info(f"Positions initialisées pour les symboles: {symbols}")
        
        iteration_count = 0
        optimization_interval = 10  # Optimiser tous les 10 trades
        
        # Boucle principale de trading
        while True:
            try:
                iteration_count += 1
                logger.info(f"\n=== Itération {iteration_count} ===")
                
                # Optimisation périodique des paramètres
                if iteration_count % optimization_interval == 0:
                    logger.info("Optimisation périodique des paramètres...")
                    optimal_params = self.performance_monitor.optimize_parameters()
                    self._update_trading_parameters(optimal_params)
                
                for symbol in symbols:
                    logger.info(f"\nTraitement du symbole {symbol}...")
                    
                    # Vérification de la connexion
                    if not self.ibkr_feed.is_connected():
                        logger.error("Connexion TWS perdue. Tentative de reconnexion...")
                        if not self.ibkr_feed.connect():
                            logger.error("Échec de la reconnexion")
                            time.sleep(60)
                            continue
                    
                    # Récupération et vérification des données
                    market_data = self.ibkr_feed.get_historical_data(
                        symbol,
                        duration='1 D',
                        bar_size=interval
                    )
                    
                    if market_data.empty:
                        logger.warning(f"Aucune donnée reçue pour {symbol}")
                        continue
                    
                    # Mise à jour des variables de marché courantes
                    self.current_price = market_data.iloc[-1]['close']
                    self.current_volume = market_data.iloc[-1]['volume']
                    self.current_volatility = market_data['close'].pct_change().std()
                    
                    # Génération et évaluation du signal
                    features = self.data_handler.get_current_features()
                    if not features:
                        logger.warning("Aucune caractéristique disponible")
                        continue
                    
                    signal, confidence = self.generate_trading_signal(features)
                    self.last_signal_confidence = confidence
                    
                    logger.info(f"Signal généré: {signal}, confiance: {confidence:.4f}")
                    
                    # Exécution du trade si le signal est valide
                    if abs(signal) > 0 and confidence > self.signal_generator.confidence_threshold:
                        logger.info("Signal valide détecté, calcul de la taille de position...")
                        
                        # Calcul de la taille de position optimale
                        position_size = self.position_sizer.calculate_position_size(
                            signal,
                            confidence,
                            self.current_volatility,
                            self.capital,
                            self.current_price,
                            self.current_positions.get(symbol, 0)
                        )
                        
                        if abs(position_size) > 0:
                            action = 'BUY' if position_size > 0 else 'SELL'
                            logger.info(f"Exécution de l'ordre: {action} {abs(position_size)} {symbol}")
                            self.execute_trade(symbol, position_size, action)
                    
                    # Mise à jour et sauvegarde des métriques
                    if iteration_count % 5 == 0:  # Toutes les 5 itérations
                        self.performance_monitor.plot_performance_metrics()
                        self.performance_monitor.save_metrics()
                
                logger.info(f"Fin de l'itération {iteration_count}")
                time.sleep(60)  # Attendre 1 minute
                
            except KeyboardInterrupt:
                logger.info("Arrêt manuel de l'algorithme...")
                # Fermeture propre des positions
                for symbol in symbols:
                    if symbol in self.current_positions and self.current_positions[symbol] != 0:
                        self.close_position(symbol)
                break
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle de trading : {str(e)}")
                logger.error("Traceback complet :", exc_info=True)
                time.sleep(60) 