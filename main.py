#!/usr/bin/env python3
"""
YNAB Transaction Tagger - Main Entry Point

Starts the web server and opens the browser automatically.
"""

import asyncio
import webbrowser
import logging
from templates.web_server import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def open_browser(host: str = '127.0.0.1', port: int = 5000):
    """
    Open web browser to application URL.
    
    Args:
        host: Server host address
        port: Server port number
    """
    url = f'http://{host}:{port}'
    logger.info(f'Opening browser to {url}')
    webbrowser.open(url)


async def run_server():
    """Run the Quart web server"""
    host = '127.0.0.1'
    port = 5000
    
    logger.info('='*60)
    logger.info('YNAB Transaction Tagger')
    logger.info('='*60)
    logger.info(f'Starting server on http://{host}:{port}')
    logger.info('Press CTRL+C to quit')
    logger.info('='*60)
    
    # Open browser after short delay
    asyncio.create_task(delayed_browser_open(host, port))
    
    # Start server
    await app.run_task(host=host, port=port, debug=False)


async def delayed_browser_open(host: str, port: int, delay: float = 1.5):
    """
    Open browser after a short delay to ensure server is ready.
    
    Args:
        host: Server host address
        port: Server port number
        delay: Delay in seconds before opening browser
    """
    await asyncio.sleep(delay)
    open_browser(host, port)


def main():
    """Main entry point"""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info('\nServer stopped by user')
    except Exception as e:
        logger.error(f'Error running server: {e}')
        raise


if __name__ == '__main__':
    main()
