import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(level_str='INFO', log_file='translation_tool.log'):
    """
    Настройка логирования для приложения
    
    Args:
        level_str (str): Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file (str): Имя файла для записи логов
    """
    # Создаем директорию для логов, если её нет
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_path = log_dir / log_file
    
    # Преобразуем строковый уровень логирования в числовой
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # Настройка формата логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    
    # Настройка обработчика для файла
    file_handler = RotatingFileHandler(
        log_path, 
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    
    # Настройка обработчика для консоли (только предупреждения и выше)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.WARNING)  # В консоль только предупреждения и выше
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем все существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Добавляем наши обработчики
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console)
    
    # Настройка логирования для библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Логирование инициализировано. Уровень: {level_str}. Файл: {log_path}")
    
    return logger
