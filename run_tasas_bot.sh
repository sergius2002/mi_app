#!/bin/bash
while true; do
    source ~/.virtualenvs/mi_app_bots/bin/activate
    cd ~/mi_app
    python envio_tasas.py
    echo "Bot de tasas se detuvo. Reiniciando en 60 segundos..."
    sleep 60
done
