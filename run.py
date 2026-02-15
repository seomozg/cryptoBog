#!/usr/bin/env python3
"""
Crypto Alpha AI Advisor - Main entry point
"""

import logging
from web.app import create_app

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
