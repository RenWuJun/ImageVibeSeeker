@echo off
:: This script launches Image Vibe Seeker by calling the launcher.py
:: It assumes you have Python installed on your Windows system PATH.
:: Pass --share to this script to expose the UI to the local network.

python launcher.py %*
pause