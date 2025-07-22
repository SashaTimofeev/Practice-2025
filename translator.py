import os
import google.generativeai as genai
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class GeminiTranslator:
    def __init__(self):
        """Инициализация переводчика с использованием Gemini API"""
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY не найден в переменных окружения")
            
        genai.configure(api_key=api_key)
        # Используем gemini-1.5-flash как указано в требованиях
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.max_retries = 3
        self.retry_delay = 2  # секунды
        
        # Промпт для перевода
        self.translation_prompt = """
        Ты профессиональный переводчик с английского на русский для программного обеспечения Indico.
        Indico - это инструмент с открытым исходным кодом для организации мероприятий, архивирования и совместной работы.
        
        Основные особенности Indico:
        - Рабочий процесс организации мероприятий, подходящий для лекций, встреч, семинаров и конференций
        - Многоуровневая система защиты на основе древовидной структуры
        - Простая загрузка и извлечение презентаций, статей и других документов
        - Постоянное архивирование всех материалов и метаданных мероприятия
        - Функции рецензирования для статей конференции
        - Полное покрытие жизненного цикла конференции
        - Бронирование и управление помещениями
        - Интеграция с несколькими инструментами для совместной работы
        
        Пожалуйста, переведи следующий текст на русский язык, сохраняя технические термины и названия без изменений, если они не имеют устоявшегося перевода.
        Сохраняй регистр и форматирование исходного текста.
        Если текст содержит плейсхолдеры в формате %s, {var}, $var или {{var}}, не изменяй их.
        
        Текст для перевода:
        """

    def translate(self, text: str) -> Optional[str]:
        """
        Переводит текст с английского на русский с помощью Gemini API
        
        Args:
            text: Текст для перевода
            
        Returns:
            str: Переведенный текст или None в случае ошибки
        """
        if not text.strip():
            return text
            
        prompt = self.translation_prompt + f'"{text}"'
        
        for attempt in range(self.max_retries):
            try:
                response = self.model.generate_content(prompt)
                
                if not response.text:
                    raise ValueError("Пустой ответ от API")
                    
                # Очищаем ответ от кавычек, если они есть
                translated = response.text.strip()
                if (translated.startswith('"') and translated.endswith('"')) or \
                   (translated.startswith("'") and translated.endswith("'")):
                    translated = translated[1:-1]
                
                logger.debug(f"Переведено: {text} -> {translated}")
                return translated
                
            except Exception as e:
                logger.warning(f"Попытка {attempt + 1} не удалась: {str(e)}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Не удалось перевести текст после {self.max_retries} попыток: {text}")
                    return None
                
                # Экспоненциальная задержка перед повторной попыткой
                import time
                time.sleep(self.retry_delay * (2 ** attempt))
