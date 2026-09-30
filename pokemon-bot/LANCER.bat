@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bot Pokemon

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python n'est pas installe. Installe-le depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relance ce fichier.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Installation (premiere fois uniquement, 1 a 2 minutes^)...
    %PY% -m venv .venv || goto :erreur
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :erreur
)

".venv\Scripts\python.exe" bot.py
echo.
echo Le bot s'est arrete. Ferme cette fenetre ou relance LANCER.bat.
pause
exit /b 0

:erreur
echo Erreur pendant l'installation. Envoie-moi ce qui est ecrit au-dessus.
rmdir /s /q .venv 2>nul
pause
exit /b 1
