"""Ancien point d'entrée, conservé pour compatibilité : lance l'application complète."""
import asyncio

from app import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
