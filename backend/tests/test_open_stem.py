from app.generation.openai_client import build_open_stem


def test_build_open_stem_has_all_blocks():
    stem = build_open_stem(
        topic_title="От бизнес-проблемы к требованиям",
        case="В финтех-компании растёт количество обращений.",
        task="Сформулируйте до 5 уточняющих вопросов.",
        focus="Не нужно проектировать архитектуру.",
        criteria_visible="понимание бизнес-потребности; качество вопросов.",
    )
    # Header lines
    assert "до 2500 знаков с пробелами" in stem
    assert "Тип: открытый кейс. От бизнес-проблемы к требованиям" in stem
    # Body blocks, each on its own labelled line
    assert "В финтех-компании растёт количество обращений." in stem
    assert "Задание: Сформулируйте до 5 уточняющих вопросов." in stem
    assert "Фокус ответа: Не нужно проектировать архитектуру." in stem
    assert "Критерии оценки: понимание бизнес-потребности; качество вопросов." in stem
    # Blocks are newline-separated so the frontend can render them on separate lines
    assert "\n" in stem
    assert stem.count("\n\n") >= 1  # blank line between header/case and blocks
