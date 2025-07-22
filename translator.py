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
        self.model = genai.GenerativeModel('gemini-2.0-flash')
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
        
        Правила, которыми ты должен руководствоваться при переводе текста на русский язык:
        - Сохраняй технические термины и названия без изменений, если они не имеют устоявшегося перевода.
        - Сохраняй регистр и форматирование исходного текста.
        - Если текст содержит плейсхолдеры в формате %s, {var}, $var или {{var}}, не изменяй их.
        - Не оборачивай переведенный текст в кавычки
        - Не пиши в начале переведенной строки её номер
        
        Текст для перевода:
        """

    # Константы для пакетной обработки
    BATCH_SIZE = 10  # Количество строк для перевода в одном запросе
    
    def _clean_translation(self, translated_text: str) -> str:
        """Очищает переведенный текст от лишних символов"""
        if not translated_text:
            return ""
            
        # Удаляем кавычки, если они есть
        text = translated_text.strip()
        if (text.startswith('"') and text.endswith('"')) or \
           (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]
            
        return text
    
    def _create_batch_prompt(self, texts: list[str]) -> str:
        """Создает промпт для пакетного перевода"""
        prompt = self.translation_prompt + "\n\n"
        prompt += "Переведите следующие строки, разделяя переводы пустой строкой. Сохраняйте порядок:\n\n"
        
        for i, text in enumerate(texts, 1):
            prompt += f"{i}. {text}\n"
            
        return prompt
    
    def _parse_retry_delay(self, error_msg: str) -> int:
        """Извлекает время задержки из сообщения об ошибке API"""
        try:
            # Пытаемся найти retry_delay в сообщении об ошибке
            import re
            match = re.search(r'retry_delay\s*{\s*seconds\s*:\s*(\d+)', error_msg)
            if match:
                return int(match.group(1)) + 5  # Добавляем 5 секунд на всякий случай
        except Exception as e:
            logger.warning(f"Не удалось распознать время задержки: {str(e)}")
        
        # Возвращаем задержку по умолчанию, если не удалось распознать
        return self.retry_delay * (2 ** 2)  # 8 секунд по умолчанию
    
    def _handle_api_error(self, error, attempt: int) -> bool:
        """Обрабатывает ошибку API и возвращает True, если нужно повторить запрос"""
        error_msg = str(error)
        
        # Проверяем, не превышен ли лимит запросов
        if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
            delay = self._parse_retry_delay(error_msg)
            logger.warning(f"Превышен лимит запросов. Ждем {delay} секунд перед повторной попыткой...")
            import time
            time.sleep(delay)
            return True
            
        # Для других ошибок используем экспоненциальную задержку
        delay = self.retry_delay * (2 ** attempt)
        logger.warning(f"Ошибка API (попытка {attempt + 1}/{self.max_retries}). Ждем {delay} секунд...")
        import time
        time.sleep(delay)
        return True
    
    def translate_batch(self, texts: list[str]) -> list[Optional[str]]:
        """
        Переводит пакет строк с английского на русский с помощью Gemini API
        
        Args:
            texts: Список текстов для перевода
            
        Returns:
            list: Список переведенных текстов или None для неудачных переводов
        """
        if not texts:
            return []
            
        prompt = self._create_batch_prompt(texts)
        
        for attempt in range(self.max_retries):
            try:
                response = self.model.generate_content(prompt)
                
                if not response.text:
                    raise ValueError("Пустой ответ от API")
                
                # Разбиваем ответ на отдельные переводы
                translations = [self._clean_translation(t) for t in response.text.split('\n\n')]
                
                # Проверяем, что получили столько же переводов, сколько запрашивали
                if len(translations) != len(texts):
                    logger.warning(f"Количество переводов ({len(translations)}) не совпадает с количеством запросов ({len(texts)})."
                                 f" Ответ: {response.text[:200]}...")
                    # Возвращаем None для всех переводов в пакете в случае несоответствия
                    return [None] * len(texts)
                
                logger.debug(f"Успешно переведено {len(translations)} строк")
                return translations
                
            except Exception as e:
                logger.warning(f"Ошибка при переводе пакета (попытка {attempt + 1}/{self.max_retries}): {str(e)}")
                
                if attempt == self.max_retries - 1:
                    logger.error(f"Не удалось перевести пакет после {self.max_retries} попыток")
                    return [None] * len(texts)
                
                # Обрабатываем ошибку и решаем, нужно ли повторять запрос
                if not self._handle_api_error(e, attempt):
                    return [None] * len(texts)
    
    def translate(self, text: str) -> Optional[str]:
        """
        Переводит одну строку текста с английского на русский с помощью Gemini API
        
        Args:
            text: Текст для перевода
            
        Returns:
            str: Переведенный текст или None в случае ошибки
        """
        if not text.strip():
            return text
            
        # Используем пакетный перевод даже для одной строки
        result = self.translate_batch([text])
        return result[0] if result else None
