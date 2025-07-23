#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from translation_manager import TranslationManager
from utils.logger import setup_logger

def main():
    # Загрузка переменных окружения
    load_dotenv()
    
    # Настройка логирования
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE', 'translation_tool.log')
    setup_logger(log_level, log_file)
    
    logger = logging.getLogger(__name__)
    
    try:
        if not os.getenv('GOOGLE_API_KEY'):
            logger.error("GOOGLE_API_KEY не найден в .env файле.")
            sys.exit(1)
            
        manager = TranslationManager()
        manager.run()
        
    except KeyboardInterrupt:
        logger.info("\nРабота программы прервана пользователем")
        sys.exit(0)
    except Exception as e:
        logger.exception("Произошла непредвиденная ошибка")
        sys.exit(1)

if __name__ == "__main__":
    main()
