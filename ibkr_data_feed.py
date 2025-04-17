import time

class IBKRDataFeed:
    def __init__(self, client_id=1):
        """Initialise la connexion à TWS"""
        self.client = IB()
        self.client_id = client_id
        self.port = 7497  # Port Paper Trading
        print(f"Configuration de la connexion TWS - Port: {self.port} (Paper Trading)")

    def connect(self):
        """Établit la connexion avec TWS"""
        try:
            if not self.client.isConnected():
                print("Tentative de connexion à TWS...")
                print(f"Port utilisé: {self.port}")
                print(f"Client ID: {self.client_id}")
                
                # Vérification de la version de l'API
                try:
                    from ib_insync import __version__ as ib_version
                    print(f"Version de l'API IBKR: {ib_version}")
                except ImportError:
                    print("WARNING: Impossible de vérifier la version de l'API IBKR")
                
                # Vérification si TWS est en cours d'exécution
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', self.port))
                    sock.close()
                    if result != 0:
                        raise ConnectionError("TWS ne semble pas être en cours d'exécution ou n'écoute pas sur le port spécifié")
                    print("✓ TWS est en cours d'exécution et écoute sur le port", self.port)
                except Exception as e:
                    raise ConnectionError(f"Erreur lors de la vérification de TWS: {str(e)}")
                
                # Tentative de connexion avec retry
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        self.client.connect('127.0.0.1', self.port, self.client_id)
                        print(f"✓ Connexion établie avec succès (tentative {attempt + 1}/{max_attempts})")
                        break
                    except Exception as e:
                        if attempt == max_attempts - 1:
                            raise
                        print(f"Tentative {attempt + 1} échouée, nouvelle tentative dans 5 secondes...")
                        time.sleep(5)
                
                # Vérification de la connexion
                if not self.client.isConnected():
                    raise ConnectionError("La connexion a échoué après l'appel à connect()")
                
                # Attente de la connexion
                time.sleep(1)
                
                # Vérification finale
                if not self.client.isConnected():
                    raise ConnectionError("La connexion a été perdue après l'établissement initial")
                
                print("✓ Connexion vérifiée et stable")
            else:
                print("✓ Déjà connecté à TWS")
        except Exception as e:
            print(f"❌ Erreur de connexion: {str(e)}")
            print("\nVeuillez vérifier que:")
            print("1. TWS est en cours d'exécution")
            print("2. Le port API est correctement configuré dans TWS (7496 pour live, 7497 pour paper)")
            print("3. L'API est activée dans TWS (Edit > Global Configuration > API)")
            print("4. L'adresse IP 127.0.0.1 est autorisée dans les paramètres API")
            print("5. Le client ID est unique (généralement 1)")
            raise 