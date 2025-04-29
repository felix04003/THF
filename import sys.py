import sys
from termios import IBSHIFT
import time
import socket
import subprocess
import os
from ib_insync import * # type: ignore

def check_tws_process():
    """Vérifie si TWS est en cours d'exécution"""
    print("Vérification des processus TWS...")
    try:
        # Pour Unix/Linux/Mac
        if sys.platform != 'win32':
            output = subprocess.check_output(['ps', 'aux']).decode()
            tws_running = 'tws' in output.lower() or 'trader workstation' in output.lower()
        # Pour Windows
        else:
            output = subprocess.check_output('tasklist', shell=True).decode()
            tws_running = 'tws' in output.lower() or 'trader workstation' in output.lower()
            
        if tws_running:
            print("✅ TWS est en cours d'exécution")
        else:
            print("❌ TWS n'est pas en cours d'exécution")
        return tws_running
    except Exception as e:
        print(f"❌ Erreur lors de la vérification du processus TWS: {e}")
        return False

def check_port_availability(port=7496):
    """Vérifie si le port TWS est en écoute"""
    print(f"Vérification du port {port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            print(f"✅ Le port {port} est ouvert et accessible")
            return True
        else:
            print(f"❌ Le port {port} n'est pas accessible (code: {result})")
            return False
    except Exception as e:
        print(f"❌ Erreur lors de la vérification du port {port}: {e}")
        return False

def test_basic_connection(port=7496, client_id=12345):
    """Test basique de connexion avec ib_insync"""
    print(f"Test de connexion basique au port {port} avec clientId {client_id}...")
    ib = IBSHIFT()
    try:
        ib.connect('127.0.0.1', port, clientId=client_id, timeout=10)
        if ib.isConnected():
            print("✅ Connexion réussie!")
            print(f"  Version TWS: {ib.client.serverVersion()}")
            print(f"  Comptes: {ib.managedAccounts()}")
            return True
        else:
            print("❌ Échec de la connexion")
            return False
    except Exception as e:
        print(f"❌ Erreur lors de la connexion: {e}")
        return False
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("  Déconnexion effectuée")

def run_full_diagnostic():
    """Exécute tous les tests de diagnostic"""
    print("=== DIAGNOSTIC COMPLET DE LA CONNEXION TWS ===")
    
    # Vérifier les processus
    tws_running = check_tws_process()
    if not tws_running:
        print("⚠️ TWS doit être en cours d'exécution pour les tests suivants")
    
    # Tester les ports standard
    ports = [7496, 7497, 4001, 4002]
    for port in ports:
        time.sleep(1)  # Délai pour éviter surcharge
        available = check_port_availability(port)
    
    # Tester la connexion avec différents clientId
    print("\n=== TESTS DE CONNEXION ===")
    for port in ports:
        if check_port_availability(port):
            # Tester avec plusieurs clientId
            for client_id in [1, 12345, 54321]:
                time.sleep(1)  # Délai entre tentatives
                success = test_basic_connection(port, client_id)
                if success:
                    print(f"\n✅✅✅ CONNEXION RÉUSSIE sur port {port} avec clientId {client_id}")
                    print(f"Configuration recommandée: PORT={port}, CLIENT_ID={client_id}")
                    return

    print("\n❌❌❌ DIAGNOSTIC FINAL: Aucune connexion réussie")
    print("""
    RECOMMANDATIONS:
    1. Vérifiez que TWS est correctement démarré
    2. Vérifiez la configuration API dans TWS (Global Configuration > API)
    3. Redémarrez TWS complètement
    4. Désactivez temporairement votre pare-feu/antivirus
    5. Essayez d'utiliser IB Gateway au lieu de TWS
    """)

if __name__ == "__main__":
    run_full_diagnostic()
    