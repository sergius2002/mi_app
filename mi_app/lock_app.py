import os
import sys
import fcntl

LOCK_FILE = "/home/sancristobalspa/bot.lock"

def acquire_lock():
    lock_file = open(LOCK_FILE, 'w')
    try:
        # Intentamos bloquear el archivo de forma exclusiva y sin bloqueo
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        # Si falla, significa que otra instancia ya tiene el bloqueo
        print("Otra instancia del bot ya está corriendo.")
        sys.exit(1)

# Al inicio del script, intenta adquirir el bloqueo
lock = acquire_lock()

# Resto de tu código aquí (bot, funciones, etc.)

# Al final, asegúrate de liberar el bloqueo (opcional, si el script termina)
# fcntl.flock(lock, fcntl.LOCK_UN)
# lock.close()
# os.remove(LOCK_FILE)