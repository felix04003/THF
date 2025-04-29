import time
import logging
import threading
from test_ibkr import IBKRTester

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class IBKRDataFeed:
    def __init__(self, client_id=123):
        """Initialise la connexion à TWS"""
        self.client = IBKRTester(clientId=client_id)
        self.client_id = client_id
        self.port = 7497  # Port Paper Trading
        logger.info(f"Configuration de la connexion TWS - Port: {self.port} (Paper Trading)")

    def connect(self):
        """Établit la connexion avec TWS"""
        try:
            if not self.client.isConnected():
                logger.info("Tentative de connexion à TWS...")
                logger.info(f"Port utilisé: {self.port}")
                logger.info(f"Client ID: {self.client_id}")
                
                # Vérification si TWS est en cours d'exécution
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', self.port))
                    sock.close()
                    if result != 0:
                        raise ConnectionError("TWS ne semble pas être en cours d'exécution ou n'écoute pas sur le port spécifié")
                    logger.info(f"✓ TWS est en cours d'exécution et écoute sur le port {self.port}")
                except Exception as e:
                    raise ConnectionError(f"Erreur lors de la vérification de TWS: {str(e)}")
                
                # Tentative de connexion avec retry
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        self.client.connect('127.0.0.1', self.port, self.client_id)
                        logger.info(f"✓ Connexion établie avec succès (tentative {attempt + 1}/{max_attempts})")
                        
                        # Démarrer le thread API
                        api_thread = threading.Thread(target=self.client.run, daemon=True)
                        api_thread.start()
                        logger.info("✓ Thread API démarré")
                        
                        # Attendre la connexion
                        timeout = 10
                        start_time = time.time()
                        while not self.client.connected and time.time() - start_time < timeout:
                            time.sleep(0.1)
                            
                        if not self.client.connected:
                            raise ConnectionError("Timeout lors de l'attente de la connexion")
                            
                        break
                    except Exception as e:
                        if attempt == max_attempts - 1:
                            raise
                        logger.warning(f"Tentative {attempt + 1} échouée ({str(e)}), nouvelle tentative dans 5 secondes...")
                        time.sleep(5)
                
                # Vérification finale
                if not self.client.isConnected():
                    raise ConnectionError("La connexion a été perdue après l'établissement initial")
                
                logger.info("✓ Connexion vérifiée et stable")
            else:
                logger.info("✓ Déjà connecté à TWS")
        except Exception as e:
            logger.error(f"❌ Erreur de connexion: {str(e)}")
            logger.error("\nVeuillez vérifier que:")
            logger.error("1. TWS est en cours d'exécution")
            logger.error("2. Le port API est correctement configuré dans TWS (7496 pour live, 7497 pour paper)")
            logger.error("3. L'API est activée dans TWS (Edit > Global Configuration > API)")
            logger.error("4. L'adresse IP 127.0.0.1 est autorisée dans les paramètres API")
            logger.error("5. Le client ID est unique (généralement 123)")
            raise

if __name__ == "__main__":
    feed = IBKRDataFeed()
    feed.connect() 