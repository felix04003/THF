from ibapi.client import EClient
from ibapi.wrapper import EWrapper
import threading
import time
import logging
import socket
import subprocess
import os

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestConnection(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.connected = False
        self.error_messages = []
        self.connection_time = None
        
    def error(self, reqId, errorCode, errorString):
        self.error_messages.append(f"Code {errorCode}: {errorString}")
        logger.error(f"Erreur reçue: Code {errorCode} - {errorString}")
        
        # Messages d'erreur spécifiques
        if errorCode == 502:
            logger.error("✗ Port TWS incorrect")
            logger.error("Veuillez configurer le port 7497 dans TWS > Global Configuration > API")
        elif errorCode == 501:
            logger.error("✗ API non activée")
            logger.error("Veuillez cocher 'Enable ActiveX and Socket Clients' dans TWS")
        elif errorCode == 1100:
            logger.error("✗ Connexion perdue")
            logger.error("Veuillez vérifier que TWS est bien connecté à Internet")
        elif errorCode == 1101:
            logger.error("✗ Reconnexion en cours")
            logger.error("Veuillez patienter pendant la reconnexion")
        elif errorCode == 1102:
            logger.error("✗ Connexion impossible")
            logger.error("Veuillez vérifier que TWS est bien démarré et que l'API est activée")
        
    def nextValidId(self, orderId):
        self.connected = True
        self.connection_time = time.time()
        logger.info("Connexion établie avec succès")
        
    def connectionClosed(self):
        logger.error("Connexion fermée par TWS")
        self.connected = False

def check_tws_process():
    """Vérifie si le processus TWS est en cours d'exécution"""
    try:
        for proc in os.popen('ps aux | grep -i "trader workstation"').readlines():
            if 'trader workstation' in proc.lower():
                logger.info(f"Processus TWS trouvé: {proc.strip()}")
                return True
        return False
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du processus TWS: {str(e)}")
        return False

def check_port(port):
    """Vérifie si le port est accessible"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def test_connection():
    logger.info("Démarrage du test de connexion...")
    
    # Vérifier si TWS est en cours d'exécution
    if not check_tws_process():
        logger.error("TWS n'est pas en cours d'exécution")
        return
        
    logger.info("TWS est en cours d'exécution")
    
    # Vérifier si le port est accessible
    if not check_port(7497):
        logger.error("Le port 7497 n'est pas accessible")
        return
        
    logger.info("Le port 7497 est accessible")
    
    # Créer l'instance de test
    test = TestConnection()
    
    # Tenter la connexion
    logger.info("Tentative de connexion sur le port 7497...")
    try:
        test.connect('127.0.0.1', 7497, clientId=1)
    except Exception as e:
        logger.error(f"Erreur lors de la tentative de connexion: {str(e)}")
        return
    
    # Démarrer le thread API
    api_thread = threading.Thread(target=test.run, daemon=True)
    api_thread.start()
    
    # Attendre la connexion
    timeout = 5
    start_time = time.time()
    while not test.connected and time.time() - start_time < timeout:
        time.sleep(0.1)
        
    if not test.connected:
        logger.error("Échec de la connexion après 5 secondes")
        for error in test.error_messages:
            logger.error(error)
        logger.error("""
        Guide de dépannage :
        1. Vérifiez que TWS est bien démarré et connecté à Internet
        2. Dans TWS > Global Configuration > API :
           - Cochez 'Enable ActiveX and Socket Clients'
           - Définissez 'Socket port' sur 7497
           - Cochez 'Allow connections from localhost only'
           - Ajoutez '127.0.0.1' dans 'Trusted IP Addresses'
        3. Redémarrez TWS après avoir modifié ces paramètres
        4. Vérifiez que votre pare-feu n' bloque pas le port 7497
        """)
    else:
        logger.info("Test de connexion réussi")
        logger.info(f"Temps de connexion: {time.time() - test.connection_time:.2f} secondes")
        
    # Nettoyage
    if test.isConnected():
        test.disconnect()
        logger.info("Déconnexion effectuée")

if __name__ == "__main__":
    test_connection() 