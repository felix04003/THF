"""
Script de test de connexion IBKR simplifié
"""

import logging
import time
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class IBKRTester(EWrapper, EClient):
    """Classe de test pour la connexion IBKR"""
    def __init__(self, port=7497, clientId=123):
        EClient.__init__(self, self)
        self.port = port
        self.clientId = clientId
        self.connected = False
        self.next_order_id = None
        
    def nextValidId(self, orderId):
        """Callback quand la connexion est établie"""
        self.next_order_id = orderId
        self.connected = True
        logger.info(f"Connexion établie avec TWS, prochain ID d'ordre: {orderId}")
        
    def error(self, reqId, errorCode, errorString):
        """Gestion des erreurs de l'API"""
        logger.error(f"Erreur TWS: {reqId} / {errorCode} / {errorString}")
        
        # Messages d'erreur spécifiques
        if errorCode == 502:
            logger.error("✗ Port TWS incorrect")
        elif errorCode == 501:
            logger.error("✗ API non activée")
        elif errorCode == 1100:
            logger.error("✗ Connexion perdue")
        
    def connectionClosed(self):
        """Callback quand la connexion est fermée"""
        self.connected = False
        logger.error("Connexion à TWS fermée")

def test_tws_connection():
    """Test simple de connexion à TWS"""
    logger.info("Démarrage du test de connexion TWS...")
    
    # Créer l'instance de connexion
    tester = IBKRTester(port=7497, clientId=123)
    
    # Tentative de connexion
    logger.info("Tentative de connexion...")
    tester.connect('127.0.0.1', 7497, clientId=123)
    
    # Démarrer le thread API
    api_thread = threading.Thread(target=tester.run, daemon=True)
    api_thread.start()
    
    # Attendre la connexion
    timeout = 10
    start_time = time.time()
    while not tester.connected and time.time() - start_time < timeout:
        time.sleep(0.1)
        
    if tester.connected:
        logger.info("Connexion réussie!")
        
        # Attendre quelques secondes
        logger.info("Maintien de la connexion pendant 5 secondes...")
        time.sleep(5)
        
        # Déconnexion
        logger.info("Déconnexion...")
        tester.disconnect()
        logger.info("Test terminé avec succès!")
    else:
        logger.error("Échec de la connexion!")
        logger.error("""
        Vérifiez les points suivants dans TWS:
        1. TWS est bien démarré et connecté
        2. Dans File > Global Configuration > API:
           - 'Enable ActiveX and Socket Clients' est coché
           - 'Socket port' est défini sur 7497
           - 'Allow connections from localhost only' est coché
           - '127.0.0.1' est dans la liste des 'Trusted IP Addresses'
        3. Redémarrez TWS après avoir modifié ces paramètres
        """)

if __name__ == "__main__":
    test_tws_connection() 