import os
import shutil
import polib
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from translator import GeminiTranslator
import logging
import msvcrt

logger = logging.getLogger(__name__)

class TranslationManager:
    def __init__(self):
        self.translator = GeminiTranslator()
        self.current_file = None
        self.backup_dir = "backups"
        self.ensure_backup_dir()
        self.modified_entries = set()
        self.translation_interrupted = False

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
            po = polib.pofile(file_path, encoding='utf-8')
            
            for entry in po:
                if not entry.msgid and not entry.msgid_plural:
                    continue
                if not hasattr(entry, 'original_msgstr'):
                    entry.original_msgstr = entry.msgstr
                if hasattr(entry, 'msgid_plural'):
                    if not hasattr(entry, 'original_msgstr_plural'):
                        entry.original_msgstr_plural = entry.msgstr_plural.copy() if hasattr(entry, 'msgstr_plural') else {}
            
            po.metadata['Content-Type'] = 'text/plain; charset=utf-8'
            po.metadata['Content-Transfer-Encoding'] = '8bit'
            
            logger.info(f"Успешно загружен файл: {file_path}")
            return po
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_path}: {e}", exc_info=True)
            return None

    def print_stats(self, stats):
        """Выводим статистику в консоль"""
        print("\n=== Статистика переводов ===")
        print(f"Всего строк: {stats['total']}")
        print(f"Переведено: {stats['translated']}")
        print(f"Не переведено: {stats['untranslated']}")
        print(f"Процент перевода: {stats['percent_translated']}%\n")

    def get_untranslated_entries(self, po):
        """Получаем список непереведенных записей"""
        untranslated = []
        for entry in po:
            if not entry.msgid:
                continue
            if 'fuzzy' in entry.flags:
                untranslated.append(entry)
                continue

            is_translated = False

            if entry.msgid_plural:
                if entry.msgstr or (entry.msgstr_plural and any(entry.msgstr_plural.values())):
                    is_translated = True
            else:
                if entry.msgstr:
                    is_translated = True
            
            if not is_translated:
                untranslated.append(entry)
        
        return untranslated

    def get_translation_stats(self, po):
        """Получаем статистику по переводам"""
        entries = [e for e in po if e.msgid]
        total = len(entries)
        translated = 0

        for entry in entries:
            if 'fuzzy' in entry.flags:
                continue

            if entry.msgid_plural:
                if entry.msgstr or (entry.msgstr_plural and any(entry.msgstr_plural.values())):
                    translated += 1
            elif entry.msgstr:
                translated += 1
                
        return {
            'total': total,
            'translated': translated,
            'untranslated': total - translated,
            'percent_translated': round((translated / total * 100), 2) if total > 0 else 0
        }

    def print_untranslated(self, entries, count=10):
        """Выводим непереведенные строки"""
        if not entries:
            print("Нет непереведенных строк!")
            return
            
        print(f"\n=== Непереведенные строки (показано {min(count, len(entries))} из {len(entries)}) ===\n")
        
        for i, entry in enumerate(entries[:count], 1):
            print(f"{i}. [Исходный] {entry.msgid}")
            
            if entry.msgid_plural:
                print(f"   [Мн.число] {entry.msgid_plural}")
            print()


    def _process_translation_result(self, entry, translation):
        """Обрабатывает результат перевода для одной записи"""
        if not translation or not isinstance(translation, dict):
            logger.error(f"Неверный формат перевода: {translation} для msgid: '{entry.msgid}'")
            return False
            
        try:
            if translation.get('type') == 'simple':
                text = translation.get('text')
                if text is not None:
                    entry.msgstr = text
                    return True
            elif translation.get('type') == 'plural':
                forms = translation.get('forms', {})
                if forms and all(k in forms for k in ['one', 'few', 'many', 'other']):
                    # polib ожидает ключи 0, 1, 2 для русского языка.
                    # one -> 0, few -> 1, many -> 2
                    entry.msgstr_plural[0] = forms['one']
                    entry.msgstr_plural[1] = forms['few']
                    entry.msgstr_plural[2] = forms['many']
                    
                    # Устанавливаем msgstr в первую форму по умолчанию
                    entry.msgstr = forms['one']
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при обработке перевода для '{entry.msgid}': {e}", exc_info=True)
            return False

    def _check_key_press(self):
        """Проверяет нажатие клавиш Esc или Enter"""
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b'\x1b', b'\r', b'\n'):  # Esc, Enter
                return True
        return False

    def translate_entries(self, po, entries_to_translate, batch_size_override=None):
        """Переводим непереведенные записи пакетами с возможностью прерывания"""
        if not entries_to_translate:
            print("Нет строк для перевода!")
            return 0

        if batch_size_override is not None and batch_size_override > 0:
            entries_to_translate = entries_to_translate[:batch_size_override]

        print(f"\nНачинаем перевод {len(entries_to_translate)} строк...")
        print("Нажмите Esc, Enter или Ctrl+C для прерывания перевода")
        
        entries_to_process = [e for e in entries_to_translate if e.msgid.strip()]
        if not entries_to_process:
            print("Нет валидных строк для перевода!")
            return 0
            
        translated_count = 0
        batch_size = self.translator.BATCH_SIZE
        total_entries = len(entries_to_process)
        self.translation_interrupted = False
        
        try:
            with tqdm(total=total_entries, desc="Перевод строк") as pbar:
                for i in range(0, total_entries, batch_size):
                    # Проверяем нажатие клавиш
                    if self._check_key_press():
                        print("\nОбнаружено прерывание пользователем...")
                        self.translation_interrupted = True
                        break
                        
                    batch_entries = entries_to_process[i:i + batch_size]
                    
                    batch_to_translate = []
                    for entry in batch_entries:
                        if entry.msgid_plural:
                            batch_to_translate.append({
                                'msgid': entry.msgid,
                                'msgid_plural': entry.msgid_plural
                            })
                        else:
                            batch_to_translate.append(entry.msgid)
                    
                    try:
                        translations = self.translator.translate_batch(batch_to_translate)
                        
                        for entry, translation in zip(batch_entries, translations):
                            if self._process_translation_result(entry, translation):
                                translated_count += 1
                                if 'fuzzy' in entry.flags:
                                    entry.flags.remove('fuzzy')
                                
                    except Exception as e:
                        logger.error(f"Ошибка при пакетном переводе: {e}", exc_info=True)
                        # Продолжаем со следующим пакетом, если произошла ошибка
                        continue
                    
                    pbar.update(len(batch_entries))
                    pbar.set_postfix({'переведено': f"{translated_count}/{pbar.n}"})
                    
        except KeyboardInterrupt:
            print("\nПеревод прерван пользователем (Ctrl+C)")
            self.translation_interrupted = True
        
        if self.translation_interrupted:
            print(f"\nПеревод прерван. Успешно переведено {translated_count} строк.")
        else:
            print(f"\nПеревод завершен. Всего переведено: {translated_count} строк.")
            
        return translated_count

    def save_po_file(self, po, file_path):
        """Сохраняет PO файл"""
        try:
            if os.path.exists(file_path) and not os.access(file_path, os.W_OK):
                error_msg = f"Нет прав на запись в файл: {file_path}"
                print(f"Ошибка: {error_msg}")
                logger.error(error_msg)
                return False
                
            self.create_backup(file_path)
            
            logger.info(f"Попытка сохранения файла: {file_path}")
            po.save(file_path) 
            
            # Сбрасываем флаги изменений после успешного сохранения
            for entry in po:
                if hasattr(entry, 'original_msgstr'):
                    entry.original_msgstr = entry.msgstr
                if hasattr(entry, 'original_msgstr_plural') and hasattr(entry, 'msgstr_plural'):
                    entry.original_msgstr_plural = entry.msgstr_plural.copy()
            
            success_msg = f"Файл успешно сохранен: {file_path}"
            print(success_msg)
            logger.info(success_msg)
            return True
            
        except Exception as e:
            error_msg = f"Ошибка при сохранении файла {file_path}: {e}"
            print(f"Ошибка: {error_msg}")
            logger.error(error_msg, exc_info=True)
            return False

    def has_unsaved_changes(self, po):
        """Проверяем, есть ли несохраненные изменения"""
        for entry in po:
            if not hasattr(entry, 'original_msgstr'): # Новая, еще не сохраненная запись
                if entry.msgstr or entry.msgstr_plural:
                    return True
                continue
            
            # Проверяем обычные строки
            if entry.msgstr != entry.original_msgstr:
                return True
                
            # Проверяем множественные формы
            if hasattr(entry, 'msgid_plural'):
                current_plural = entry.msgstr_plural if hasattr(entry, 'msgstr_plural') else {}
                if current_plural != entry.original_msgstr_plural:
                    return True
                    
        return False

    def get_modified_entries(self, po):
        """Получаем список измененных, но не сохраненных записей"""
        modified = []
        for entry in po:
            if hasattr(entry, 'original_msgstr') and entry.msgstr != entry.original_msgstr:
                modified.append(entry)
            elif hasattr(entry, 'original_msgstr_plural'):
                if not hasattr(entry, 'msgstr_plural') or entry.msgstr_plural != entry.original_msgstr_plural:
                    modified.append(entry)
        return modified

    def view_and_edit_unsaved(self, po):
        """Просмотр и редактирование несохраненных изменений"""
        modified_entries = self.get_modified_entries(po)
        
        if not modified_entries:
            print("\nНет несохраненных изменений.")
            return
            
        while True:
            print("\n=== Несохраненные изменения ===")
            for i, entry in enumerate(modified_entries, 1):
                print(f"{i}. [Исходный] {entry.msgid[:80]}{'...' if len(entry.msgid) > 80 else ''}")
                print(f"   [Перевод]  {entry.msgstr[:80]}{'...' if len(entry.msgstr) > 80 else ''}\n")
            
            
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
            
            print("\n=== Редактирование перевода ===")
            print(f"Оригинал: {selected_entry.msgid}")
            print(f"Текущий перевод: {selected_entry.msgstr}")
            
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

    def ensure_original_backup(self, file_path):
        """Создаем резервную копию с суффиксом _original, если её нет"""
        backup_path = file_path.replace('.po', '_original.po')
        if not os.path.exists(backup_path):
            shutil.copy2(file_path, backup_path)
            logger.info(f"Создана резервная копия: {backup_path}")
        return backup_path

    def process_file(self, file_path, batch_size=None):
        """Обработка одного PO файла"""
        # Проверяем существование файла
        if not os.path.exists(file_path):
            error_msg = f"Файл не найден: {file_path}"
            print(f"Ошибка: {error_msg}")
            logger.error(error_msg)
            return False
            
        # Проверяем права на чтение
        if not os.access(file_path, os.R_OK):
            error_msg = f"Нет прав на чтение файла: {file_path}"
            print(f"Ошибка: {error_msg}")
            logger.error(error_msg)
            return False
            
        print(f"\nОбработка файла: {file_path}")
        print(f"Размер файла: {os.path.getsize(file_path)} байт")
        
        self.current_file = file_path
        
        # Создаем резервную копию с суффиксом _original, если её нет
        original_backup = self.ensure_original_backup(file_path)
        print(f"Резервная копия: {original_backup}")
        
        # Загружаем файл
        print("Загрузка файла...")
        po = self.load_po_file(file_path)
        if not po:
            return False
            
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
                    batch_size_override = int(batch) if batch else None
                    if batch_size_override == 0:
                        continue
                        
                    translated_count = self.translate_entries(po, untranslated, batch_size_override)
                    
                    # Обновляем статистику, только если перевод не был прерван
                    if not self.translation_interrupted:
                        print(f"\nУспешно переведено {translated_count} строк.")
                        stats = self.get_translation_stats(po)
                        self.print_stats(stats)
                    
                except ValueError:
                    print("Некорректный ввод!")
                    
            elif choice == '4':
                self.view_and_edit_unsaved(po)
                
            elif choice == '5':
                if self.save_po_file(po, file_path):  # Сохраняем в исходный файл
                    print("Изменения успешно сохранены!")
                    
            elif choice == '6':
                if self.has_unsaved_changes(po):
                    save_choice = input("\nЕсть несохраненные изменения. Сохранить перед выходом? (y/N): ").strip().lower()
                    if save_choice == 'y':
                        self.save_po_file(po, file_path)
                print("Завершение работы с файлом.")
                break # Выходим из цикла работы с файлом
                
            else:
                print("Некорректный выбор. Пожалуйста, введите число от 1 до 6.")
        return True # Возвращаемся в главное меню для выбора другого файла

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
            file_path = self.get_po_file_path()
            
            if file_path is None:
                # Если пользователь выбрал выйти из get_po_file_path
                file_path = input("\nВведите путь к PO файлу (или 'q' для выхода): ").strip()
                if file_path.lower() == 'q':
                    print("Выход из программы.")
                    return

            if not os.path.isfile(file_path):
                print(f"\nОшибка: Файл не найден: {file_path}")
                continue
                
            if not file_path.lower().endswith('.po'):
                print("\nОшибка: Файл должен иметь расширение .po")
                continue
            
            self.process_file(file_path)

            break
        
        print("\nРабота завершена.")