import os
import shutil
import polib
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from translator import GeminiTranslator
import logging

logger = logging.getLogger(__name__)

class TranslationManager:
    def __init__(self):
        self.translator = GeminiTranslator()
        self.current_file = None
        self.backup_dir = "backups"
        self.ensure_backup_dir()
        self.modified_entries = set()  # Множество для хранения ID измененных записей

    def ensure_backup_dir(self):
        """Создаем директорию для бэкапов, если её нет"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def create_backup(self, file_path):
        """Создаем резервную копию файла"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(
            self.backup_dir,
            f"{Path(file_path).stem}_{timestamp}.po"
        )
        shutil.copy2(file_path, backup_path)
        logger.info(f"Создана резервная копия: {backup_path}")
        return backup_path

    def load_po_file(self, file_path):
        """Загружаем PO файл"""
        try:
            po = polib.pofile(file_path)
            # Инициализируем атрибут для отслеживания изменений
            for entry in po:
                if not hasattr(entry, 'original_msgstr'):
                    entry.original_msgstr = entry.msgstr
            return po
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_path}: {str(e)}")
            return None

    def get_translation_stats(self, po):
        """Получаем статистику по переводам"""
        total = len(po)
        translated = sum(1 for entry in po if entry.msgstr)
        return {
            'total': total,
            'translated': translated,
            'untranslated': total - translated,
            'percent_translated': round((translated / total * 100), 2) if total > 0 else 0
        }

    def print_stats(self, stats):
        """Выводим статистику в консоль"""
        print("\n=== Статистика переводов ===")
        print(f"Всего строк: {stats['total']}")
        print(f"Переведено: {stats['translated']}")
        print(f"Не переведено: {stats['untranslated']}")
        print(f"Процент перевода: {stats['percent_translated']}%\n")

    def get_untranslated_entries(self, po):
        """Получаем список непереведенных записей"""
        return [entry for entry in po if not entry.msgstr]

    def print_untranslated(self, entries, count=10):
        """Выводим непереведенные строки"""
        print(f"\n=== Первые {min(count, len(entries))} непереведенных строк ===")
        for i, entry in enumerate(entries[:count]):
            print(f"{i+1}. {entry.msgid[:100]}{'...' if len(entry.msgid) > 100 else ''}")
        if len(entries) > count:
            print(f"... и еще {len(entries) - count} строк")
        print()

    def translate_entries(self, po, entries_to_translate, batch_size=None):
        """Переводим непереведенные записи пакетами"""
        if not entries_to_translate:
            print("Нет строк для перевода!")
            return 0

        if batch_size:
            entries_to_translate = entries_to_translate[:batch_size]

        print(f"\nНачинаем перевод {len(entries_to_translate)} строк...")
        
        # Фильтруем пустые строки и сохраняем оригинальные значения
        entries_to_process = []
        for entry in entries_to_translate:
            if entry.msgid.strip():
                if not hasattr(entry, 'original_msgstr'):
                    entry.original_msgstr = entry.msgstr
                entries_to_process.append(entry)
        
        if not entries_to_process:
            print("Нет валидных строк для перевода!")
            return 0
            
        translated_count = 0
        batch_size = self.translator.BATCH_SIZE
        total_entries = len(entries_to_process)
        
        with tqdm(total=total_entries, desc="Перевод строк") as pbar:
            for i in range(0, len(entries_to_process), batch_size):
                # Получаем пакет записей для перевода
                batch_entries = entries_to_process[i:i + batch_size]
                batch_texts = [entry.msgid for entry in batch_entries]
                
                try:
                    # Переводим пакет
                    translations = self.translator.translate_batch(batch_texts)
                    
                    # Обновляем переводы
                    for entry, translation in zip(batch_entries, translations):
                        if translation is not None:
                            entry.msgstr = translation
                            translated_count += 1
                            
                except Exception as e:
                    logger.error(f"Ошибка при пакетном переводе: {str(e)}")
                
                # Обновляем прогресс-бар
                pbar.update(len(batch_entries))
                pbar.set_postfix({
                    'переведено': f"{translated_count}/{total_entries}",
                    'прогресс': f"{pbar.n/pbar.total*100:.1f}%"
                })
                
        return translated_count

    def save_po_file(self, po, file_path):
        """Сохраняем PO файл"""
        try:
            # Сбрасываем флаги изменений при сохранении
            for entry in po:
                if hasattr(entry, 'original_msgstr'):
                    entry.original_msgstr = entry.msgstr
                    
            po.save(file_path)
            logger.info(f"Файл успешно сохранен: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла: {str(e)}")
            return False

    def get_modified_entries(self, po):
        """Получаем список измененных, но не сохраненных записей"""
        return [entry for entry in po if hasattr(entry, 'original_msgstr') and entry.msgstr != entry.original_msgstr]

    def view_and_edit_unsaved(self, po):
        """Просмотр и редактирование несохраненных изменений"""
        modified_entries = self.get_modified_entries(po)
        
        if not modified_entries:
            print("\nНет несохраненных изменений.")
            return
            
        while True:
            # Выводим список несохраненных изменений
            print("\n=== Несохраненные изменения ===")
            for i, entry in enumerate(modified_entries, 1):
                print(f"{i}. [Исходный] {entry.msgid[:80]}{'...' if len(entry.msgid) > 80 else ''}")
                print(f"   [Перевод]  {entry.msgstr[:80]}{'...' if len(entry.msgstr) > 80 else ''}\n")
            
            # Запрашиваем номер строки для редактирования
            while True:
                choice = input("\nВведите номер строки для редактирования (или Enter для выхода): ").strip()
                if not choice:
                    return
                    
                try:
                    entry_num = int(choice)
                    if 1 <= entry_num <= len(modified_entries):
                        break
                    print(f"Пожалуйста, введите число от 1 до {len(modified_entries)}")
                except ValueError:
                    print("Пожалуйста, введите корректный номер строки.")
            
            # Получаем выбранную запись
            selected_entry = modified_entries[entry_num - 1]
            
            # Выводим полный текст выбранной записи
            print("\n=== Редактирование перевода ===")
            print(f"Оригинал: {selected_entry.msgid}")
            print(f"Текущий перевод: {selected_entry.msgstr}")
            
            # Запрашиваем новый перевод
            new_translation = input("\nВведите новый перевод (или Enter для отмены): ").strip()
            if new_translation:
                # Сохраняем оригинальное значение, если это первое изменение
                if not hasattr(selected_entry, 'original_msgstr'):
                    selected_entry.original_msgstr = selected_entry.msgstr
                    
                selected_entry.msgstr = new_translation
                print("Перевод обновлен.")
                # Обновляем список измененных записей
                modified_entries = self.get_modified_entries(po)
            else:
                print("Редактирование отменено.")

    def process_file(self, file_path, batch_size=None):
        """Обработка одного PO файла"""
        self.current_file = file_path
        
        # Создаем копию файла для работы
        work_file = file_path.replace('.po', '_translated.po')
        if not os.path.exists(work_file):
            shutil.copy2(file_path, work_file)
        
        # Загружаем файл
        po = self.load_po_file(work_file)
        if not po:
            return False
            
        # Получаем статистику
        stats = self.get_translation_stats(po)
        self.print_stats(stats)
        
        # Основной цикл работы с файлом
        while True:
            print("\nВыберите действие:")
            print("1. Показать статистику")
            print("2. Показать непереведенные строки")
            print("3. Перевести строки")
            print("4. Просмотреть/редактировать несохраненные изменения")
            print("5. Сохранить изменения")
            print("6. Выход")
            
            choice = input("\nВаш выбор (1-6): ").strip()
            
            if choice == '1':
                stats = self.get_translation_stats(po)
                self.print_stats(stats)
                
            elif choice == '2':
                untranslated = self.get_untranslated_entries(po)
                if not untranslated:
                    print("Все строки переведены!")
                    continue
                count = input(f"Сколько строк показать (макс {len(untranslated)}): ").strip()
                try:
                    count = min(int(count), len(untranslated)) if count else 10
                    self.print_untranslated(untranslated, count)
                except ValueError:
                    print("Некорректное число!")
                    
            elif choice == '3':
                untranslated = self.get_untranslated_entries(po)
                if not untranslated:
                    print("Нет непереведенных строк!")
                    continue
                    
                print(f"\nНайдено {len(untranslated)} непереведенных строк.")
                batch = input(f"Сколько строк перевести (Enter для всех, 0 для отмены): ").strip()
                
                try:
                    batch_size = int(batch) if batch else None
                    if batch_size == 0:
                        continue
                        
                    translated_count = self.translate_entries(po, untranslated, batch_size)
                    print(f"\nУспешно переведено {translated_count} строк.")
                    
                    # Обновляем статистику
                    stats = self.get_translation_stats(po)
                    self.print_stats(stats)
                    
                except ValueError:
                    print("Некорректный ввод!")
                    
            elif choice == '4':
                self.view_and_edit_unsaved(po)
                
            elif choice == '5':
                if self.save_po_file(po, work_file):
                    print("Изменения успешно сохранены!")
                    
            elif choice == '6':
                # Проверяем, есть ли несохраненные изменения
                if po.percent_translated() != self.get_translation_stats(po)['percent_translated']:
                    save = input("\nЕсть несохраненные изменения. Сохранить перед выходом? (y/N): ").strip().lower()
                    if save == 'y':
                        self.save_po_file(po, work_file)
                return True
                
            else:
                print("Некорректный выбор. Пожалуйста, введите число от 1 до 6.")

    def get_po_file_path(self):
        """Получаем путь к PO файлу из переменных окружения или запрашиваем у пользователя"""
        file_path = os.getenv('PO_FILE_PATH', '').strip()
        
        if file_path and os.path.isfile(file_path):
            return file_path
            
        if file_path:
            print(f"\nФайл, указанный в настройках, не найден: {file_path}")
        else:
            print("\nПуть к PO файлу не указан в настройках.")
            
        print("\nВы можете:")
        print("1. Указать путь к файлу вручную")
        print("2. Задать путь в файле .env (переменная PO_FILE_PATH)")
        print("3. Выйти из программы")
        
        while True:
            choice = input("\nВаш выбор (1-3): ").strip()
            
            if choice == '1':
                break
            elif choice == '2':
                print("\nОткройте файл .env в корневой директории проекта")
                print("и добавьте или измените строку:")
                print('PO_FILE_PATH="путь_к_вашему_файлу.po"')
                input("\nНажмите Enter после сохранения изменений...")
                file_path = os.getenv('PO_FILE_PATH', '').strip()
                if file_path and os.path.isfile(file_path):
                    return file_path
                print("Файл по-прежнему не найден. Проверьте путь и повторите попытку.")
            elif choice == '3':
                return None
            else:
                print("Некорректный выбор. Пожалуйста, введите 1, 2 или 3.")
        
        return None

    def run(self):
        """Основной метод запуска приложения"""
        print("\n=== Инструмент для перевода PO файлов ===")
        
        while True:
            # Пытаемся получить путь из .env
            file_path = self.get_po_file_path()
            
            # Если пользователь выбрал выход
            if file_path is None:
                print("Выход из программы.")
                break
                
            # Если путь не был получен из .env, запрашиваем у пользователя
            if not file_path:
                file_path = input("\nВведите путь к PO файлу (или 'q' для выхода): ").strip()
                
                if file_path.lower() == 'q':
                    print("Выход из программы.")
                    break
            
            # Проверяем существование файла
            if not os.path.isfile(file_path):
                print(f"\nОшибка: Файл не найден: {file_path}")
                print("Пожалуйста, проверьте путь и повторите попытку.")
                continue
                
            # Проверяем расширение файла
            if not file_path.lower().endswith('.po'):
                print("\nОшибка: Файл должен иметь расширение .po")
                continue
            
            # Создаем резервную копию оригинального файла
            self.create_backup(file_path)
            
            # Обрабатываем файл
            self.process_file(file_path)
            
            # Сбрасываем путь к файлу для следующей итерации
            file_path = None
