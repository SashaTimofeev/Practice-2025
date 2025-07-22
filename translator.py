# translator.py

import os
import google.generativeai as genai
import logging
import json
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GeminiTranslator:
    def __init__(self):
        """Инициализация переводчика с использованием Gemini API"""
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY не найден в переменных окружения")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash') 
        self.max_retries = 3
        self.retry_delay = 5  # секунды
        self.BATCH_SIZE = 10  

    def _create_batch_prompt(self, entries: List[Dict[str, Any]]) -> str:
        """Создает промпт для пакетного перевода с инструкцией вывода в JSON."""
        prompt = """
You are a professional software translator from English to Russian for an open-source event management tool called Indico.

Translate the following list of texts. Follow these rules STRICTLY:
1.  Preserve technical terms and placeholders like `%s`, `{var}`, `$var`, `%(name)s`.
2.  Maintain the original case and formatting where appropriate for the context.
3.  Your entire response MUST be a valid JSON array `[...]` containing one JSON object for each input text, in the same order. Do not output anything before or after the JSON array.

For each text, generate a JSON object with a "type" field and a "translation" field.

- If the text is a simple string, the JSON object should be:
  {"type": "simple", "translation": "your_russian_translation"}

- If the text has plural forms (marked with [PLURAL]), the JSON object must include all four Russian plural forms:
  {"type": "plural", "translation": {"one": "форма для 1", "few": "форма для 2-4", "many": "форма для 5+", "other": "общая форма"}}

Example Input:
[
  {"id": 1, "type": "simple", "text": "Upload BoA"},
  {"id": 2, "type": "plural", "text": {"msgid": "one file", "msgid_plural": "%(num)d files"}}
]

Example Output for the above input:
[
  {"id": 1, "type": "simple", "translation": "Загрузить BoA"},
  {"id": 2, "type": "plural", "translation": {"one": "один файл", "few": "%(num)d файла", "many": "%(num)d файлов", "other": "%(num)d файл(ов)"}}
]

Now, translate the following texts:
"""
        
        # Подготавливаем входные данные в формате JSON для промпта
        input_data = []
        for i, entry in enumerate(entries):
            if isinstance(entry, dict) and 'msgid_plural' in entry:
                input_data.append({
                    "id": i,
                    "type": "plural",
                    "text": {
                        "msgid": entry['msgid'],
                        "msgid_plural": entry['msgid_plural']
                    }
                })
            else:
                text = entry if isinstance(entry, str) else entry['msgid']
                input_data.append({
                    "id": i,
                    "type": "simple",
                    "text": text
                })

        prompt += json.dumps(input_data, indent=2, ensure_ascii=False)
        return prompt

    def translate_batch(self, entries: list) -> List[Optional[Dict]]:
        """Переводит пакет строк, ожидая ответ в формате JSON."""
        if not entries:
            return []
            
        prompt = self._create_batch_prompt(entries)
        logger.debug(f"Отправка запроса на перевод (всего {len(entries)} записей).")
        
        for attempt in range(self.max_retries):
            try:
                # Используем JSON режим, если модель его поддерживает
                generation_config = {
                    "response_mime_type": "application/json",
                }
                response = self.model.generate_content(prompt, generation_config=generation_config)
                
                # Парсим JSON ответ
                response_json = json.loads(response.text)
                
                if not isinstance(response_json, list) or len(response_json) != len(entries):
                    logger.warning(f"Ответ API не соответствует ожидаемому формату. Получено {len(response_json)}/{len(entries)} записей.")
                    # Попробуем еще раз, возможно, временный сбой
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    return [None] * len(entries)

                results = []
                for res_item in response_json:
                    res_type = res_item.get('type')
                    translation = res_item.get('translation')

                    if res_type == 'simple' and isinstance(translation, str):
                        results.append({'type': 'simple', 'text': translation})
                    elif res_type == 'plural' and isinstance(translation, dict):
                        results.append({'type': 'plural', 'forms': translation})
                    else:
                        logger.warning(f"Некорректный элемент в ответе JSON: {res_item}")
                        results.append(None)
                
                logger.info(f"Успешно переведено и обработано {len(results)} строк.")
                return results

            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования JSON ответа API: {e}\nОтвет: {response.text[:500]}")
                if attempt == self.max_retries - 1:
                    return [None] * len(entries)
                time.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Ошибка при переводе пакета (попытка {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    return [None] * len(entries)
                time.sleep(self.retry_delay * (attempt + 1))
        
        return [None] * len(entries)

    def translate(self, text: str) -> Optional[str]:
        """Переводит одну строку текста."""
        if not text.strip():
            return text
            
        result = self.translate_batch([text])
        return result[0]['text'] if result and result[0] and result[0]['type'] == 'simple' else None
        
    def translate_plural(self, msgid: str, msgid_plural: str) -> Optional[dict]:
        """Переводит строку с множественными формами."""
        if not msgid.strip() or not msgid_plural.strip():
            return None
            
        result = self.translate_batch([{'msgid': msgid, 'msgid_plural': msgid_plural}])
        if not result or not result[0] or result[0]['type'] != 'plural':
            return None
            
        return result[0]['forms']