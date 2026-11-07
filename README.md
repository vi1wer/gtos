# GT/OS

Настольная операционная система на Linux + Qt 6.

**Автор:** Glukhov Mikhail  
**Сайт:** локально `python website/app.py` (порт 5050)  
**Почта:** mikhail.lososka@gmail.com

## Скачать

Официальные ISO публикуются в [Releases](https://github.com/vi1wer/gtos/releases).

Текущий выпуск: **1.5.6**.

## Сборка

```bash
python build.py          # ядро + initrd
python make_iso.py --version 1.5.6
python run.py            # QEMU
python run.py --safe     # безопасный режим
```

После правок оболочки:

```bash
python refresh_ui.py
python run.py
```

## Безопасный режим

- ISO/GRUB: пункт **GT/OS (Safe Mode)** (`gtos.safemode=1`)
- Из сеанса: Ctrl+Alt+Delete → «Безопасный режим»
- QEMU: `python run.py --safe`

В safe mode не поднимаются автоматически CUPS и сохранённый Wi‑Fi; каталог магазина не подгружается в фоне.

## Лицензия / продукт

GT/OS — продукт **Glukhov Mikhail**.
