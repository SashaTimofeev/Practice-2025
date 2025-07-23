# Инструмент для перевода PO файлов Indico

Этот инструмент помогает переводить PO файлы для проекта Indico с использованием Google Gemini API.

## Требования

- Python 3.8+
- API ключ от Google AI Studio (Gemini)

## Установка

1. Клонируйте репозиторий:
   ```bash
   git clone <repository-url>
   cd <repository-folder>
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Получите API ключ Gemini:
   - Перейдите по ссылке https://aistudio.google.com/apikey
   - Нажмите на кнопку "Create API key"
   - Следуйте дальнейшим инструкциям на экране

5. Настройте окружение:
   - Создайте файл `.env` в корневой директории
   - В .env файле укажите API ключ от Google AI Studio
   ```
   GOOGLE_API_KEY=
   PO_FILE_PATH=for_translation_indico_core-messages-all_ru_RU-2.po

   # Настройки логирования
   LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
   LOG_FILE=translation_tool.log
   ```



## Использование

1. Запустите программу:
   ```bash
   python main.py
   ```

2. Следуйте инструкциям в консоли:
   - Введите путь к PO файлу для перевода, если не указали его в .env
   - Выберите действие из меню
   - Сохраняйте изменения по мере работы

## Функции

- Просмотр статистики по переводам
- Просмотр непереведенных строк
- Автоматический перевод строк с помощью Gemini API
- Сохранение прогресса
- Автоматическое создание резервных копий

## Логи

Логи сохраняются в папку `logs/translation_tool.log`
